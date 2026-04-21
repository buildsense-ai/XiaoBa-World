from __future__ import annotations

import json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.datastructures import UploadFile as StarletteUploadFile

from .config import ROOT_DIR, settings
from .schemas import CaseCreateRequest, EventCreateRequest, LogCardCreateRequest, LogEventCreateRequest, StateUpdateRequest
from .service import CASE_STATES, OWNER_OPTIONS, service

CASE_CATEGORY_OPTIONS = [
    "runtime_bug",
    "skill_fix",
    "new_skill_candidate",
    "insufficient_signal",
]
CASE_BOARD_COLUMNS = [
    {
        "id": "inspector",
        "title": "Inspector Lane",
        "summary": "新问题、待分诊和阻塞案件。",
        "states": {"new", "inspecting", "blocked"},
        "dot_class": "dot-inspector",
    },
    {
        "id": "engineer",
        "title": "Engineer Lane",
        "summary": "正在实现和返工中的案件。",
        "states": {"fixing", "reopened"},
        "dot_class": "dot-engineer",
    },
    {
        "id": "reviewer",
        "title": "Reviewer Lane",
        "summary": "等待验收和 closure decision。",
        "states": {"reviewing"},
        "dot_class": "dot-reviewer",
    },
    {
        "id": "closed",
        "title": "Closed Lane",
        "summary": "已完成 closure，等待指标沉淀和后续复盘。",
        "states": {"closed"},
        "dot_class": "dot-closed",
    },
]


@asynccontextmanager
async def lifespan(_: FastAPI):
    service.bootstrap()
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(ROOT_DIR / "app" / "static")), name="static")
templates = Jinja2Templates(directory=str(ROOT_DIR / "app" / "templates"))


def render(template_name: str, request: Request, context: dict[str, Any]) -> HTMLResponse:
    payload = {"request": request, **context}
    return templates.TemplateResponse(template_name, payload)


def parse_json_text(raw_text: str | None, fallback: Any) -> Any:
    if not raw_text:
        return fallback
    try:
        return json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {exc.msg}") from exc


def format_seconds(value: Any) -> str:
    if value in (None, ""):
        return "-"
    try:
        total = int(value)
    except (TypeError, ValueError):
        return str(value)
    if total < 60:
        return f"{total}s"
    if total < 3600:
        minutes, seconds = divmod(total, 60)
        return f"{minutes}m {seconds}s"
    hours, remainder = divmod(total, 3600)
    minutes, _ = divmod(remainder, 60)
    return f"{hours}h {minutes}m"


def pretty_json(value: Any) -> str:
    return json.dumps(value or {}, ensure_ascii=False, indent=2)


def build_case_board_columns(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    columns: list[dict[str, Any]] = []
    for item in CASE_BOARD_COLUMNS:
        column_cases = [case for case in cases if case.get("status") in item["states"]]
        columns.append({
            **item,
            "items": column_cases,
        })
    return columns


def build_case_dashboard_stats(cases: list[dict[str, Any]]) -> dict[str, Any]:
    active_cases = [item for item in cases if item.get("status") != "closed"]
    latest_updated = max((item.get("updated_at") for item in cases if item.get("updated_at")), default=None)
    return {
        "total_cases": len(cases),
        "active_cases": len(active_cases),
        "reviewing_cases": sum(1 for item in cases if item.get("status") == "reviewing"),
        "closed_cases": sum(1 for item in cases if item.get("status") == "closed"),
        "latest_updated": latest_updated,
    }


def build_case_event_view(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            **event,
            "payload_pretty": pretty_json(event.get("payload") or {}),
        }
        for event in reversed(events)
    ]


def resolve_related_logs(case_item: dict[str, Any]) -> list[dict[str, Any]]:
    session_id = case_item.get("source_session_id")
    if not session_id:
        return []
    return service.list_logs(session_id=session_id, limit=6)


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "app": settings.app_name,
        "database": settings.mysql_database,
        "bucket": settings.minio_bucket,
    }


@app.get("/", response_class=HTMLResponse)
def index() -> RedirectResponse:
    return RedirectResponse(url="/cases", status_code=302)


@app.get("/cases", response_class=HTMLResponse)
def case_board(
    request: Request,
    status: str | None = None,
    owner: str | None = None,
    category: str | None = None,
    q: str | None = None,
) -> HTMLResponse:
    all_cases = service.list_cases(limit=200)
    filtered_cases = service.list_cases(
        limit=200,
        status=status or None,
        owner=owner or None,
        category=category or None,
        search=q or None,
    )
    return render(
        "cases.html",
        request,
        {
            "cases": filtered_cases,
            "columns": build_case_board_columns(filtered_cases),
            "stats": build_case_dashboard_stats(all_cases),
            "filters": {
                "status": status or "",
                "owner": owner or "",
                "category": category or "",
                "q": q or "",
            },
            "status_options": CASE_STATES,
            "owner_options": OWNER_OPTIONS,
            "category_options": CASE_CATEGORY_OPTIONS,
        },
    )


@app.get("/cases/{case_id}", response_class=HTMLResponse)
def case_detail(request: Request, case_id: str) -> HTMLResponse:
    detail = service.get_case_detail(case_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Case not found")

    case_item = detail["case"]
    highlights = detail.get("highlights") or {}
    loop_metrics = detail.get("metrics", {}).get("loop") or {}
    writeback_plan = (highlights.get("writeback_plan") or {}).get("payload") or {}
    writeback_result = (highlights.get("writeback_result") or {}).get("payload") or {}
    review_summary = (highlights.get("review_summary") or {}).get("payload") or {}
    implementation_summary = (highlights.get("implementation_summary") or {}).get("payload") or {}
    related_logs = resolve_related_logs(case_item)

    loop_metric_rows = [
        ("Decision", loop_metrics.get("decision") or case_item.get("status") or "-"),
        ("Cycle", format_seconds(loop_metrics.get("cycleSeconds"))),
        ("Fix → Review", format_seconds(loop_metrics.get("fixToReviewSeconds"))),
        ("Review → Decision", format_seconds(loop_metrics.get("reviewToDecisionSeconds"))),
        ("Reopened Count", str(loop_metrics.get("reopenedCount", "-"))),
        ("Writeback", loop_metrics.get("writebackStatus") or "-"),
    ]

    writeback_action_rows = list(writeback_plan.get("actions") or [])
    writeback_result_rows = list(writeback_result.get("actionResults") or [])

    return render(
        "case_detail.html",
        request,
        {
            **detail,
            "case": case_item,
            "events_view": build_case_event_view(detail.get("events") or []),
            "loop_metrics": loop_metrics,
            "loop_metric_rows": loop_metric_rows,
            "writeback_plan_payload": writeback_plan,
            "writeback_actions": writeback_action_rows,
            "writeback_result_payload": writeback_result,
            "writeback_results": writeback_result_rows,
            "review_summary_payload": review_summary,
            "review_summary_pretty": pretty_json(review_summary) if review_summary else None,
            "implementation_summary_payload": implementation_summary,
            "implementation_summary_pretty": pretty_json(implementation_summary) if implementation_summary else None,
            "related_logs": related_logs,
            "latest_patch": (highlights.get("patch") or {}).get("artifact"),
            "latest_closure_note": (highlights.get("closure_note") or {}).get("artifact"),
            "metrics_artifact": (highlights.get("metrics") or {}).get("artifact"),
            "writeback_plan_artifact": (highlights.get("writeback_plan") or {}).get("artifact"),
            "writeback_result_artifact": (highlights.get("writeback_result") or {}).get("artifact"),
            "review_summary_artifact": (highlights.get("review_summary") or {}).get("artifact"),
            "implementation_summary_artifact": (highlights.get("implementation_summary") or {}).get("artifact"),
        },
    )


@app.get("/api/cases")
def api_list_cases(
    limit: int = settings.page_size,
    status: str | None = None,
    owner: str | None = None,
    category: str | None = None,
    q: str | None = None,
) -> dict[str, Any]:
    return {
        "items": service.list_cases(
            limit=limit,
            status=status or None,
            owner=owner or None,
            category=category or None,
            search=q or None,
        )
    }


@app.post("/api/cases")
def api_create_case(payload: CaseCreateRequest) -> dict[str, Any]:
    case = service.create_case(payload.model_dump())
    return {
        "case_id": case["case_id"],
        "status": case["status"],
        "created_at": case["created_at"],
    }


@app.get("/api/cases/{case_id}")
def api_get_case_detail(case_id: str) -> dict[str, Any]:
    detail = service.get_case_detail(case_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Case not found")
    return detail


@app.post("/api/cases/{case_id}/events")
def api_append_event(case_id: str, payload: EventCreateRequest) -> dict[str, Any]:
    event = service.append_event(case_id, payload.model_dump())
    return {"event_id": event["event_id"]}


@app.post("/api/cases/{case_id}/state")
def api_update_state(case_id: str, payload: StateUpdateRequest) -> dict[str, Any]:
    case = service.update_state(
        case_id,
        {
            "from_state": payload.from_state,
            "to": payload.to,
            "actor_id": payload.actor_id,
            "reason": payload.reason,
            "category": payload.category,
            "recommended_next_action": payload.recommended_next_action,
        },
    )
    return {
        "case_id": case["case_id"],
        "status": case["status"],
        "updated_at": case["updated_at"],
    }


@app.post("/api/cases/{case_id}/artifacts")
async def api_append_artifact(case_id: str, request: Request) -> dict[str, Any]:
    content_type = request.headers.get("content-type", "")

    if content_type.startswith("application/json"):
        payload = await request.json()
        artifact = service.record_artifact(case_id, payload)
        return {
            "artifact_id": artifact["artifact_id"],
            "case_id": artifact["case_id"],
        }

    if content_type.startswith("multipart/form-data"):
        form = await request.form()
        upload = form.get("file")
        if upload is None or not isinstance(upload, StarletteUploadFile):
            raise HTTPException(status_code=400, detail="Multipart upload requires a file field")

        data = await upload.read()
        artifact = service.upload_artifact(
            case_id=case_id,
            artifact_type=str(form.get("type") or "attachment"),
            stage=str(form.get("stage") or "input"),
            title=str(form.get("title") or upload.filename or "artifact"),
            produced_by_agent=str(form.get("produced_by_agent") or "system"),
            filename=upload.filename or "artifact.bin",
            content_type=upload.content_type,
            data=data,
            artifact_format=str(form.get("format") or Path(upload.filename or "artifact.bin").suffix.lstrip(".") or "binary"),
            metadata=parse_json_text(str(form.get("metadata") or ""), {}),
        )
        return {
            "artifact_id": artifact["artifact_id"],
            "case_id": artifact["case_id"],
        }

    raise HTTPException(status_code=415, detail="Unsupported content type")


@app.post("/api/logs/ingest")
async def api_ingest_log(
    session_type: str = Form("unknown"),
    session_id: str = Form("unknown"),
    log_date: str = Form(""),
    file: UploadFile | None = None,
) -> dict[str, Any]:
    if file is None:
        raise HTTPException(status_code=400, detail="file field required")
    data = await file.read()
    return service.ingest_log(
        session_type=session_type,
        session_id=session_id,
        log_date=log_date,
        filename=file.filename or "session.jsonl",
        data=data,
        content_type=file.content_type,
    )


@app.get("/api/logs")
def api_list_logs(
    session_type: str | None = None,
    session_id: str | None = None,
    log_date: str | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    return {
        "items": service.list_logs(
            session_type=session_type,
            session_id=session_id,
            log_date=log_date,
            limit=limit,
        )
    }


@app.get("/api/logs/pending")
def api_list_pending_logs(agent: str = "inspector", limit: int = 20) -> dict[str, Any]:
    return {"items": service.list_pending_logs(agent=agent, limit=limit)}


@app.get("/api/logs/{log_id}")
def api_get_log_detail(log_id: str) -> dict[str, Any]:
    detail = service.get_session_log_detail(log_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Log not found")
    return detail


@app.post("/api/logs/{log_id}/events")
def api_append_log_event(log_id: str, payload: LogEventCreateRequest) -> dict[str, Any]:
    event = service.append_log_event(log_id, payload.model_dump())
    return {"event_id": event["event_id"]}


@app.post("/api/logs/{log_id}/cards")
def api_append_log_card(log_id: str, payload: LogCardCreateRequest) -> dict[str, Any]:
    card = service.append_log_card(log_id, payload.model_dump())
    return {"card_id": card["card_id"]}


@app.get("/logs", response_class=HTMLResponse)
def log_archive(
    request: Request,
    session_type: str | None = None,
    session_id: str | None = None,
    log_date: str | None = None,
) -> HTMLResponse:
    logs = service.list_logs(
        session_type=session_type,
        session_id=session_id,
        log_date=log_date,
        limit=200,
    )
    total_bytes = sum(int(item.get("size_bytes") or 0) for item in logs)
    unique_sessions = len({item["session_id"] for item in logs if item.get("session_id")})
    latest_upload = max((item.get("uploaded_at") for item in logs if item.get("uploaded_at")), default=None)
    return render(
        "logs.html",
        request,
        {
            "logs": logs,
            "filters": {
                "session_type": session_type or "",
                "session_id": session_id or "",
                "log_date": log_date or "",
            },
            "stats": {
                "total_logs": len(logs),
                "unique_sessions": unique_sessions,
                "total_size_label": service._format_bytes(total_bytes),
                "latest_upload": latest_upload,
            },
        },
    )


@app.get("/logs/{log_id}", response_class=HTMLResponse)
def log_detail(request: Request, log_id: str) -> HTMLResponse:
    detail = service.get_session_log_detail(log_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Log not found")
    return render("log_detail.html", request, detail)


@app.get("/api/logs/{log_id}/download")
def api_download_log(log_id: str) -> Response:
    log_item, data = service.read_session_log_bytes(log_id)
    filename = log_item.get("filename") or f"{log_id}.jsonl"
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return Response(
        content=data,
        media_type="application/x-ndjson",
        headers=headers,
    )


@app.get("/api/artifacts/{artifact_id}/download")
def api_download_artifact(artifact_id: str) -> Response:
    artifact, data = service.read_artifact_bytes(artifact_id)
    filename = artifact.get("original_filename") or f"{artifact_id}.bin"
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return Response(
        content=data,
        media_type=artifact.get("content_type") or "application/octet-stream",
        headers=headers,
    )
