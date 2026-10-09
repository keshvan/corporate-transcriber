from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from app.config import Settings

_NOT_FOUND_CODES = {"404", "NoSuchKey", "NotFound"}

class StorageError(Exception):
    pass

class ObjectNotFoundError(StorageError):
    pass

@contextmanager
def _translate(what: str) -> Iterator[None]:
    try:
        yield
    except ClientError as e:
        code = str(e.response.get("Error", {}).get("Code", ""))
        if code in _NOT_FOUND_CODES:
            raise ObjectNotFoundError(what) from e
        raise StorageError(f"{code or 'client error'}: {what}") from e
    except BotoCoreError as e:
        raise StorageError(f"{type(e).__name__}: {what}") from e

class S3Storage:
    def __init__(self, client: Any, bucket: str) -> None:
        self._s3 = client
        self._bucket = bucket

    @classmethod
    def from_settings(cls, s: Settings) -> S3Storage:
        client = boto3.client(
            "s3",
            endpoint_url=s.s3_endpoint,
            aws_access_key_id=s.s3_access_key,
            aws_secret_access_key=s.s3_secret_key.get_secret_value(),
            config=Config(
                signature_version="s3v4",
                s3={"addresing_style": "path"},
                retries={"max_attempts": 5, "mode": "standard"},
                connect_timeout=5,
                read_timeout=60,
            ),
        )
        return cls(client, s.s3_bucket)

    def uri(self, key: str) -> str:
        return f"s3://{self._bucket}/{key}"

    def _key_from_uri(self, uri: str) -> str:
        prefix = f"s3://{self._bucket}/"
        if not uri.startswith(prefix) or len(uri) == len(prefix):
            raise StorageError(f"invalid or foreign uri: {uri!r}")
        return uri[len(prefix):]

    def download_file(self, uri: str, dest: Path) -> Path:
        key = self._key_from_uri(uri)
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_name(dest.name + ".part")
        self._s3.download_file(self._bucket, key, str(tmp))
        tmp.replace(dest)
        return dest

    def exists(self, uri: str) -> bool:
        key = self._key_from_uri(uri)
        try:
            with _translate(uri):
                self._s3.head_object(Bucket=self._bucket, Key=key)
        except ObjectNotFoundError:
            return False
        return True

    def upload_file(self, src: Path, key: str, content_type: str | None = None) -> str:
        extra = {"ContentType": content_type} if content_type else None
        with _translate(key):
            self._s3.upload_file(str(src), self._bucket, key, ExtraArgs=extra)
        return self.uri(key)
