# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from typing import AsyncIterator

from fastedgy.storage.adapters.base import StorageAdapter


class S3Adapter(StorageAdapter):
    """Storage adapter for S3-compatible object storage.

    Uses aioboto3 for async S3 operations.
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
        self._session = None

    def _key(self, path: str) -> str:
        """Build the full S3 key from a relative path."""
        clean = path.strip("/")
        if self.prefix:
            return f"{self.prefix}/{clean}"
        return clean

    def _get_session(self):
        if self._session is None:
            import aioboto3

            self._session = aioboto3.Session()
        return self._session

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

    def _client(self):
        return self._get_session().client("s3", **self._client_kwargs())

    async def exists(self, path: str) -> bool:
        from botocore.exceptions import ClientError

        async with self._client() as s3:
            try:
                await s3.head_object(Bucket=self.bucket, Key=self._key(path))
                return True
            except ClientError as e:
                if e.response["Error"]["Code"] == "404":
                    return False
                raise

    async def read(self, path: str) -> bytes:
        async with self._client() as s3:
            response = await s3.get_object(Bucket=self.bucket, Key=self._key(path))
            return await response["Body"].read()

    async def read_stream(self, path: str, chunk_size: int = 1024 * 1024) -> AsyncIterator[bytes]:
        async with self._client() as s3:
            response = await s3.get_object(Bucket=self.bucket, Key=self._key(path))
            stream = response["Body"]
            while True:
                chunk = await stream.read(chunk_size)
                if not chunk:
                    break
                yield chunk

    async def read_range_stream(
        self, path: str, start: int, end: int, chunk_size: int = 1024 * 1024
    ) -> AsyncIterator[bytes]:
        async with self._client() as s3:
            response = await s3.get_object(
                Bucket=self.bucket,
                Key=self._key(path),
                Range=f"bytes={start}-{end}",
            )
            stream = response["Body"]
            while True:
                chunk = await stream.read(chunk_size)
                if not chunk:
                    break
                yield chunk

    async def write(self, path: str, data: bytes, content_type: str | None = None) -> None:
        async with self._client() as s3:
            kwargs: dict = {
                "Bucket": self.bucket,
                "Key": self._key(path),
                "Body": data,
            }
            if content_type:
                kwargs["ContentType"] = content_type
            await s3.put_object(**kwargs)

    async def delete(self, path: str) -> None:
        async with self._client() as s3:
            try:
                await s3.delete_object(Bucket=self.bucket, Key=self._key(path))
            except Exception:
                pass

    async def delete_directory(self, path: str) -> None:
        async with self._client() as s3:
            prefix = self._key(path).rstrip("/") + "/"
            paginator = s3.get_paginator("list_objects_v2")

            async for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
                objects = page.get("Contents", [])
                if objects:
                    delete_request = {
                        "Objects": [{"Key": obj["Key"]} for obj in objects]
                    }
                    await s3.delete_objects(
                        Bucket=self.bucket, Delete=delete_request
                    )

    async def file_size(self, path: str) -> int:
        async with self._client() as s3:
            response = await s3.head_object(Bucket=self.bucket, Key=self._key(path))
            return response["ContentLength"]


__all__ = [
    "S3Adapter",
]
