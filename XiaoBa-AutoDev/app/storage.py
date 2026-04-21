from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO

from minio import Minio

from .config import settings


@dataclass(slots=True)
class StoredArtifact:
    bucket_name: str
    object_key: str
    size_bytes: int
    content_type: str | None


class ArtifactStorage:
    def __init__(self) -> None:
        endpoint = settings.minio_endpoint.replace("https://", "").replace("http://", "")
        secure = settings.minio_secure or settings.minio_endpoint.startswith("https://")
        self.client = Minio(
            endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=secure,
            region=settings.minio_region,
        )

    def ensure_bucket(self) -> None:
        if not self.client.bucket_exists(settings.minio_bucket):
            self.client.make_bucket(settings.minio_bucket, location=settings.minio_region)

    def put_object(
        self,
        case_id: str,
        artifact_id: str,
        filename: str,
        data: bytes,
        content_type: str | None,
    ) -> StoredArtifact:
        object_key = self.build_object_key(case_id, artifact_id, filename)
        self.client.put_object(
            settings.minio_bucket,
            object_key,
            data=BytesIO(data),
            length=len(data),
            content_type=content_type or "application/octet-stream",
        )
        return StoredArtifact(
            bucket_name=settings.minio_bucket,
            object_key=object_key,
            size_bytes=len(data),
            content_type=content_type,
        )

    def put_log_object(
        self,
        session_type: str,
        log_date: str,
        session_id: str,
        log_id: str,
        filename: str,
        data: bytes,
        content_type: str | None,
    ) -> StoredArtifact:
        object_key = self.build_log_object_key(session_type, log_date, session_id, log_id, filename)
        self.client.put_object(
            settings.minio_bucket,
            object_key,
            data=BytesIO(data),
            length=len(data),
            content_type=content_type or "application/octet-stream",
        )
        return StoredArtifact(
            bucket_name=settings.minio_bucket,
            object_key=object_key,
            size_bytes=len(data),
            content_type=content_type,
        )

    def download_object(self, bucket_name: str, object_key: str) -> bytes:
        response = self.client.get_object(bucket_name, object_key)
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()

    def build_object_key(self, case_id: str, artifact_id: str, filename: str) -> str:
        safe_name = self._sanitize_segment(filename)
        return f"{settings.artifact_prefix}/{case_id}/{artifact_id}/{safe_name}"

    def build_log_object_key(
        self,
        session_type: str,
        log_date: str,
        session_id: str,
        log_id: str,
        filename: str,
    ) -> str:
        safe_type = self._sanitize_segment(session_type or "unknown")
        safe_date = self._sanitize_segment(log_date or "unknown-date")
        safe_session_id = self._sanitize_segment(session_id or "unknown-session")
        safe_log_id = self._sanitize_segment(log_id)
        safe_name = self._sanitize_segment(filename)
        return f"{settings.log_prefix}/{safe_type}/{safe_date}/{safe_session_id}/{safe_log_id}/{safe_name}"

    def _sanitize_segment(self, value: str) -> str:
        return (
            value.replace("\\", "_")
            .replace("/", "_")
            .replace(" ", "_")
            .replace(":", "_")
        )


storage = ArtifactStorage()
