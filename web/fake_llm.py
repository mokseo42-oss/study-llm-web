"""Offline fake model (STUDY_FAKE_LLM=1) — lets the whole app run without API cost.

It recognises each controller call by its instructions (like the notebook's _FakeLLM test
double) and returns deterministic, plausible output. Evidence is judged by simple
heuristics so State transitions can be demonstrated; it is NOT a real tutor.
"""
from __future__ import annotations

import json
import re
from types import SimpleNamespace


def _ns(text: str):
    return SimpleNamespace(output_text=text)


class _Responses:
    def create(self, model=None, instructions=None, input=None, text=None, **_):
        ins = instructions or ""
        inp = input if isinstance(input, str) else json.dumps(input, ensure_ascii=False)
        if isinstance(input, list):  # baseline chat
            last = input[-1]["content"] if input else ""
            return _ns(f"(오프라인 데모) '{last[:40]}'에 대한 일반 설명이에요. 정의, 원리, 예시를 한 번에 정리하면 다음과 같아요: "
                       "개념의 정의 → 작동 원리 → 관련 공식 → 예시. 더 궁금한 점이 있으면 물어보세요.")
        if "learning-start intent router" in ins:
            msg = inp.split("LEARNER MESSAGE:\n", 1)[-1].split("\n\nOUTPUT FORMAT", 1)[0].strip()
            topic = re.sub(r"(이|가|을|를|에 대해|에 대해서)?\s*(잘\s*)?(모르겠어|이해가 안 돼|이해 안 돼|헷갈려|공부하고 싶어|알려줘|설명해줘).*$", "", msg).strip(" .?!")
            if len(topic) < 2:
                return _ns(json.dumps({"topic": "", "goal": "", "needs_clarification": True,
                                       "clarification_question": "어떤 구체적인 주제를 공부하고 싶으세요?",
                                       "intent": "other", "direct_request": ""}, ensure_ascii=False))
            return _ns(json.dumps({"topic": topic[:40], "goal": "핵심 개념을 이해하고 새로운 상황에 적용하기",
                                   "needs_clarification": False, "clarification_question": "",
                                   "intent": "structured_learning", "direct_request": ""}, ensure_ascii=False))
        if "Create a concise learning map" in ins or "Compress the learning map" in ins or "Revise the sub-concept registry" in ins:
            m = re.search(r"Topic: (.+)", inp)
            t = (m.group(1).strip() if m else "주제")[:30]
            skills = [
                {"id": "core_definition", "label": f"{t}의 뜻", "key_points": ["정의", "무엇을 설명하는 개념인지"]},
                {"id": "mechanism", "label": f"{t}의 원리", "key_points": ["원인과 결과", "왜 그렇게 되는지"]},
                {"id": "application", "label": f"{t}의 적용", "key_points": ["새 상황에 적용", "수치 비교"]},
            ]
            return _ns(json.dumps({"skills": skills}, ensure_ascii=False))
        if "reviewing a proposed list of sub-concepts" in ins:
            msg = json.loads(inp.split("\n\nOutput requirement", 1)[0]).get("learner_message", "")
            dec = "revise" if re.search(r"빼|추가|바꿔|합쳐", msg) else ("confirm" if re.search(r"좋|네|응|ㅇㅋ|그대로|진행|ok", msg, re.I) else "unclear")
            return _ns(json.dumps({"decision": dec, "revision_request": msg if dec == "revise" else "", "reason": "fake"}))
        if "Classify the learner's intent in context" in ins:
            return _ns(json.dumps({"decision": "start_learning", "new_topic": "", "reason": ""}))
        if "practical study coach" in ins:
            return _ns("(오프라인 데모) 큰 흐름을 먼저 묶어 외우고, 각 단계의 '왜'를 한 문장으로 말해 보세요.")
        if "answering the learner's explicit request" in ins:
            return _ns("(오프라인 데모) 요청하신 설명이에요. 핵심 정의와 원리를 짧게 정리했어요.")
        if ins.startswith("You are a learning assistant. The learner has confirmed"):
            data = json.loads(inp)
            if data.get("prior_misconceptions_from_other_units"):
                return _ns(f"시작하기 전에 하나만 확인할게요. 처음 보는 상황에서 {data['first_skill']}을(를) 어떻게 판단할지 이유와 함께 말해 볼래요?")
            return _ns(f"{data.get('first_skill', '이 개념')}에 대해 아는 대로 설명해 볼래요?")
        if ins.startswith("\nYou are the evidence evaluator") or "evidence evaluator for STUDY LLM" in ins:
            return _ns(json.dumps(self._evaluate(inp), ensure_ascii=False))
        if "Rewrite" in ins:
            return _ns(re.split(r"(?<=[?？])", inp)[0][:150])
        # learner-facing tutor response (RESPONSE_PROMPT)
        try:
            ctx = json.loads(inp)
        except Exception:
            ctx = {}
        return _ns(self._tutor(ctx))

    @staticmethod
    def _evaluate(inp: str) -> dict:
        ctx = json.loads(inp.split("CONTEXT:\n", 1)[1].split("\n\nLATEST LEARNER MESSAGE", 1)[0])
        msg = inp.split("LATEST LEARNER MESSAGE:\n", 1)[1].split("\n\nOutput requirement", 1)[0].strip()
        sid = ctx.get("active_skill_id") or next(iter(ctx.get("skill_registry", {})), "")
        label = ctx.get("skill_registry", {}).get(sid, sid)
        base = {"topic_detected": ctx.get("topic", ""), "goal_detected": "", "skill_id": sid, "skill_label": label,
                "task_complete": False, "task_completion_note": "", "intent": "continue", "has_content_attempt": False,
                "concept": "unknown", "reasoning": "unknown", "transfer": "unknown",
                "concept_source": "unknown", "reasoning_source": "unknown", "transfer_source": "unknown",
                "core_misconception": False, "misconception_note": "", "calculation_or_notation_error_only": False,
                "evidence_note": "", "learner_stuck": False, "same_strategy_failed": False, "key_points_covered": 0,
                "missing_key_point": "", "out_of_scope_error": "", "answered_asked_question_correctly": False,
                "explicit_explain_request": False}
        if re.search(r"설명해 ?줘|알려 ?줘|가르쳐", msg):
            base.update(intent="explain", explicit_explain_request=True, evidence_note="설명 요청")
            return base
        if re.search(r"모르겠|몰라|잘 모르", msg) and len(msg) < 25:
            base.update(learner_stuck=True, evidence_note="자기 평가만 있음 — 판단 근거 없음")
            return base
        base["has_content_attempt"] = True
        if re.search(r"아니야\?|거 아닌가|열을 공급|높으면 .*크", msg):
            base.update(concept="missing", concept_source="independent_explanation", core_misconception=True,
                        misconception_note=f"오개념 신호: {msg[:60]}", evidence_note="핵심 개념과 다른 설명")
            return base
        why = bool(re.search(r"때문|니까|이유|왜냐", msg))
        num = bool(re.search(r"\d", msg))
        base.update(concept="confirmed" if len(msg) >= 12 else "partial", concept_source="independent_explanation",
                    key_points_covered=2 if why else 1, answered_asked_question_correctly=True,
                    evidence_note="학습자가 자기 말로 설명함" + (" + 이유 포함" if why else ""))
        if why:
            base.update(reasoning="confirmed", reasoning_source="independent_explanation")
        else:
            base.update(missing_key_point="이유")
        if num and why:
            base.update(transfer="confirmed", transfer_source="independent_transfer", task_complete=True)
        return base

    @staticmethod
    def _tutor(ctx: dict) -> str:
        action = ctx.get("action", "")
        label = (ctx.get("active_skill") or {}).get("label", "이 개념")
        canned = {
            "diagnostic_question": f"{label}에 대해 아는 대로 설명해 볼래요?",
            "guided_question": "좋아요. 그렇게 되는 이유는 무엇이라고 생각해요?",
            "hint": "힌트를 하나 드릴게요. 원인과 결과를 나눠서 생각해 보면 어떨까요?",
            "diagnose_misconception": "흥미로운 생각이에요. 그렇다면 조건을 하나 바꿨을 때도 같은 결과가 나올까요?",
            "advance_next": f"잘 설명했어요. 다음 개념으로 넘어갈게요. {label}은(는) 어떤 의미라고 생각해요?",
            "full_explanation": f"{label}을(를) 짧게 설명할게요. 핵심은 원인과 결과의 관계예요. 방금 설명을 네 말로 한 문장으로 정리해 볼래요?",
            "reveal_and_next": "정답은 원인과 결과의 관계에 있어요. 다음 개념으로 넘어가서 다시 확인해 볼게요. 어떻게 생각해요?",
            "wrap_up_check": "마무리로 하나만 확인할게요. 새로운 상황에서는 어떻게 될까요?",
            "wrap_up_summary": "오늘 학습을 정리했어요. 잘 확인된 개념과 더 볼 개념을 나눠 두었어요.",
            "practice": "연습 문제예요. 값이 두 배가 되면 결과는 어떻게 될까요?",
        }
        return "(오프라인 데모) " + canned.get(action, "좋아요. 조금 더 자세히 말해 볼래요?")


class FakeClient:
    def __init__(self):
        self.responses = _Responses()
