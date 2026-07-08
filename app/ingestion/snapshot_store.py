"""Local filesystem snapshot store for dev/test. R2 for production."""

import hashlib
import json
from abc import ABC, abstractmethod
from pathlib import Path

import boto3
from botocore.client import BaseClient

from app.config import get_settings


class SnapshotStore(ABC):
    @abstractmethod
    async def write(self, source: str, url: str, payload: bytes) -> tuple[str, str]:
        """Returns (content_hash, storage_key)."""


class LocalSnapshotStore(SnapshotStore):
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    async def write(self, source: str, url: str, payload: bytes) -> tuple[str, str]:
        content_hash = hashlib.sha256(payload).hexdigest()
        key = f"{source}/{content_hash[:16]}.json"
        path = self.root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        return content_hash, key


class R2SnapshotStore(SnapshotStore):
    def __init__(self, client: BaseClient, bucket: str) -> None:
        self.client = client
        self.bucket = bucket

    async def write(self, source: str, url: str, payload: bytes) -> tuple[str, str]:
        content_hash = hashlib.sha256(payload).hexdigest()
        key = f"{source}/{content_hash[:16]}.json"
        self.client.put_object(Bucket=self.bucket, Key=key, Body=payload)
        return content_hash, key


def get_snapshot_store() -> SnapshotStore:
    settings = get_settings()
    if settings.snapshot_store_backend == "r2":
        client = boto3.client(
            "s3",
            endpoint_url=settings.r2_endpoint,
            aws_access_key_id=settings.r2_access_key_id,
            aws_secret_access_key=settings.r2_secret_access_key,
        )
        return R2SnapshotStore(client, settings.r2_bucket)
    return LocalSnapshotStore(Path(settings.local_snapshot_dir))


def snapshot_payload(record: dict) -> bytes:
    return json.dumps(record, default=str).encode()
