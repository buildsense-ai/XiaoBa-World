from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import settings
from .db import init_mysql, mysql_connection
from .storage import storage

CASE_STATES = ["new", "inspecting", "fixing", "reviewing", "closed", "reopened", "blocked"]
OWNER_OPTIONS = ["inspector", "engineer", "reviewer"]
STATE_OWNERS = {
    "new": "inspector",
    "inspecting": "inspector",
    "fixing": "engineer",
    "reviewing": "reviewer",
    "closed": "reviewer",
    "reopened": "engineer",
    "blocked": "inspector",
}

ALLOWED_TRANSITIONS = {
    "new": {"inspecting"},
    "inspecting": {"fixing", "blocked"},
    "fixing": {"reviewing", "blocked"},
    "reviewing": {"closed", "reopened"},
    "reopened": {"fixing"},
    "blocked": {"inspecting", "fixing"},
    "closed": set(),
}

STAGE_META = {
    "input": {
        "label": "Input",
        "summary": "原始 log、jsonl 和外部附件。",
    },
    "analysis": {
        "label": "Analysis",
        "summary": "Inspector 的评估、证据归纳和问题定性。",
    },
    "execution": {
        "label": "Execution",
        "summary": "Engineer 的修复文档、patch 或 skill 变更。",
    },
    "verification": {
        "label": "Verification",
        "summary": "Reviewer 的复核、回归结果和风险判断。",
    },
    "closure": {
        "label": "Closure",
        "summary": "最终 closure note 和交付结论。",
    },
}
STAGE_ORDER = list(STAGE_META.keys())

TEXT_EXTENSIONS = {
    ".json",
    ".jsonl",
    ".log",
    ".md",
    ".markdown",
    ".patch",
    ".diff",
    ".txt",
    ".yaml",
    ".yml",
    ".sql",
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".sh",
}
TEXT_FORMATS = {
    "json",
    "jsonl",
    "log",
    "markdown",
    "md",
    "patch",
    "diff",
    "text",
    "txt",
    "yaml",
    "yml",
}
TEXT_MIME_TYPES = {
    "application/json",
    "application/x-ndjson",
}
PREVIEW_BYTE_LIMIT = 12 * 1024


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def make_id(prefix: str) -> str:
    return f"{prefix}-{datetime.now(timezone.utc):%Y%m%d%H%M%S}-{uuid.uuid4().hex[:6]}"


def json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def json_loads(value: str | None, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback


class AutoDevService:
    def bootstrap(self) -> None:
        init_mysql()
        storage.ensure_bucket()

    def list_cases(
        self,
        limit: int | None = None,
        status: str | None = None,
        owner: str | None = None,
        category: str | None = None,
        search: str | None = None,
    ) -> list[dict[str, Any]]:
        page_size = limit or settings.page_size
        clauses: list[str] = []
        params: list[Any] = []

        if status:
            clauses.append("status = %s")
            params.append(status)
        if owner:
            clauses.append("current_owner_agent = %s")
            params.append(owner)
        if category:
            clauses.append("category = %s")
            params.append(category)
        if search:
            like = f"%{search}%"
            clauses.append(
                "("
                "case_id LIKE %s OR title LIKE %s OR COALESCE(summary, '') LIKE %s OR "
                "COALESCE(source_session_id, '') LIKE %s OR COALESCE(source_user_id, '') LIKE %s"
                ")"
            )
            params.extend([like, like, like, like, like])

        query = "SELECT * FROM cases"
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY updated_at DESC LIMIT %s"
        params.append(page_size)

        with mysql_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, tuple(params))
                rows = cursor.fetchall()
        return [self._hydrate_case(row) for row in rows]

    def get_case_detail(self, case_id: str) -> dict[str, Any] | None:
        with mysql_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT * FROM cases WHERE case_id = %s", (case_id,))
                case_row = cursor.fetchone()
                if not case_row:
                    return None

                cursor.execute("SELECT * FROM artifacts WHERE case_id = %s ORDER BY created_at ASC", (case_id,))
                artifact_rows = cursor.fetchall()

                cursor.execute("SELECT * FROM events WHERE case_id = %s ORDER BY created_at ASC", (case_id,))
                event_rows = cursor.fetchall()

        artifacts = [self._enrich_artifact(self._hydrate_artifact(row)) for row in artifact_rows]
        events = [self._hydrate_event(row) for row in event_rows]
        chain = self._build_chain(artifacts)
        return {
            "case": self._hydrate_case(case_row),
            "artifacts": artifacts,
            "events": events,
            "chain": chain,
            "highlights": self._build_case_highlights(artifacts),
            "metrics": {
                "artifact_count": len(artifacts),
                "event_count": len(events),
                "completed_stages": sum(1 for stage in chain if stage["has_items"]),
                "latest_artifact": artifacts[-1] if artifacts else None,
                "latest_event": events[-1] if events else None,
                "loop": self._extract_latest_structured_artifact_payload(artifacts, "metrics"),
                "writeback": self._extract_latest_structured_artifact_payload(artifacts, "writeback_result"),
            },
        }

    def get_artifact(self, artifact_id: str) -> dict[str, Any] | None:
        with mysql_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT * FROM artifacts WHERE artifact_id = %s", (artifact_id,))
                row = cursor.fetchone()
        return self._hydrate_artifact(row) if row else None

    def create_case(self, payload: dict[str, Any]) -> dict[str, Any]:
        case_id = make_id("case")
        now = utcnow()
        workdir = settings.workdir_root / case_id
        workdir.mkdir(parents=True, exist_ok=True)

        record = {
            "case_id": case_id,
            "title": payload["title"],
            "status": "new",
            "category": payload.get("category"),
            "source": payload.get("source") or "xiaoba_runtime",
            "source_session_id": payload.get("source_session_id"),
            "source_user_id": payload.get("source_user_id"),
            "priority": payload.get("priority") or "normal",
            "summary": payload.get("summary"),
            "current_owner_agent": STATE_OWNERS["new"],
            "recommended_next_action": payload.get("recommended_next_action"),
            "labels_json": json_dumps(payload.get("labels") or []),
            "workdir_path": str(workdir),
            "created_at": now,
            "updated_at": now,
        }

        with mysql_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO cases (
                        case_id, title, status, category, source, source_session_id, source_user_id,
                        priority, summary, current_owner_agent, recommended_next_action,
                        labels_json, workdir_path, created_at, updated_at
                    ) VALUES (
                        %(case_id)s, %(title)s, %(status)s, %(category)s, %(source)s, %(source_session_id)s, %(source_user_id)s,
                        %(priority)s, %(summary)s, %(current_owner_agent)s, %(recommended_next_action)s,
                        %(labels_json)s, %(workdir_path)s, %(created_at)s, %(updated_at)s
                    )
                    """,
                    record,
                )
                self._insert_event(
                    cursor,
                    case_id=case_id,
                    kind="case_created",
                    actor_type="system",
                    actor_id="platform",
                    payload={"status": "new"},
                    created_at=now,
                )
            connection.commit()

        detail = self.get_case_detail(case_id)
        if not detail:
            raise RuntimeError("Failed to reload created case")
        return detail["case"]

    def append_event(self, case_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        now = utcnow()
        event_id = make_id("evt")

        with mysql_connection() as connection:
            with connection.cursor() as cursor:
                self._require_case(cursor, case_id)
                cursor.execute(
                    """
                    INSERT INTO events (event_id, case_id, kind, actor_type, actor_id, payload_json, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        event_id,
                        case_id,
                        payload["kind"],
                        payload.get("actor_type") or "agent",
                        payload["actor_id"],
                        json_dumps(payload.get("payload") or {}),
                        now,
                    ),
                )
                cursor.execute("UPDATE cases SET updated_at = %s WHERE case_id = %s", (now, case_id))
            connection.commit()

        detail = self.get_case_detail(case_id)
        if not detail:
            raise RuntimeError("Failed to reload case after adding event")
        return detail["events"][-1]

    def update_state(self, case_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        now = utcnow()
        with mysql_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT * FROM cases WHERE case_id = %s", (case_id,))
                current = cursor.fetchone()
                if not current:
                    raise ValueError(f"Case not found: {case_id}")

                current_status = current["status"]
                requested_from = payload["from_state"]
                target_status = payload["to"]
                if requested_from != current_status:
                    raise ValueError(f"Case {case_id} is in state {current_status}, not {requested_from}")
                if target_status not in ALLOWED_TRANSITIONS.get(current_status, set()):
                    raise ValueError(f"Illegal transition: {current_status} -> {target_status}")

                cursor.execute(
                    """
                    UPDATE cases
                    SET status = %s,
                        category = %s,
                        current_owner_agent = %s,
                        recommended_next_action = %s,
                        updated_at = %s
                    WHERE case_id = %s
                    """,
                    (
                        target_status,
                        payload.get("category") or current.get("category"),
                        STATE_OWNERS.get(target_status, current.get("current_owner_agent")),
                        payload.get("recommended_next_action")
                        if payload.get("recommended_next_action") is not None
                        else current.get("recommended_next_action"),
                        now,
                        case_id,
                    ),
                )
                self._insert_event(
                    cursor,
                    case_id=case_id,
                    kind="state_changed",
                    actor_type="agent",
                    actor_id=payload["actor_id"],
                    payload={
                        "from": current_status,
                        "source_status": current_status,
                        "to": target_status,
                        "target_status": target_status,
                        "reason": payload.get("reason") or "",
                    },
                    created_at=now,
                )
            connection.commit()

        detail = self.get_case_detail(case_id)
        if not detail:
            raise RuntimeError("Failed to reload case after state update")
        return detail["case"]

    def record_artifact(self, case_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        now = utcnow()
        artifact_id = payload.get("artifact_id") or make_id("art")

        with mysql_connection() as connection:
            with connection.cursor() as cursor:
                case_row = self._require_case(cursor, case_id)
                version = self._next_artifact_version(cursor, case_id, payload["type"])
                cursor.execute(
                    """
                    INSERT INTO artifacts (
                        artifact_id, case_id, type, stage, title, format, storage_mode, storage_path,
                        local_path, bucket_name, object_key, original_filename, size_bytes,
                        content_type, produced_by_agent, version, metadata_json, created_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        artifact_id,
                        case_id,
                        payload["type"],
                        payload["stage"],
                        payload["title"],
                        payload.get("format") or "binary",
                        payload.get("storage_mode") or "external",
                        payload.get("storage_path"),
                        payload.get("local_path"),
                        payload.get("bucket_name"),
                        payload.get("object_key"),
                        payload.get("original_filename"),
                        payload.get("size_bytes"),
                        payload.get("content_type"),
                        payload.get("produced_by_agent") or "system",
                        version,
                        json_dumps(payload.get("metadata") or {}),
                        now,
                    ),
                )
                self._insert_event(
                    cursor,
                    case_id=case_id,
                    kind="artifact_created",
                    actor_type="agent",
                    actor_id=payload.get("produced_by_agent") or "system",
                    payload={"artifact_id": artifact_id, "type": payload["type"]},
                    created_at=now,
                )
                cursor.execute("UPDATE cases SET updated_at = %s WHERE case_id = %s", (now, case_id))

                if payload.get("local_path"):
                    Path(case_row["workdir_path"]).mkdir(parents=True, exist_ok=True)
            connection.commit()

        artifact = self.get_artifact(artifact_id)
        if not artifact:
            raise RuntimeError("Failed to reload artifact after insert")
        return artifact

    def upload_artifact(
        self,
        case_id: str,
        artifact_type: str,
        stage: str,
        title: str,
        produced_by_agent: str,
        filename: str,
        content_type: str | None,
        data: bytes,
        artifact_format: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        artifact_id = make_id("art")
        safe_name = Path(filename).name.replace(" ", "_")
        local_dir = settings.workdir_root / case_id / "artifacts"
        local_dir.mkdir(parents=True, exist_ok=True)
        local_path = local_dir / safe_name
        local_path.write_bytes(data)

        stored = storage.put_object(case_id, artifact_id, safe_name, data, content_type)
        return self.record_artifact(
            case_id,
            {
                "artifact_id": artifact_id,
                "type": artifact_type,
                "stage": stage,
                "title": title,
                "format": artifact_format,
                "storage_mode": "minio",
                "storage_path": f"minio://{stored.bucket_name}/{stored.object_key}",
                "local_path": str(local_path),
                "bucket_name": stored.bucket_name,
                "object_key": stored.object_key,
                "original_filename": safe_name,
                "size_bytes": stored.size_bytes,
                "content_type": content_type,
                "produced_by_agent": produced_by_agent,
                "metadata": metadata or {},
            },
        )

    def read_artifact_bytes(self, artifact_id: str) -> tuple[dict[str, Any], bytes]:
        artifact = self.get_artifact(artifact_id)
        if not artifact:
            raise ValueError(f"Artifact not found: {artifact_id}")

        local_path = artifact.get("local_path")
        if local_path and Path(local_path).exists():
            return artifact, Path(local_path).read_bytes()

        bucket_name = artifact.get("bucket_name")
        object_key = artifact.get("object_key")
        if bucket_name and object_key:
            return artifact, storage.download_object(bucket_name, object_key)

        raise FileNotFoundError(f"Artifact {artifact_id} has no readable body")

    def get_session_log(self, log_id: str) -> dict[str, Any] | None:
        with mysql_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM session_logs WHERE log_id = %s", (log_id,))
                row = cur.fetchone()
        return self._hydrate_session_log(row) if row else None

    def read_session_log_bytes(self, log_id: str) -> tuple[dict[str, Any], bytes]:
        log_item = self.get_session_log(log_id)
        if not log_item:
            raise ValueError(f"Session log not found: {log_id}")

        bucket_name = log_item.get("bucket_name")
        object_key = log_item.get("object_key")
        if bucket_name and object_key:
            return log_item, storage.download_object(bucket_name, object_key)

        raise FileNotFoundError(f"Session log {log_id} has no readable body")

    def list_pending_logs(self, agent: str, limit: int = 20) -> list[dict[str, Any]]:
        with mysql_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT l.*
                    FROM session_logs l
                    LEFT JOIN (
                        SELECT DISTINCT log_id
                        FROM log_events
                        WHERE agent = %s AND kind IN ('inspector_review_completed', 'inspector_review_failed')
                    ) processed ON processed.log_id = l.log_id
                    WHERE processed.log_id IS NULL
                    ORDER BY l.uploaded_at DESC
                    LIMIT %s
                    """,
                    (agent, limit),
                )
                rows = cur.fetchall()
        return [self._hydrate_session_log(row) for row in (rows or [])]

    def append_log_event(self, log_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        now = utcnow()
        event_id = make_id("lge")

        with mysql_connection() as conn:
            with conn.cursor() as cur:
                self._require_session_log(cur, log_id)
                cur.execute(
                    """
                    INSERT INTO log_events (event_id, log_id, agent, kind, payload_json, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (
                        event_id,
                        log_id,
                        payload["agent"],
                        payload["kind"],
                        json_dumps(payload.get("payload") or {}),
                        now,
                    ),
                )
            conn.commit()

        return {
            "event_id": event_id,
            "log_id": log_id,
            "agent": payload["agent"],
            "kind": payload["kind"],
            "payload": payload.get("payload") or {},
            "created_at": now.isoformat(),
        }

    def append_log_card(self, log_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        now = utcnow()
        card_id = make_id("lgc")

        with mysql_connection() as conn:
            with conn.cursor() as cur:
                self._require_session_log(cur, log_id)
                cur.execute(
                    """
                    INSERT INTO log_cards (
                        card_id, log_id, agent, card_type, title, summary, severity, status, payload_json, created_at, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        card_id,
                        log_id,
                        payload["agent"],
                        payload["card_type"],
                        payload["title"],
                        payload.get("summary"),
                        payload.get("severity"),
                        payload.get("status") or "open",
                        json_dumps(payload.get("payload") or {}),
                        now,
                        now,
                    ),
                )
            conn.commit()

        return self.get_log_card(card_id) or {
            "card_id": card_id,
            "log_id": log_id,
            "agent": payload["agent"],
            "card_type": payload["card_type"],
            "title": payload["title"],
            "summary": payload.get("summary"),
            "severity": payload.get("severity"),
            "status": payload.get("status") or "open",
            "payload": payload.get("payload") or {},
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }

    def get_session_log_detail(self, log_id: str) -> dict[str, Any] | None:
        try:
            log_item, data = self.read_session_log_bytes(log_id)
        except ValueError:
            return None

        preview_bytes = data[:PREVIEW_BYTE_LIMIT]
        preview_text = preview_bytes.decode("utf-8", errors="replace").replace("\x00", "").strip() or None
        analysis = self._analyze_session_log_entries(data)
        events = self.list_log_events(log_id)
        cards = self.list_log_cards(log_id)
        related_logs = self.list_logs(
            session_type=log_item.get("session_type"),
            session_id=log_item.get("session_id"),
            limit=12,
        )
        related_logs = [item for item in related_logs if item.get("log_id") != log_id][:6]
        return {
            "log": log_item,
            "preview_text": preview_text,
            "preview_truncated": len(data) > PREVIEW_BYTE_LIMIT,
            "analysis": analysis,
            "events": events,
            "cards": cards,
            "related_logs": related_logs,
            "agent_cards": self._build_agent_card_summary(cards),
        }

    def _require_case(self, cursor: Any, case_id: str) -> dict[str, Any]:
        cursor.execute("SELECT * FROM cases WHERE case_id = %s", (case_id,))
        case_row = cursor.fetchone()
        if not case_row:
            raise ValueError(f"Case not found: {case_id}")
        return case_row

    def _require_session_log(self, cursor: Any, log_id: str) -> dict[str, Any]:
        cursor.execute("SELECT * FROM session_logs WHERE log_id = %s", (log_id,))
        row = cursor.fetchone()
        if not row:
            raise ValueError(f"Session log not found: {log_id}")
        return row

    def _next_artifact_version(self, cursor: Any, case_id: str, artifact_type: str) -> int:
        cursor.execute(
            "SELECT COALESCE(MAX(version), 0) AS max_version FROM artifacts WHERE case_id = %s AND type = %s",
            (case_id, artifact_type),
        )
        row = cursor.fetchone() or {"max_version": 0}
        return int(row["max_version"] or 0) + 1

    def _insert_event(
        self,
        cursor: Any,
        case_id: str,
        kind: str,
        actor_type: str,
        actor_id: str,
        payload: dict[str, Any],
        created_at: datetime,
    ) -> None:
        cursor.execute(
            "INSERT INTO events (event_id, case_id, kind, actor_type, actor_id, payload_json, created_at) VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (make_id("evt"), case_id, kind, actor_type, actor_id, json_dumps(payload), created_at),
        )

    def _hydrate_case(self, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "case_id": row["case_id"],
            "title": row["title"],
            "status": row["status"],
            "category": row["category"],
            "source": row["source"],
            "source_session_id": row["source_session_id"],
            "source_user_id": row["source_user_id"],
            "priority": row["priority"],
            "summary": row["summary"],
            "current_owner_agent": row["current_owner_agent"],
            "recommended_next_action": row["recommended_next_action"],
            "labels": json_loads(row.get("labels_json"), []),
            "workdir_path": row["workdir_path"],
            "created_at": row["created_at"].isoformat() if row.get("created_at") else None,
            "updated_at": row["updated_at"].isoformat() if row.get("updated_at") else None,
        }

    def _hydrate_artifact(self, row: dict[str, Any]) -> dict[str, Any]:
        original_filename = row["original_filename"] or ""
        artifact_format = row["format"] or ""
        content_type = row["content_type"] or ""
        size_bytes = row["size_bytes"] or 0
        return {
            "artifact_id": row["artifact_id"],
            "case_id": row["case_id"],
            "type": row["type"],
            "stage": row["stage"],
            "title": row["title"],
            "format": artifact_format,
            "storage_mode": row["storage_mode"],
            "storage_path": row["storage_path"],
            "local_path": row["local_path"],
            "bucket_name": row["bucket_name"],
            "object_key": row["object_key"],
            "original_filename": original_filename,
            "size_bytes": size_bytes,
            "size_label": self._format_bytes(size_bytes),
            "content_type": content_type,
            "produced_by_agent": row["produced_by_agent"],
            "version": row["version"],
            "metadata": json_loads(row.get("metadata_json"), {}),
            "created_at": row["created_at"].isoformat() if row.get("created_at") else None,
            "is_previewable": self._is_previewable_artifact(original_filename, artifact_format, content_type),
            "download_url": f"/api/artifacts/{row['artifact_id']}/download",
        }

    def _hydrate_event(self, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "event_id": row["event_id"],
            "case_id": row["case_id"],
            "kind": row["kind"],
            "actor_type": row["actor_type"],
            "actor_id": row["actor_id"],
            "payload": json_loads(row.get("payload_json"), {}),
            "created_at": row["created_at"].isoformat() if row.get("created_at") else None,
        }

    def _build_chain(self, artifacts: list[dict[str, Any]]) -> list[dict[str, Any]]:
        grouped: dict[str, list[dict[str, Any]]] = {stage: [] for stage in STAGE_ORDER}
        extra_groups: dict[str, list[dict[str, Any]]] = {}

        for artifact in artifacts:
            stage = artifact.get("stage") or "input"
            if stage in grouped:
                grouped[stage].append(artifact)
            else:
                extra_groups.setdefault(stage, []).append(artifact)

        chain: list[dict[str, Any]] = []
        for index, stage in enumerate(STAGE_ORDER, start=1):
            items = sorted(
                grouped[stage],
                key=lambda item: (item.get("created_at") or "", int(item.get("version") or 0)),
                reverse=True,
            )
            meta = STAGE_META[stage]
            chain.append(
                {
                    "id": stage,
                    "sequence": index,
                    "label": meta["label"],
                    "summary": meta["summary"],
                    "artifact_count": len(items),
                    "has_items": bool(items),
                    "lead": items[0] if items else None,
                    "items": items,
                }
            )

        for offset, stage in enumerate(sorted(extra_groups), start=len(chain) + 1):
            items = sorted(
                extra_groups[stage],
                key=lambda item: (item.get("created_at") or "", int(item.get("version") or 0)),
                reverse=True,
            )
            chain.append(
                {
                    "id": stage,
                    "sequence": offset,
                    "label": stage.replace("_", " ").title(),
                    "summary": "Custom stage",
                    "artifact_count": len(items),
                    "has_items": bool(items),
                    "lead": items[0] if items else None,
                    "items": items,
                }
            )

        return chain

    def _build_case_highlights(self, artifacts: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "assessment": self._extract_latest_structured_artifact(artifacts, "assessment"),
            "implementation_summary": self._extract_latest_structured_artifact(artifacts, "implementation_summary"),
            "review_summary": self._extract_latest_structured_artifact(artifacts, "review_summary"),
            "metrics": self._extract_latest_structured_artifact(artifacts, "metrics"),
            "writeback_plan": self._extract_latest_structured_artifact(artifacts, "writeback_plan"),
            "writeback_result": self._extract_latest_structured_artifact(artifacts, "writeback_result"),
            "patch": self._extract_latest_structured_artifact(artifacts, "patch"),
            "closure_note": self._extract_latest_structured_artifact(artifacts, "closure_note"),
        }

    def _extract_latest_structured_artifact(
        self,
        artifacts: list[dict[str, Any]],
        artifact_type: str,
    ) -> dict[str, Any] | None:
        matches = [
            artifact for artifact in artifacts
            if str(artifact.get("type") or "").strip() == artifact_type
        ]
        if not matches:
            return None

        ordered = sorted(
            matches,
            key=lambda item: (item.get("created_at") or "", int(item.get("version") or 0)),
            reverse=True,
        )
        artifact = ordered[0]
        return {
            "artifact": artifact,
            "payload": self._parse_artifact_preview_payload(artifact),
        }

    def _extract_latest_structured_artifact_payload(
        self,
        artifacts: list[dict[str, Any]],
        artifact_type: str,
    ) -> dict[str, Any] | list[Any] | None:
        structured = self._extract_latest_structured_artifact(artifacts, artifact_type)
        if not structured:
            return None
        payload = structured.get("payload")
        if isinstance(payload, (dict, list)):
            return payload
        return None

    def _parse_artifact_preview_payload(self, artifact: dict[str, Any]) -> dict[str, Any] | list[Any] | None:
        preview_text = str(artifact.get("preview_text") or "").strip()
        if not preview_text:
            return None
        try:
            parsed = json.loads(preview_text)
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, (dict, list)) else None

    def _enrich_artifact(self, artifact: dict[str, Any]) -> dict[str, Any]:
        preview_text = None
        preview_truncated = False
        if artifact["is_previewable"]:
            try:
                preview_text, preview_truncated = self._read_preview(artifact["artifact_id"])
            except OSError:
                preview_text = None
                preview_truncated = False

        return {
            **artifact,
            "preview_text": preview_text,
            "preview_truncated": preview_truncated,
        }

    def _read_preview(self, artifact_id: str) -> tuple[str | None, bool]:
        _, data = self.read_artifact_bytes(artifact_id)
        preview_bytes = data[:PREVIEW_BYTE_LIMIT]
        text = preview_bytes.decode("utf-8", errors="replace").replace("\x00", "")
        return text.strip() or None, len(data) > PREVIEW_BYTE_LIMIT

    def _is_previewable_artifact(self, filename: str, artifact_format: str, content_type: str) -> bool:
        suffix = Path(filename).suffix.lower()
        normalized_format = artifact_format.strip().lower()
        normalized_content_type = content_type.strip().lower()

        if suffix in TEXT_EXTENSIONS:
            return True
        if normalized_format in TEXT_FORMATS:
            return True
        if normalized_content_type.startswith("text/"):
            return True
        if normalized_content_type in TEXT_MIME_TYPES:
            return True
        return False

    def _format_bytes(self, size_bytes: int | None) -> str:
        value = float(size_bytes or 0)
        units = ["B", "KB", "MB", "GB"]
        for unit in units:
            if value < 1024 or unit == units[-1]:
                if unit == "B":
                    return f"{int(value)} {unit}"
                return f"{value:.1f} {unit}"
            value /= 1024
        return f"{int(size_bytes or 0)} B"

    def _analyze_session_log_entries(self, data: bytes) -> dict[str, Any]:
        total_entries = 0
        runtime_entries = 0
        turn_entries = 0
        parse_errors = 0
        first_timestamp = None
        last_timestamp = None

        for raw_line in data.decode("utf-8", errors="replace").splitlines():
            line = raw_line.strip()
            if not line:
                continue
            total_entries += 1
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                parse_errors += 1
                continue

            entry_type = str(payload.get("entry_type") or "").strip().lower()
            if entry_type == "runtime":
                runtime_entries += 1
            elif entry_type == "turn":
                turn_entries += 1

            timestamp = payload.get("timestamp") or payload.get("created_at") or payload.get("time")
            if timestamp:
                if not first_timestamp:
                    first_timestamp = timestamp
                last_timestamp = timestamp

        return {
            "total_entries": total_entries,
            "runtime_entries": runtime_entries,
            "turn_entries": turn_entries,
            "parse_errors": parse_errors,
            "first_timestamp": first_timestamp,
            "last_timestamp": last_timestamp,
        }

    def ingest_log(
        self,
        session_type: str,
        session_id: str,
        log_date: str,
        filename: str,
        data: bytes,
        content_type: str | None = None,
    ) -> dict[str, Any]:
        log_id = make_id("log")
        uploaded_at = datetime.now(timezone.utc)
        stored = storage.put_log_object(
            session_type=session_type,
            log_date=log_date,
            session_id=session_id,
            log_id=log_id,
            filename=filename,
            data=data,
            content_type=content_type or "application/x-ndjson",
        )
        with mysql_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO session_logs
                        (log_id, session_type, session_id, log_date, filename, size_bytes, bucket_name, object_key, uploaded_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                        size_bytes = VALUES(size_bytes),
                        bucket_name = VALUES(bucket_name),
                        object_key = VALUES(object_key),
                        uploaded_at = VALUES(uploaded_at)
                    """,
                    (log_id, session_type, session_id, log_date, filename,
                     stored.size_bytes, stored.bucket_name, stored.object_key,
                     uploaded_at),
                )
            conn.commit()
        return {"log_id": log_id, "session_type": session_type, "session_id": session_id, "log_date": log_date, "size_bytes": stored.size_bytes}

    def list_logs(
        self,
        session_type: str | None = None,
        session_id: str | None = None,
        log_date: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        clauses = []
        params: list[Any] = []
        if session_type:
            clauses.append("session_type = %s")
            params.append(session_type)
        if session_id:
            clauses.append("session_id = %s")
            params.append(session_id)
        if log_date:
            clauses.append("log_date = %s")
            params.append(log_date)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        params.append(limit)
        with mysql_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"SELECT * FROM session_logs {where} ORDER BY uploaded_at DESC LIMIT %s",
                    params,
                )
                rows = cur.fetchall()
        return [self._hydrate_session_log(row) for row in (rows or [])]

    def get_log_card(self, card_id: str) -> dict[str, Any] | None:
        with mysql_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM log_cards WHERE card_id = %s", (card_id,))
                row = cur.fetchone()
        return self._hydrate_log_card(row) if row else None

    def list_log_cards(self, log_id: str) -> list[dict[str, Any]]:
        with mysql_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM log_cards WHERE log_id = %s ORDER BY created_at DESC", (log_id,))
                rows = cur.fetchall()
        return [self._hydrate_log_card(row) for row in (rows or [])]

    def list_log_events(self, log_id: str) -> list[dict[str, Any]]:
        with mysql_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM log_events WHERE log_id = %s ORDER BY created_at ASC", (log_id,))
                rows = cur.fetchall()
        return [self._hydrate_log_event(row) for row in (rows or [])]

    def _hydrate_session_log(self, row: dict[str, Any]) -> dict[str, Any]:
        log_date = row["log_date"].isoformat() if hasattr(row["log_date"], "isoformat") else str(row["log_date"])
        uploaded_at = row["uploaded_at"].isoformat() if row.get("uploaded_at") else None
        bucket_name = row.get("bucket_name")
        object_key = row.get("object_key")
        storage_path = f"minio://{bucket_name}/{object_key}" if bucket_name and object_key else None
        return {
            "log_id": row["log_id"],
            "session_type": row["session_type"],
            "session_id": row["session_id"],
            "log_date": log_date,
            "filename": row["filename"],
            "size_bytes": row["size_bytes"],
            "size_label": self._format_bytes(row["size_bytes"]),
            "bucket_name": bucket_name,
            "object_key": object_key,
            "storage_path": storage_path,
            "uploaded_at": uploaded_at,
            "download_url": f"/api/logs/{row['log_id']}/download",
        }

    def _hydrate_log_card(self, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "card_id": row["card_id"],
            "log_id": row["log_id"],
            "agent": row["agent"],
            "card_type": row["card_type"],
            "title": row["title"],
            "summary": row.get("summary"),
            "severity": row.get("severity"),
            "status": row.get("status"),
            "payload": json_loads(row.get("payload_json"), {}),
            "created_at": row["created_at"].isoformat() if row.get("created_at") else None,
            "updated_at": row["updated_at"].isoformat() if row.get("updated_at") else None,
        }

    def _hydrate_log_event(self, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "event_id": row["event_id"],
            "log_id": row["log_id"],
            "agent": row["agent"],
            "kind": row["kind"],
            "payload": json_loads(row.get("payload_json"), {}),
            "created_at": row["created_at"].isoformat() if row.get("created_at") else None,
        }

    def _build_agent_card_summary(self, cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
        defaults = {
            "inspector": "基于这条 session log 生成问题识别、证据抽取和定性卡片。",
            "engineer": "围绕同一条 session log 追加修复建议、实现记录和验证待办。",
            "reviewer": "对修复结果和回归风险做复核，沉淀最终结论卡片。",
        }
        grouped: dict[str, list[dict[str, Any]]] = {}
        for card in cards:
            grouped.setdefault(card["agent"], []).append(card)

        items: list[dict[str, Any]] = []
        for agent in ["inspector", "engineer", "reviewer"]:
            agent_cards = grouped.get(agent, [])
            items.append({
                "agent": agent,
                "title": f"{agent.title()} Cards",
                "summary": defaults[agent],
                "items": agent_cards,
            })
        for agent in sorted(grouped):
            if agent in defaults:
                continue
            items.append({
                "agent": agent,
                "title": f"{agent.title()} Cards",
                "summary": "Custom agent output cards.",
                "items": grouped[agent],
            })
        return items


service = AutoDevService()
