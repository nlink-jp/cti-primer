"""FastAPI web application for cti-primer.

BEACON-compatible routes with CSRF protection and session management.
"""

from __future__ import annotations

import json
import logging
import secrets
import tempfile
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from cti_primer.config import Config
from cti_primer.models import PIROutput
from cti_primer.pipeline import run_pipeline

logger = logging.getLogger(__name__)

_TEMPLATES_DIR = Path(__file__).parent / "templates"
_MAX_UPLOAD_SIZE = 10 * 1024 * 1024  # 10 MB
_CSRF_TOKEN_BYTES = 32


def create_app(config: Config, *, no_llm: bool = False) -> FastAPI:
    """Create FastAPI application."""
    app = FastAPI(title="CTI Primer", docs_url=None, redoc_url=None)
    templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

    # In-memory session store (single-process only)
    sessions: dict[str, dict[str, Any]] = {}

    def _get_session(request: Request) -> dict[str, Any]:
        sid = request.cookies.get("session_id", "")
        if sid and sid in sessions:
            return sessions[sid]
        return {}

    def _set_session(response: Any, data: dict[str, Any]) -> str:
        sid = secrets.token_hex(16)
        sessions[sid] = data
        response.set_cookie(
            "session_id",
            sid,
            httponly=True,
            samesite="lax",
            max_age=86400,
        )
        return sid

    def _new_csrf() -> str:
        return secrets.token_hex(_CSRF_TOKEN_BYTES)

    def _check_csrf(request_token: str, session: dict) -> bool:
        expected = session.get("csrf_token", "")
        if not expected or not request_token:
            return False
        return secrets.compare_digest(request_token, expected)

    # -----------------------------------------------------------------------
    # HTML Routes
    # -----------------------------------------------------------------------

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request) -> HTMLResponse:
        csrf = _new_csrf()
        session = _get_session(request)
        session["csrf_token"] = csrf
        resp = templates.TemplateResponse(
            request,
            "index.html",
            {
                "csrf_token": csrf,
                "no_llm": no_llm,
            },
        )
        _set_session(resp, session)
        return resp

    @app.post("/generate")
    async def generate(
        request: Request,
        file: UploadFile = File(...),
        csrf_token: str = Form(...),
    ) -> RedirectResponse:
        session = _get_session(request)
        if not _check_csrf(csrf_token, session):
            raise HTTPException(status_code=403, detail="Invalid CSRF token")

        content = await file.read()
        if len(content) > _MAX_UPLOAD_SIZE:
            raise HTTPException(status_code=413, detail="File too large (max 10 MB)")

        # Write to temp file for pipeline
        suffix = Path(file.filename or "input.json").suffix
        with tempfile.NamedTemporaryFile(
            mode="wb",
            suffix=suffix,
            delete=False,
        ) as tmp:
            tmp.write(content)
            tmp_path = Path(tmp.name)

        try:
            result = run_pipeline(tmp_path, config, no_llm=no_llm)
            pir_data = json.loads(result.pir.model_dump_json())
            session["pir_output"] = pir_data
            session["report"] = result.report
        finally:
            tmp_path.unlink(missing_ok=True)

        csrf = _new_csrf()
        session["csrf_token"] = csrf
        resp = RedirectResponse(url="/review", status_code=303)
        _set_session(resp, session)
        return resp

    @app.post("/load")
    async def load(
        request: Request,
        file: UploadFile = File(...),
        csrf_token: str = Form(...),
    ) -> RedirectResponse:
        session = _get_session(request)
        if not _check_csrf(csrf_token, session):
            raise HTTPException(status_code=403, detail="Invalid CSRF token")

        content = await file.read()
        try:
            pir_data = json.loads(content)
            PIROutput(**pir_data)  # validate
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Invalid PIR JSON: {exc}")

        session["pir_output"] = pir_data
        csrf = _new_csrf()
        session["csrf_token"] = csrf
        resp = RedirectResponse(url="/review", status_code=303)
        _set_session(resp, session)
        return resp

    @app.get("/review", response_class=HTMLResponse)
    async def review(request: Request) -> HTMLResponse:
        session = _get_session(request)
        pir_data = session.get("pir_output")
        if not pir_data:
            return RedirectResponse(url="/")

        csrf = _new_csrf()
        session["csrf_token"] = csrf
        resp = templates.TemplateResponse(
            request,
            "review.html",
            {
                "pir": pir_data,
                "csrf_token": csrf,
            },
        )
        _set_session(resp, session)
        return resp

    @app.post("/review/save")
    async def review_save(request: Request) -> JSONResponse:
        session = _get_session(request)
        form = await request.form()
        csrf = form.get("csrf_token", "")
        if not _check_csrf(str(csrf), session):
            raise HTTPException(status_code=403, detail="Invalid CSRF token")

        pir_data = session.get("pir_output")
        if not pir_data:
            raise HTTPException(status_code=404, detail="No PIR in session")

        # Update editable fields
        pir_id = str(form.get("pir_id", ""))
        for item in pir_data.get("pir_items", []):
            if item["pir_id"] == pir_id:
                if "description" in form:
                    item["description"] = str(form["description"])
                if "rationale" in form:
                    item["rationale"] = str(form["rationale"])
                if "recommended_action" in form:
                    item["recommended_action"] = str(form["recommended_action"])
                break

        session["pir_output"] = pir_data
        return JSONResponse({"status": "saved"})

    @app.post("/review/approve")
    async def review_approve(request: Request) -> JSONResponse:
        session = _get_session(request)
        form = await request.form()
        csrf = form.get("csrf_token", "")
        if not _check_csrf(str(csrf), session):
            raise HTTPException(status_code=403, detail="Invalid CSRF token")

        pir_data = session.get("pir_output")
        if not pir_data:
            raise HTTPException(status_code=404, detail="No PIR in session")

        from cti_primer.review.github import GitHubReviewer

        try:
            reviewer = GitHubReviewer(config.github)
            pir = PIROutput(**pir_data)
            urls = reviewer.create_issues(pir)
            return JSONResponse({"status": "approved", "issues": urls})
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    @app.get("/review/export")
    async def review_export(request: Request) -> JSONResponse:
        session = _get_session(request)
        pir_data = session.get("pir_output")
        if not pir_data:
            raise HTTPException(status_code=404, detail="No PIR in session")
        return JSONResponse(pir_data)

    # -----------------------------------------------------------------------
    # REST API Routes
    # -----------------------------------------------------------------------

    @app.get("/api/pir")
    async def api_pir(request: Request) -> JSONResponse:
        session = _get_session(request)
        pir_data = session.get("pir_output")
        if not pir_data:
            return JSONResponse({"pir_items": []})
        return JSONResponse(pir_data)

    @app.post("/api/generate")
    async def api_generate(request: Request) -> JSONResponse:
        body = await request.body()
        if len(body) > _MAX_UPLOAD_SIZE:
            raise HTTPException(status_code=413, detail="Payload too large")

        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Invalid JSON")

        # Write to temp file
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".json",
            delete=False,
            encoding="utf-8",
        ) as tmp:
            json.dump(data, tmp, ensure_ascii=False)
            tmp_path = Path(tmp.name)

        try:
            result = run_pipeline(tmp_path, config, no_llm=no_llm)
            return JSONResponse(json.loads(result.pir.model_dump_json()))
        finally:
            tmp_path.unlink(missing_ok=True)

    return app
