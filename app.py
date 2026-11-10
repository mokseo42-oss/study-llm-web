"""STUDY LLM web — FastAPI entrypoint (Vercel Python runtime picks up `app`).

Environment variables (Vercel → Project → Settings → Environment Variables):
  OPENAI_API_KEY   required unless every user enters their own key in 설정
  OPENAI_MODEL     optional, default "gpt-5.5" (same as the notebook)
  ACCESS_CODE      optional; if set, the app asks for this code before calling the API
  STUDY_FAKE_LLM   "1" = offline demo mode with a scripted fake model (no API cost)
"""
from __future__ import annotations

import os
import pathlib
import time

os.environ.setdefault("TZ", "Asia/Seoul")
if hasattr(time, "tzset"):
    time.tzset()

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from web import runtime

ROOT = pathlib.Path(__file__).resolve().parent
DEFAULT_MODEL = os.environ.get("OPENAI_MODEL", "gpt-5.5")
BASELINE_INSTRUCTIONS = (
    "You are a helpful study assistant. Answer the learner's questions clearly and accurately in Korean."
)

app = FastAPI(title="STUDY LLM", docs_url=None, redoc_url=None)


class TurnRequest(BaseModel):
    command: str = "turn"
    text: str = ""
    state: dict | None = None
    model: str | None = None


class BaselineRequest(BaseModel):
    text: str
    history: list[dict] = Field(default_factory=list)
    model: str | None = None


def _check_access(code: str | None):
    expected = os.environ.get("ACCESS_CODE", "").strip()
    if expected and (code or "").strip() != expected:
        raise HTTPException(status_code=401, detail="접근 코드가 올바르지 않아요. 설정에서 팀이 공유한 코드를 입력해 주세요.")


def _client(user_key: str | None):
    if os.environ.get("STUDY_FAKE_LLM") == "1":
        from web.fake_llm import FakeClient
        return FakeClient()
    from openai import OpenAI
    key = (user_key or "").strip() or os.environ.get("OPENAI_API_KEY", "").strip()
    if not key:
        raise HTTPException(status_code=400, detail="서버에 OpenAI API 키가 설정되지 않았어요. 설정에서 본인 키를 입력하거나 관리자에게 문의해 주세요.")
    return OpenAI(api_key=key, timeout=120, max_retries=1)


def _model(requested: str | None) -> str:
    m = (requested or "").strip()
    return m[:60] if m else DEFAULT_MODEL


@app.get("/api/health")
def health():
    return {
        "ok": True,
        "model": DEFAULT_MODEL,
        "has_server_key": bool(os.environ.get("OPENAI_API_KEY")),
        "access_code_required": bool(os.environ.get("ACCESS_CODE", "").strip()),
        "fake_llm": os.environ.get("STUDY_FAKE_LLM") == "1",
    }


@app.post("/api/turn")
def turn(req: TurnRequest, x_openai_key: str | None = Header(default=None),
         x_access_code: str | None = Header(default=None)):
    _check_access(x_access_code)
    if req.command not in runtime.COMMANDS:
        raise HTTPException(status_code=400, detail="알 수 없는 명령이에요.")
    if req.command == "turn" and not req.text.strip():
        raise HTTPException(status_code=400, detail="내용을 입력해 주세요.")
    needs_llm = req.command in ("turn", "finish")
    client = _client(x_openai_key) if needs_llm else None
    try:
        return runtime.run(req.state, req.command, req.text[:4000], client=client, model=_model(req.model))
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover - surfaced to the UI
        return JSONResponse(status_code=500, content={"detail": f"서버 오류: {exc!r}"})


@app.post("/api/baseline")
def baseline(req: BaselineRequest, x_openai_key: str | None = Header(default=None),
             x_access_code: str | None = Header(default=None)):
    """Controller 미적용 일반 LLM (Baseline) — 같은 모델, 일반 지시문만 사용."""
    _check_access(x_access_code)
    client = _client(x_openai_key)
    history = [{"role": m.get("role"), "content": str(m.get("content", ""))[:4000]}
               for m in req.history[-20:] if m.get("role") in ("user", "assistant")]
    history.append({"role": "user", "content": req.text[:4000]})
    started = time.time()
    try:
        resp = client.responses.create(model=_model(req.model), instructions=BASELINE_INSTRUCTIONS, input=history)
        return {"reply": resp.output_text.strip(), "elapsed_sec": round(time.time() - started, 2)}
    except Exception as exc:
        return JSONResponse(status_code=502, content={"detail": f"Baseline 응답 오류: {exc!r}"})


PUBLIC = ROOT / "public"


@app.get("/")
def index():
    page = PUBLIC / "index.html"
    if page.exists():
        return FileResponse(page)
    # On Vercel, public/ is served by the CDN (not bundled into the function)
    return RedirectResponse("/index.html", status_code=307)


# local development; on Vercel the public/ folder is served by the CDN
if PUBLIC.is_dir():
    app.mount("/", StaticFiles(directory=PUBLIC), name="static")
