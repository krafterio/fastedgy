# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime, timedelta
from threading import Lock
from typing import TYPE_CHECKING, BinaryIO, cast

from anyio import to_thread

from fastedgy.storage.adapters.base import StorageAdapter, clean_storage_path

if TYPE_CHECKING:
    from botocore.response import StreamingBody
    from types_boto3_s3 import S3Client
    from types_boto3_s3.type_defs import ObjectIdentifierTypeDef

MAX_POOL_CONNECTIONS = 50


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
    ):
        self.bucket = bucket
        self.region = region
        self.endpoint = endpoint
        self.access_key_id = access_key_id
        self.secret_access_key = secret_access_key
        self.prefix = prefix.strip("/") if prefix else None
        self._s3: "S3Client | None" = None
        self._lock = Lock()

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

                config = Config(max_pool_connections=MAX_POOL_CONNECTIONS)
                self._s3 = cast("S3Client", boto3.Session().client("s3", config=config, **self._client_kwargs()))

            return self._s3

    async def _run[T](self, call: Callable[["S3Client"], T]) -> T:
        return await to_thread.run_sync(lambda: call(self._client()))

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

    async def exists(self, path: str) -> bool:
        from botocore.exceptions import ClientError

        try:
            await self._run(lambda s3: s3.head_object(Bucket=self.bucket, Key=self._key(path)))
        except ClientError as e:
            if e.response["Error"]["Code"] == "404":
                return False
            raise

        return True

    async def read(self, path: str) -> bytes:
        return await self._run(lambda s3: s3.get_object(Bucket=self.bucket, Key=self._key(path))["Body"].read())

    async def read_stream(self, path: str, chunk_size: int = 1024 * 1024) -> AsyncIterator[bytes]:
        response = await self._run(lambda s3: s3.get_object(Bucket=self.bucket, Key=self._key(path)))

        async for chunk in self._chunks(response["Body"], chunk_size):
            yield chunk

    async def read_range_stream(
        self, path: str, start: int, end: int, chunk_size: int = 1024 * 1024
    ) -> AsyncIterator[bytes]:
        response = await self._run(
            lambda s3: s3.get_object(Bucket=self.bucket, Key=self._key(path), Range=f"bytes={start}-{end}")
        )

        async for chunk in self._chunks(response["Body"], chunk_size):
            yield chunk

    async def write(self, path: str, data: bytes, content_type: str | None = None) -> None:
        kwargs: dict = {
            "Bucket": self.bucket,
            "Key": self._key(path),
            "Body": data,
        }
        if content_type:
            kwargs["ContentType"] = content_type

        await self._run(lambda s3: s3.put_object(**kwargs))

    async def write_file(self, path: str, file: BinaryIO, content_type: str | None = None) -> None:
        extra = {"ContentType": content_type} if content_type else None

        await self._run(lambda s3: s3.upload_fileobj(file, self.bucket, self._key(path), ExtraArgs=extra))

    async def delete(self, path: str) -> None:
        try:
            await self._run(lambda s3: s3.delete_object(Bucket=self.bucket, Key=self._key(path)))
        except Exception:
            pass

    async def delete_directory(self, path: str) -> None:
        await self._run(lambda s3: self._delete_under(s3, path))

    async def file_size(self, path: str) -> int:
        response = await self._run(lambda s3: s3.head_object(Bucket=self.bucket, Key=self._key(path)))
        return response["ContentLength"]

    async def delete_old_files(self, prefix: str, max_age_seconds: float) -> int:
        before = datetime.now(UTC) - timedelta(seconds=max_age_seconds)

        return await self._run(lambda s3: self._delete_under(s3, prefix, before))


__all__ = [
    "S3Adapter",
]
