# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import builtins

import pytest

from fastedgy.storage.adapters.s3 import S3Adapter


def test_s3_adapter_requires_aioboto3(monkeypatch: pytest.MonkeyPatch) -> None:
    real_import = builtins.__import__

    def fake_import(name: str, *args, **kwargs):
        if name == "aioboto3":
            raise ImportError("aioboto3 is not installed")

        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    adapter = S3Adapter(bucket="my-bucket")

    with pytest.raises(ImportError, match=r"fastedgy\[s3\]"):
        adapter._get_session()
