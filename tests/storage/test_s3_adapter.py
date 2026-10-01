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


def _operations(adapter: S3Adapter) -> list[str]:
    called: list[str] = []
    adapter._client().meta.events.register(
        "before-parameter-build.s3", lambda model, **kwargs: called.append(model.name)
    )
    return called


async def test_write_file_sends_a_small_file_in_one_put(adapter: S3Adapter, stub: Stubber) -> None:
    called = _operations(adapter)
    stub.add_response("put_object", {})

    await adapter.write_file("clip.mp4", BytesIO(b"tiny"), content_type="video/mp4")

    assert called == ["PutObject"]


async def test_write_file_sends_a_large_file_in_parts(adapter: S3Adapter, stub: Stubber) -> None:
    called = _operations(adapter)
    stub.add_response("create_multipart_upload", {"UploadId": "upload-1"})
    for number in range(3):
        stub.add_response("upload_part", {"ETag": f'"etag-{number}"'})
    stub.add_response("complete_multipart_upload", {})

    await adapter.write_file("clip.mp4", BytesIO(b"v" * 17 * 1024 * 1024), content_type="video/mp4")

    assert called == ["CreateMultipartUpload", "UploadPart", "UploadPart", "UploadPart", "CompleteMultipartUpload"]


async def test_a_missing_key_reads_as_file_not_found(adapter: S3Adapter, stub: Stubber) -> None:
    stub.add_client_error("get_object", service_error_code="NoSuchKey", http_status_code=404)
    stub.add_client_error("head_object", service_error_code="404", http_status_code=404)
    stub.add_client_error("get_object", service_error_code="NoSuchKey", http_status_code=404)

    with pytest.raises(FileNotFoundError):
        await adapter.read("gone.txt")

    with pytest.raises(FileNotFoundError):
        await adapter.file_size("gone.txt")

    with pytest.raises(FileNotFoundError):
        await adapter.open_stream("gone.txt")


async def test_open_stream_reads_the_size_and_the_content_in_one_request(adapter: S3Adapter, stub: Stubber) -> None:
    called = _operations(adapter)
    stub.add_response(
        "get_object",
        {"Body": _body(b"hello world"), "ContentLength": 11},
        {"Bucket": "my-bucket", "Key": "data/notes.txt"},
    )

    size, chunks = await adapter.open_stream("notes.txt", chunk_size=6)

    assert size == 11
    assert [chunk async for chunk in chunks] == [b"hello ", b"world"]
    assert called == ["GetObject"]


async def test_open_range_reads_the_served_range_and_the_total_in_one_request(
    adapter: S3Adapter, stub: Stubber
) -> None:
    called = _operations(adapter)
    stub.add_response(
        "get_object",
        {"Body": _body(b"56789"), "ContentRange": "bytes 5-9/10"},
        {"Bucket": "my-bucket", "Key": "data/notes.txt", "Range": "bytes=5-"},
    )

    opened = await adapter.open_range("notes.txt", 5, None)

    assert opened is not None
    start, end, total, chunks = opened
    assert (start, end, total) == (5, 9, 10)
    assert [chunk async for chunk in chunks] == [b"56789"]
    assert called == ["GetObject"]


async def test_open_range_past_the_end_opens_nothing(adapter: S3Adapter, stub: Stubber) -> None:
    stub.add_client_error("get_object", service_error_code="InvalidRange", http_status_code=416)

    assert await adapter.open_range("notes.txt", 50, None) is None
    assert await adapter.open_range("notes.txt", 5, 2) is None


async def test_every_write_carries_the_storage_class() -> None:
    adapter = S3Adapter(
        bucket="my-bucket",
        region="gra",
        access_key_id="key",
        secret_access_key="secret",
        storage_class="EXPRESS_ONEZONE",
    )
    sent: list[dict] = []
    adapter._client().meta.events.register(
        "before-parameter-build.s3.PutObject", lambda params, **kwargs: sent.append(dict(params))
    )

    with Stubber(adapter._client()) as stub:
        stub.add_response("put_object", {})
        stub.add_response("put_object", {})

        await adapter.write("a.txt", b"x")
        await adapter.write_file("b.mp4", BytesIO(b"tiny"), content_type="video/mp4")

    assert [params["StorageClass"] for params in sent] == ["EXPRESS_ONEZONE", "EXPRESS_ONEZONE"]


async def test_set_storage_class_copies_in_place_what_is_not_there_yet(adapter: S3Adapter, stub: Stubber) -> None:
    stub.add_response(
        "list_objects_v2",
        {
            "Contents": [
                {"Key": "data/a.jpg", "StorageClass": "STANDARD", "Size": 10},
                {"Key": "data/b.jpg", "StorageClass": "EXPRESS_ONEZONE", "Size": 20},
                {"Key": "data/huge.mov", "StorageClass": "STANDARD", "Size": 6 * 1024**3},
            ]
        },
        {"Bucket": "my-bucket", "Prefix": "data/"},
    )
    stub.add_response(
        "copy_object",
        {},
        {
            "Bucket": "my-bucket",
            "Key": "data/a.jpg",
            "CopySource": {"Bucket": "my-bucket", "Key": "data/a.jpg"},
            "StorageClass": "EXPRESS_ONEZONE",
            "MetadataDirective": "COPY",
        },
    )

    assert await adapter.set_storage_class("EXPRESS_ONEZONE", workers=1) == (1, 10, 1)


async def test_set_storage_class_dry_run_copies_nothing(adapter: S3Adapter, stub: Stubber) -> None:
    stub.add_response(
        "list_objects_v2",
        {"Contents": [{"Key": "data/a.jpg", "StorageClass": "STANDARD", "Size": 10}]},
        {"Bucket": "my-bucket", "Prefix": "data/"},
    )

    assert await adapter.set_storage_class("EXPRESS_ONEZONE", dry_run=True) == (1, 10, 0)
