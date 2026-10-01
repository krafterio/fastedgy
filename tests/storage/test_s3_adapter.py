# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import builtins
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from io import BytesIO

import pytest
from botocore.response import StreamingBody
from botocore.stub import Stubber

from fastedgy.storage.adapters.s3 import S3Adapter


@pytest.fixture
def adapter() -> S3Adapter:
    return S3Adapter(
        bucket="my-bucket",
        region="gra",
        endpoint="https://s3.gra.io.cloud.ovh.net",
        access_key_id="key",
        secret_access_key="secret",
        prefix="data",
    )


@pytest.fixture
def stub(adapter: S3Adapter) -> Iterator[Stubber]:
    with Stubber(adapter._client()) as stubber:
        yield stubber
        stubber.assert_no_pending_responses()


def _body(data: bytes) -> StreamingBody:
    return StreamingBody(BytesIO(data), len(data))


def test_s3_adapter_requires_boto3(monkeypatch: pytest.MonkeyPatch) -> None:
    real_import = builtins.__import__

    def fake_import(name: str, *args, **kwargs):
        if name == "boto3":
            raise ImportError("boto3 is not installed")

        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    adapter = S3Adapter(bucket="my-bucket")

    with pytest.raises(ImportError, match=r"fastedgy\[storage-s3\]"):
        adapter._client()


async def test_exists_reads_the_head_of_the_prefixed_key(adapter: S3Adapter, stub: Stubber) -> None:
    stub.add_response("head_object", {"ContentLength": 5}, {"Bucket": "my-bucket", "Key": "data/a/b.txt"})
    stub.add_client_error("head_object", service_error_code="404", http_status_code=404)

    assert await adapter.exists("/a/b.txt") is True
    assert await adapter.exists("a/missing.txt") is False


async def test_read_and_stream_the_object(adapter: S3Adapter, stub: Stubber) -> None:
    key = {"Bucket": "my-bucket", "Key": "data/notes.txt"}
    stub.add_response("get_object", {"Body": _body(b"hello world")}, key)
    stub.add_response("get_object", {"Body": _body(b"hello world")}, key)
    stub.add_response("get_object", {"Body": _body(b"o w")}, {**key, "Range": "bytes=4-6"})

    assert await adapter.read("notes.txt") == b"hello world"
    assert [chunk async for chunk in adapter.read_stream("notes.txt", chunk_size=4)] == [b"hell", b"o wo", b"rld"]
    assert [chunk async for chunk in adapter.read_range_stream("notes.txt", 4, 6, chunk_size=2)] == [b"o ", b"w"]


async def test_write_sends_the_content_type(adapter: S3Adapter, stub: Stubber) -> None:
    stub.add_response(
        "put_object",
        {},
        {"Bucket": "my-bucket", "Key": "data/img.jpg", "Body": b"jpeg", "ContentType": "image/jpeg"},
    )

    await adapter.write("img.jpg", b"jpeg", content_type="image/jpeg")


async def test_delete_old_files_removes_only_the_expired_ones(adapter: S3Adapter, stub: Stubber) -> None:
    now = datetime.now(UTC)
    stub.add_response(
        "list_objects_v2",
        {
            "Contents": [
                {"Key": "data/tmp/old.bin", "LastModified": now - timedelta(hours=2)},
                {"Key": "data/tmp/new.bin", "LastModified": now},
            ]
        },
        {"Bucket": "my-bucket", "Prefix": "data/tmp/"},
    )
    stub.add_response(
        "delete_objects",
        {},
        {"Bucket": "my-bucket", "Delete": {"Objects": [{"Key": "data/tmp/old.bin"}]}},
    )

    assert await adapter.delete_old_files("tmp", max_age_seconds=3600) == 1


async def test_file_size_and_delete(adapter: S3Adapter, stub: Stubber) -> None:
    stub.add_response("head_object", {"ContentLength": 42}, {"Bucket": "my-bucket", "Key": "data/a.bin"})
    stub.add_client_error("delete_object", service_error_code="AccessDenied", http_status_code=403)

    assert await adapter.file_size("a.bin") == 42
    await adapter.delete("a.bin")
