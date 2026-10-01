# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from collections.abc import AsyncIterator, Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Lock
from typing import TYPE_CHECKING, Any, BinaryIO, cast

from anyio import to_thread

from fastedgy.storage.adapters.base import StorageAdapter, clean_storage_path

if TYPE_CHECKING:
    from botocore.response import StreamingBody
    from types_boto3_s3 import S3Client
    from types_boto3_s3.type_defs import GetObjectOutputTypeDef, ObjectIdentifierTypeDef

MAX_POOL_CONNECTIONS = 50

MISSING_CODES = ("404", "NoSuchKey")

MAX_COPY_SIZE = 5 * 1024**3


class S3Adapter(StorageAdapter):
    """Storage adapter for S3-compatible object storage.

    Uses boto3, each call run in a worker thread so the event loop never waits on S3.
    """

    def __init__(
        self,
        bucket: str,
        region: str | None = None,
        endpoint: str | None = None,
        access_key_id: str | None = None,
        secret_access_key: str | None = None,
        prefix: str | None = None,
        storage_class: str | None = None,
    ):
        self.bucket = bucket
        self.region = region
        self.endpoint = endpoint
        self.access_key_id = access_key_id
        self.secret_access_key = secret_access_key
        self.prefix = prefix.strip("/") if prefix else None
        self.storage_class = storage_class
        self._s3: "S3Client | None" = None
        self._lock = Lock()

    @property
    def location(self) -> str:
        return f"s3://{self.endpoint or ''}/{self.bucket}/{self.prefix or ''}"

    def _key(self, path: str) -> str:
        """Build the full S3 key from a relative path."""
        clean = clean_storage_path(path)
        if self.prefix:
            return f"{self.prefix}/{clean}"
        return clean

    def _client_kwargs(self) -> dict:
        kwargs: dict = {}
        if self.region:
            kwargs["region_name"] = self.region
        if self.endpoint:
            kwargs["endpoint_url"] = self.endpoint
        if self.access_key_id:
            kwargs["aws_access_key_id"] = self.access_key_id
        if self.secret_access_key:
            kwargs["aws_secret_access_key"] = self.secret_access_key
        return kwargs

    def _client(self) -> "S3Client":
        with self._lock:
            if self._s3 is None:
                try:
                    import boto3
                except ImportError as e:
                    raise ImportError(
                        "The s3 storage adapter requires boto3. Install it with: pip install 'fastedgy[storage-s3]'"
                    ) from e

                from botocore.config import Config

                config = Config(
                    max_pool_connections=MAX_POOL_CONNECTIONS,
                    retries={"mode": "standard"},
                    tcp_keepalive=True,
                )
                self._s3 = cast("S3Client", boto3.Session().client("s3", config=config, **self._client_kwargs()))

            return self._s3

    async def _run[T](self, call: Callable[["S3Client"], T]) -> T:
        return await to_thread.run_sync(lambda: call(self._client()))

    async def _found[T](self, path: str, call: Callable[["S3Client"], T]) -> T:
        from botocore.exceptions import ClientError

        try:
            return await self._run(call)
        except ClientError as e:
            if e.response["Error"]["Code"] in MISSING_CODES:
                raise FileNotFoundError(path) from e
            raise

    async def _get(self, path: str, byte_range: str | None = None) -> "GetObjectOutputTypeDef":
        key = self._key(path)

        if byte_range:
            return await self._found(path, lambda s3: s3.get_object(Bucket=self.bucket, Key=key, Range=byte_range))

        return await self._found(path, lambda s3: s3.get_object(Bucket=self.bucket, Key=key))

    @staticmethod
    async def _chunks(body: "StreamingBody", chunk_size: int) -> AsyncIterator[bytes]:
        try:
            while chunk := await to_thread.run_sync(body.read, chunk_size):
                yield chunk
        finally:
            body.close()

    def _delete_under(self, s3: "S3Client", path: str, before: datetime | None = None) -> int:
        deleted = 0
        prefix = self._key(path).rstrip("/") + "/"

        for page in s3.get_paginator("list_objects_v2").paginate(Bucket=self.bucket, Prefix=prefix):
            objects: list["ObjectIdentifierTypeDef"] = [
                {"Key": obj["Key"]}
                for obj in page.get("Contents", [])
                if before is None or obj.get("LastModified", before) < before
            ]

            if objects:
                s3.delete_objects(Bucket=self.bucket, Delete={"Objects": objects})
                deleted += len(objects)

        return deleted

    def _usage_under(self, s3: "S3Client", prefix: str) -> dict[str, tuple[int, int]]:
        usage: dict[str, tuple[int, int]] = {}
        base = self._key(prefix)
        base = f"{base}/" if base and not base.endswith("/") else base

        for page in s3.get_paginator("list_objects_v2").paginate(Bucket=self.bucket, Prefix=base):
            for obj in page.get("Contents", []):
                rest = obj.get("Key", "")[len(base) :]

                if not rest or rest.endswith("/"):
                    continue

                folder = rest.split("/", 1)[0] if "/" in rest else ""
                files, size = usage.get(folder, (0, 0))
                usage[folder] = (files + 1, size + obj.get("Size", 0))

        return usage

    def _move_to_class(self, s3: "S3Client", storage_class: str, dry_run: bool, workers: int) -> tuple[int, int, int]:
        moved = size = skipped = 0
        prefix = f"{self.prefix}/" if self.prefix else ""

        def move(key: str) -> None:
            s3.copy_object(
                Bucket=self.bucket,
                Key=key,
                CopySource={"Bucket": self.bucket, "Key": key},
                StorageClass=cast("Any", storage_class),
                MetadataDirective="COPY",
            )

        with ThreadPoolExecutor(workers) as pool:
            for page in s3.get_paginator("list_objects_v2").paginate(Bucket=self.bucket, Prefix=prefix):
                pending = [
                    obj for obj in page.get("Contents", []) if obj.get("StorageClass", "STANDARD") != storage_class
                ]
                movable = [obj for obj in pending if obj.get("Size", 0) <= MAX_COPY_SIZE]
                skipped += len(pending) - len(movable)

                if not dry_run:
                    list(pool.map(move, [obj.get("Key", "") for obj in movable]))

                moved += len(movable)
                size += sum(obj.get("Size", 0) for obj in movable)

        return moved, size, skipped

    async def set_storage_class(
        self, storage_class: str, dry_run: bool = False, workers: int = 16
    ) -> tuple[int, int, int]:
        """Move every object under the prefix to storage_class, copied in place by the server.

        Return the objects and bytes moved, or that would be with dry_run, and the objects over the 5 GiB a single
        copy accepts, left as they are."""
        return await self._run(lambda s3: self._move_to_class(s3, storage_class, dry_run, workers))

    async def exists(self, path: str) -> bool:
        try:
            await self._found(path, lambda s3: s3.head_object(Bucket=self.bucket, Key=self._key(path)))
        except FileNotFoundError:
            return False

        return True

    async def read(self, path: str) -> bytes:
        key = self._key(path)

        return await self._found(path, lambda s3: s3.get_object(Bucket=self.bucket, Key=key)["Body"].read())

    async def read_stream(self, path: str, chunk_size: int = 1024 * 1024) -> AsyncIterator[bytes]:
        response = await self._get(path)

        async for chunk in self._chunks(response["Body"], chunk_size):
            yield chunk

    async def read_range_stream(
        self, path: str, start: int, end: int, chunk_size: int = 1024 * 1024
    ) -> AsyncIterator[bytes]:
        response = await self._get(path, f"bytes={start}-{end}")

        async for chunk in self._chunks(response["Body"], chunk_size):
            yield chunk

    async def open_stream(self, path: str, chunk_size: int = 1024 * 1024) -> tuple[int, AsyncIterator[bytes]]:
        response = await self._get(path)

        return response["ContentLength"], self._chunks(response["Body"], chunk_size)

    async def open_range(
        self, path: str, start: int, end: int | None, chunk_size: int = 1024 * 1024
    ) -> tuple[int, int, int, AsyncIterator[bytes]] | None:
        from botocore.exceptions import ClientError

        if end is not None and end < start:
            return None

        try:
            response = await self._get(path, f"bytes={start}-{'' if end is None else end}")
        except ClientError as e:
            if e.response["Error"]["Code"] == "InvalidRange":
                return None
            raise

        served, total = response["ContentRange"].removeprefix("bytes ").split("/")
        first, last = served.split("-")

        return int(first), int(last), int(total), self._chunks(response["Body"], chunk_size)

    async def write(self, path: str, data: bytes, content_type: str | None = None) -> None:
        kwargs: dict = {
            "Bucket": self.bucket,
            "Key": self._key(path),
            "Body": data,
        }
        if content_type:
            kwargs["ContentType"] = content_type
        if self.storage_class:
            kwargs["StorageClass"] = self.storage_class

        await self._run(lambda s3: s3.put_object(**kwargs))

    async def write_file(self, path: str, file: BinaryIO, content_type: str | None = None) -> None:
        extra: dict = {}
        if content_type:
            extra["ContentType"] = content_type
        if self.storage_class:
            extra["StorageClass"] = self.storage_class

        await self._run(lambda s3: s3.upload_fileobj(file, self.bucket, self._key(path), ExtraArgs=extra))

    async def delete(self, path: str) -> None:
        try:
            await self._run(lambda s3: s3.delete_object(Bucket=self.bucket, Key=self._key(path)))
        except Exception:
            pass

    async def delete_directory(self, path: str) -> None:
        await self._run(lambda s3: self._delete_under(s3, path))

    async def file_size(self, path: str) -> int:
        response = await self._found(path, lambda s3: s3.head_object(Bucket=self.bucket, Key=self._key(path)))
        return response["ContentLength"]

    async def delete_old_files(self, prefix: str, max_age_seconds: float) -> int:
        before = datetime.now(UTC) - timedelta(seconds=max_age_seconds)

        return await self._run(lambda s3: self._delete_under(s3, prefix, before))

    async def usage(self, prefix: str = "") -> dict[str, tuple[int, int]]:
        return await self._run(lambda s3: self._usage_under(s3, prefix))


__all__ = [
    "S3Adapter",
]
