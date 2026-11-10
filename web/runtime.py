"""Runs one STUDY LLM turn in an isolated namespace.

The notebook controller keeps its learning state in module-level globals. On a serverless
platform many learners share one process, so every request gets a FRESH namespace built from
the compiled core, the learner's saved state is loaded into it, one turn runs, and the new
state is returned to the browser (which stores it). Nothing is kept on the server.
"""
from __future__ import annotations

import copy
import json
import pathlib
import time
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parent.parent
CORE_PATH = ROOT / "study_core.py"
_CORE_CODE = compile(CORE_PATH.read_text(encoding="utf-8"), str(CORE_PATH), "exec")

# Globals that make up one learner's session (see notebook cell 2, export_records/load_records).
STATE_KEYS = [
    "learning_context", "concept_records", "messages", "logs",
    "pending_post_explanation_check", "learning_phase", "awaiting_registry_confirmation",
    "pending_new_unit", "pending_study_strategy", "pending_start_requests",
]
MAX_MESSAGES_KEPT = 40   # the controller only reads the last 6-8 messages

COMMANDS = {"turn", "finish", "new_topic", "reset_chat", "progress", "audit", "reset_all"}


def _fresh_namespace() -> dict:
    ns: dict[str, Any] = {"__name__": "study_core_session", "__file__": str(CORE_PATH)}
    exec(_CORE_CODE, ns)
    return ns


def empty_state() -> dict:
    ns = _fresh_namespace()
    return {k: copy.deepcopy(ns[k]) for k in STATE_KEYS}


def _load_state(ns: dict, state: dict | None) -> None:
    state = state or {}
    for key in STATE_KEYS:
        if key in state and state[key] is not None:
            ns[key] = copy.deepcopy(state[key])
    # same migrations the notebook applies in load_records()
    ns["learning_context"].setdefault("concept_id", "")
    for rec in ns["concept_records"].values():
        base = ns["_new_record"]()
        for k, v in base.items():
            rec.setdefault(k, v)
        for skill in rec.get("skill_records", {}).values():
            ns["_ensure_skill_fields"](skill)
            skill.setdefault("state_override", None)


def _dump_state(ns: dict) -> dict:
    out = {}
    for key in STATE_KEYS:
        out[key] = ns[key]
    out["messages"] = list(ns["messages"])[-MAX_MESSAGES_KEPT:]
    # round-trip through JSON so the browser gets plain data (tuples -> lists etc.)
    return json.loads(json.dumps(out, ensure_ascii=False, default=str))


def _progress(ns: dict) -> dict:
    """Structured version of the notebook /progress panel."""
    ctx = ns["learning_context"]
    if not ctx.get("concept_id") and not ctx.get("topic"):
        return {"topic": "", "goal": "", "skills": [], "vulnerability": "unknown", "phase": ns["learning_phase"]}
    record = ns["_record"]()
    p = ns["progress_summary"](record)
    skills = []
    for item in p.get("skills", []):
        sk = record.get("skill_records", {}).get(item.get("skill_id"), {})
        skills.append({
            "skill_id": item.get("skill_id"),
            "label": item.get("label"),
            "state": sk.get("state", "Unconfirmed"),
            "state_label": item.get("state_label"),
            "dimensions": sk.get("dimensions", {}),
            "closed": item.get("closed"),
            "unvisited": bool(sk.get("unvisited")),
            "revealed": bool(sk.get("revealed")),
            "rechecked": bool(sk.get("rechecked")),
            "needs_recheck": bool(sk.get("needs_recheck")),
            "misconceptions": sk.get("misconceptions", [])[-3:],
            "key_points": sk.get("key_points", []),
            "active": item.get("skill_id") == record.get("active_skill_id"),
        })
    done = sum(1 for x in skills if x["closed"] and not x["unvisited"])
    if record.get("wrap_up_active"):
        where = "마무리 확인 중"
    elif record.get("unit_status") == "completed":
        where = "학습 단위 완료"
    else:
        active = next((x for x in skills if x["active"]), None)
        where = f"현재 개념: {active['label']}" if active else "설정 중"
    return {
        "topic": ctx.get("topic", ""), "goal": ctx.get("goal", ""), "concept_id": ctx.get("concept_id", ""),
        "skills": skills, "done": done, "total": len(skills), "where": where,
        "vulnerability": p.get("vulnerability", "unknown"), "unit_status": record.get("unit_status"),
        "wrap_up_active": bool(record.get("wrap_up_active")), "phase": ns["learning_phase"],
    }


def _all_units(ns: dict) -> list:
    """Every learning unit in the record, with its misconceptions (for the 취약 개념 노트)."""
    units = []
    for cid, rec in ns["concept_records"].items():
        skills = []
        for sid, sk in rec.get("skill_records", {}).items():
            skills.append({"label": sk.get("label", sid), "state": sk.get("state"),
                           "misconceptions": [m.get("note", "") for m in sk.get("misconceptions", [])][-3:]})
        units.append({"concept_id": cid, "vulnerability": rec.get("vulnerability", "unknown"),
                      "unit_status": rec.get("unit_status"), "skills": skills})
    return units


def run(state: dict | None, command: str, text: str = "", client=None, model: str | None = None) -> dict:
    if command not in COMMANDS:
        raise ValueError(f"unknown command: {command}")
    ns = _fresh_namespace()
    if client is not None:
        ns["client"] = client
    if model:
        ns["MODEL"] = model
    ns["SHOW_CONTROLLER_DEBUG"] = False

    outputs: list[dict] = []
    events: list[dict] = []

    def _print(*args, sep=" ", end="\n", file=None, flush=False):
        line = sep.join(str(a) for a in args)
        if outputs and outputs[-1]["kind"] == "text":
            outputs[-1]["content"] += "\n" + line
        else:
            outputs.append({"kind": "text", "content": line})

    def _display(obj):
        kind = getattr(obj, "kind", "text")
        outputs.append({"kind": kind, "content": getattr(obj, "data", str(obj))})

    def _display_turn(response_text, record):
        # tutor reply only; the status line is rendered natively by the web UI
        outputs.append({"kind": "markdown", "content": response_text})

    ns["print"] = _print
    ns["display"] = _display
    ns["_display_turn"] = _display_turn
    ns["_trace_event"] = lambda ev: events.append(ev)
    ns["_autosave"] = lambda: None          # the browser keeps the record
    ns["export_records"] = lambda *a, **k: None

    _load_state(ns, state)
    logs_before = len(ns["logs"])
    started = time.time()
    audit = None

    if command == "turn":
        ns["study_turn"](text)
    elif command == "finish":
        ns["finish_unit"]()
    elif command == "new_topic":
        # same as /new-topic in run_chat()
        ns["pending_study_strategy"] = None
        ns["pending_start_requests"].clear()
        ns["learning_context"].update({"topic": "", "goal": "", "concept_id": ""})
        ns["messages"].clear()
        ns["learning_phase"] = "awaiting_topic"
        ns["awaiting_registry_confirmation"] = False
        _print("새 학습 주제를 입력해 주세요. 이전 학습 기록은 보존돼요.")
    elif command == "reset_chat":
        ns["reset_conversation"]()
    elif command == "reset_all":
        fresh = empty_state()
        for k in STATE_KEYS:
            ns[k] = fresh[k]
        _print("전체 학습 기록과 로그를 초기화했어요.")
    elif command == "audit":
        bad = ns["audit_logs"]()
        audit = [{"turn_id": t, "action": a, "rule_check": rc} for (t, a, rc) in bad]
    elif command == "progress":
        pass

    new_logs = ns["logs"][logs_before:]
    outputs = [dict(o, content=str(o["content"]).strip()) for o in outputs if str(o["content"]).strip()]
    return {
        "outputs": outputs,
        "events": events,
        "new_logs": json.loads(json.dumps(new_logs, ensure_ascii=False, default=str)),
        "state": _dump_state(ns),
        "progress": _progress(ns),
        "units": _all_units(ns),
        "audit": audit,
        "elapsed_sec": round(time.time() - started, 2),
        "core_version": ns.get("APP_VERSION"),
    }
