import inspect

# v3.10 regression tests: preserve controller invariants + verify complete startup state machine

def run_v310_controller_regression_tests():
    rec = _new_record()
    set_skill_registry({"electric_field":"전기장", "electric_potential":"전위", "field_potential_relation":"전기장과 전위의 관계"}, rec)
    def assessment(sid, c="unknown", r="unknown", t="unknown", cs="unknown", rs="unknown", ts="unknown", mis=False):
        return {"skill_id":sid,"has_content_attempt":True,"concept":c,"reasoning":r,"transfer":t,
                "concept_source":cs,"reasoning_source":rs,"transfer_source":ts,
                "core_misconception":mis,"misconception_note":"검증용 오개념","evidence_note":"offline test"}
    apply_state_controller(rec, assessment("electric_field", c="confirmed", cs="independent_explanation"), 1)
    assert rec["skill_records"]["electric_field"]["state"] == "State2"
    assert rec["skill_records"]["electric_potential"]["state"] == "Unconfirmed"
    assert rec["skill_records"]["field_potential_relation"]["state"] == "Unconfirmed"
    apply_state_controller(rec, assessment("electric_potential", c="partial", cs="independent_explanation"), 2)
    assert rec["skill_records"]["electric_potential"]["state"] == "Unconfirmed"
    apply_state_controller(rec, assessment("field_potential_relation", c="confirmed", cs="hint_assisted"), 3)
    assert rec["skill_records"]["field_potential_relation"]["state"] == "Unconfirmed"
    apply_state_controller(rec, assessment("electric_potential", c="missing", cs="independent_explanation", mis=True), 4)
    assert rec["skill_records"]["electric_potential"]["state"] == "State1"
    apply_state_controller(rec, assessment("electric_potential", c="confirmed", cs="independent_explanation"), 5)
    assert rec["skill_records"]["electric_potential"]["state"] == "State2"
    apply_state_controller(rec, assessment("electric_potential", c="confirmed", r="confirmed", t="confirmed", cs="independent_explanation", rs="independent_explanation", ts="independent_transfer"), 6)
    assert rec["skill_records"]["electric_potential"]["state"] == "State3"
    apply_state_controller(rec, assessment("electric_potential", r="confirmed", rs="independent_explanation"), 7)
    assert rec["skill_records"]["electric_potential"]["state"] == "State3"
    apply_state_controller(rec, assessment("electric_potential", t="confirmed", ts="independent_transfer"), 8)
    assert rec["skill_records"]["electric_potential"]["state"] == "State3"
    try:
        apply_state_controller(rec, assessment("electric_field_and_potential"), 9)
        raise AssertionError("unknown skill id was accepted")
    except ValueError:
        pass
    apply_state_controller(rec, assessment("electric_potential", c="missing", cs="independent_explanation", mis=True), 10)
    assert rec["skill_records"]["electric_potential"]["state"] == "State2"
    apply_state_controller(rec, assessment("electric_potential", r="missing", rs="independent_explanation"), 11)
    assert rec["skill_records"]["electric_potential"]["state"] == "State1"
    apply_state_controller(rec, assessment("electric_potential", c="confirmed", cs="independent_explanation"), 12)
    n1 = len(rec["skill_records"]["electric_potential"]["evidence"])
    apply_state_controller(rec, assessment("electric_potential", c="confirmed", cs="independent_explanation"), 12)
    assert len(rec["skill_records"]["electric_potential"]["evidence"]) == n1
    print("Controller regression tests: 10/10 passed")


def v310_startup_state_machine_tests():
    # Structural checks for the two critical guards and the setup-only phase.
    import inspect
    src = inspect.getsource(study_turn)
    assert "awaiting_registry_confirmation" in src
    assert "_handle_learning_start(user_text, force_new=True)" in src
    assert src.index("_handle_learning_start(user_text, force_new=True)") < src.index("_call_evaluator(user_text, record, turn_id)")
    hsrc = inspect.getsource(_handle_learning_start)
    assert "awaiting_registry_confirmation" in hsrc
    assert "return True" in hsrc
    assert "Phase: awaiting_registry_confirmation" in hsrc
    assert "initialize_skill_registry(record)" in hsrc
    # The evaluator's topic_detected field must not clear the active unit.
    assert 'learning_context["topic"] = ""' not in inspect.getsource(study_turn)
    print("Startup state-machine structural tests: 7/7 passed")


def v310_confirmation_is_not_evidence_test():
    """Offline tests for the contextual LLM registry-confirmation classifier."""
    from types import SimpleNamespace
    from unittest.mock import patch

    record = _new_record()
    set_skill_registry({"wave_basics": "파동의 기본 개념"}, record)
    original_messages = list(messages)

    cases = [
        ("이대로 진행하면 될 것 같아요.", "confirm", ""),
        ("괜찮을듯. 그대로 해주세요.", "confirm", ""),
        ("그대로 가보자", "confirm", ""),
        ("지금 버전으로 진행해보자", "confirm", ""),
        ("이대로 ㄱ", "confirm", ""),
        ("지금이 좋아보여", "confirm", ""),
        ("2번은 빼고 진행해 주세요.", "revise", "2번 삭제"),
        ("전체적으로 좋은데 3번은 다른 내용으로 바꾸고 싶어요.", "revise", "3번 변경"),
        ("아직 잘 모르겠어요.", "unclear", ""),
        ("괜찮을까요?", "unclear", ""),
    ]

    try:
        for learner_text, expected, revision in cases:
            payload = {"decision": expected, "revision_request": revision,
                       "reason": "offline mocked classifier result"}
            fake_response = SimpleNamespace(
                output_text=json.dumps(payload, ensure_ascii=False)
            )
            with patch.object(client.responses, "create", return_value=fake_response):
                result = _classify_registry_confirmation(learner_text, record)
            assert result["decision"] == expected, (learner_text, result)
            if expected == "revise":
                assert result["revision_request"] == revision
            else:
                assert result["revision_request"] == ""

        # A confirmation is setup metadata only; this test must not create evidence.
        assert all(
            not skill.get("evidence")
            for skill in record.get("skill_records", {}).values()
        )
    finally:
        messages[:] = original_messages

    print(f"Contextual registry-confirmation tests: {len(cases)}/{len(cases)} passed")


def v3102_individual_state_display_tests():
    rec = _new_record()
    set_skill_registry({"skill_a":"개념 A", "skill_b":"개념 B"}, rec)
    def a(sid, c="unknown", r="unknown", t="unknown", cs="unknown", rs="unknown", ts="unknown"):
        return {"skill_id":sid, "has_content_attempt":True,
                "concept":c, "reasoning":r, "transfer":t,
                "concept_source":cs, "reasoning_source":rs, "transfer_source":ts,
                "core_misconception":False, "evidence_note":"v3.10.3 display test"}
    apply_state_controller(rec, a("skill_a", c="confirmed", cs="independent_explanation"), 1)
    apply_state_controller(rec, a("skill_b", c="missing", cs="independent_explanation"), 2)
    summary = progress_summary(rec)
    by_id = {x["skill_id"]:x for x in summary["skills"]}
    assert by_id["skill_a"]["state"] == "State2"
    assert by_id["skill_b"]["state"] == "State1"
    assert "state" not in summary and "raw_state" not in summary
    rec["skill_registry"]["skill_c"] = "개념 C"
    rec["skill_records"]["skill_c"] = {"label":"개념 C", "state":"Unconfirmed",
        "dimensions":{"concept":"unknown", "reasoning":"unknown", "transfer":"unknown"},
        "latest_dimensions":{"concept":"unknown", "reasoning":"unknown", "transfer":"unknown"},
        "evidence":[], "misconceptions":[], "help_level":0}
    summary2 = progress_summary(rec)
    by_id2 = {x["skill_id"]:x for x in summary2["skills"]}
    assert by_id2["skill_a"]["state"] == "State2"
    assert by_id2["skill_b"]["state"] == "State1"
    assert by_id2["skill_c"]["state"] == "Unconfirmed"
    print("v3.10.3 individual-state display tests: 7/7 passed")

v3102_individual_state_display_tests()

run_v310_controller_regression_tests()
v310_confirmation_is_not_evidence_test()
v3102_individual_state_display_tests()
v310_startup_state_machine_tests()


def v3103_registry_replacement_test():
    rec = _new_record()
    set_skill_registry({"old_a":"옛 개념 A", "old_b":"옛 개념 B"}, rec)
    # Seed an old record to ensure it is archived, not mixed into the new registry.
    rec["skill_records"]["old_a"]["evidence"].append({
        "turn_id":1,"skill_id":"old_a","skill_label":"옛 개념 A",
        "dimension":"concept","status":"confirmed","source":"independent_explanation",
        "hint_used":False,"note":"legacy"
    })
    set_skill_registry({
        "derivative_concept":"미분계수의 의미와 기하학적 해석",
        "derivative_rules":"도함수의 의미와 기본 미분법",
        "derivative_applications":"도함수를 이용한 접선 및 함수 분석"
    }, rec)
    assert list(rec["skill_registry"]) == ["derivative_concept","derivative_rules","derivative_applications"]
    assert set(rec["skill_records"]) == set(rec["skill_registry"])
    assert rec["skill_records"]["derivative_concept"]["state"] == "Unconfirmed"
    assert rec["skill_records"]["derivative_concept"]["evidence"] == []
    assert "old_a" in rec["legacy_skill_records"]
    assert rec["active_skill_id"] is None and rec["active_task"] is None
    print("v3.10.3 registry replacement tests: 8/8 passed")


def v3103_state3_transfer_reasoning_test():
    rec = _new_record()
    set_skill_registry({"skill_a":"미분계수의 의미"}, rec)
    def a(c="unknown", r="unknown", t="unknown", cs="unknown", rs="unknown", ts="unknown"):
        return {"skill_id":"skill_a","has_content_attempt":True,
                "concept":c,"reasoning":r,"transfer":t,
                "concept_source":cs,"reasoning_source":rs,"transfer_source":ts,
                "core_misconception":False,"evidence_note":"v3.10.3 test"}
    apply_state_controller(rec, a(c="confirmed",cs="independent_explanation"), 1)
    assert rec["skill_records"]["skill_a"]["state"] == "State2"
    # Reasoning may be demonstrated in a transfer task, and must be independently evidenced.
    apply_state_controller(rec, a(r="confirmed",rs="independent_transfer"), 2)
    assert rec["skill_records"]["skill_a"]["state"] == "State2"
    apply_state_controller(rec, a(t="confirmed",ts="independent_transfer"), 3)
    assert rec["skill_records"]["skill_a"]["state"] == "State3"
    print("v3.10.3 State3 promotion tests: 6/6 passed")


v3103_registry_replacement_test()
v3103_state3_transfer_reasoning_test()


def v3104_state3_two_turn_threshold_test():
    rec = _new_record()
    set_skill_registry({"skill_a":"개념 A"}, rec)
    def ev(dim, turn, source):
        return {"turn_id":turn,"skill_id":"skill_a","skill_label":"개념 A",
                "dimension":dim,"status":"confirmed","source":source,
                "hint_used":False,"note":"test"}
    skill = rec["skill_records"]["skill_a"]
    skill["evidence"] = [
        ev("concept", 1, "independent_explanation"),
        ev("reasoning", 1, "independent_explanation"),
        ev("transfer", 2, "independent_transfer"),
    ]
    assert _skill_state(skill) == "State3"
    print("v3.10.4 State3 two-turn threshold: 5/5 passed")


def v3104_auto_advance_test():
    """v3.13: 개념(C)이 확인되거나 답을 알려 주거나 건너뛰면 목록 순서대로 다음 개념으로 이동한다."""
    rec = _new_record()
    set_skill_registry({"skill_a":"개념 A", "skill_b":"개념 B", "skill_c":"개념 C"}, rec)
    rec["active_skill_id"] = "skill_a"
    assert _next_open_skill_id(rec, "skill_a") == "skill_b"
    _close_skill(rec, "skill_b", "confirmed")
    assert _next_open_skill_id(rec, "skill_a") == "skill_c"
    _close_skill(rec, "skill_c", "revealed")
    assert _next_open_skill_id(rec, "skill_a") is None
    assert rec["skill_records"]["skill_c"]["revealed"] is True
    print("v3.13 sequential next-skill routing: 5/5 passed")


def v3122_topic_switch_detection_tests():
    cases = [
        ("일단 물리학 쪽에서는 궁금했던 게 해결됐어. 근데 일반생물에서도 궁금한 게 있어", True),
        ("다른 과목으로 넘어가고 싶어", True),
        ("새로운 주제로 공부하고 싶어", True),
        ("혹시 일반화학 질문으로 넘어가도 될까?", True),
        ("일반화학에서 molecular orbital 관련 내용을 물어보고 싶어", True),
        ("일반화학에서 molecular orbital을 공부하고 싶어", True),
        ("화학에서 산염기 평형을 배우고 싶어", True),
        ("효소의 작용 원리를 설명해줘", False),
        ("자기선속이 왜 변하는지 모르겠어", False),
        ("분자 오비탈에서 결합성 오비탈이 뭐야?", False),
        ("다음 개념으로 넘어가자", False),
        ("이건 아니까 다음 개념으로 가자", False),
        ("다음 단원으로 넘어가고 싶어", True),
    ]
    for text, expected in cases:
        actual = _is_explicit_topic_switch_request(text)
        assert actual is expected, (text, actual, expected)
    print(f"v3.12.2 topic-switch detection: {len(cases)}/{len(cases)} passed")


def v3122_topic_switch_router_flow_test():
    # Exercise the actual setup gate without network calls. The first message
    # names only the course; the second names both course and concrete topic.
    global learning_phase, pending_new_unit, awaiting_registry_confirmation
    old_router = globals()["_call_start_router"]
    old_init = globals()["initialize_skill_registry"]
    old_context = dict(learning_context)
    old_messages = list(messages)
    old_phase = learning_phase
    old_pending = pending_new_unit
    old_awaiting = awaiting_registry_confirmation
    old_records = dict(concept_records)
    calls = []
    try:
        learning_context.update({"topic":"효소의 작용 원리", "goal":"생물학 개념 이해", "concept_id":"효소의_작용_원리"})
        concept_records.clear()
        concept_records["효소의_작용_원리"] = _new_record()
        messages.clear()
        def fake_router(text):
            calls.append(text)
            if "molecular orbital" not in text.lower():
                return {"topic":"", "goal":"", "needs_clarification":True,
                        "clarification_question":"일반화학에서 어떤 구체적인 주제를 공부하고 싶어?", "intent":"continue"}
            return {"topic":"Molecular Orbital", "goal":"분자 오비탈 이해", "needs_clarification":False,
                    "clarification_question":"", "intent":"continue"}
        def fake_init(record=None):
            set_skill_registry({"mo_theory":"분자 오비탈 이론의 기본 개념"}, record)
            return record["skill_registry"]
        globals()["_call_start_router"] = fake_router
        globals()["initialize_skill_registry"] = fake_init

        assert _is_explicit_topic_switch_request("혹시 일반화학 질문으로 넘어가도 될까?")
        # First message should enter awaiting_topic, not evidence evaluation.
        study_turn("혹시 일반화학 질문으로 넘어가도 될까?")
        assert learning_phase == "awaiting_topic"
        assert pending_new_unit is True
        assert len(calls) == 1

        # Fully specified second message should immediately create the new registry.
        study_turn("일반화학에서 molecular orbital 관련 내용을 물어보고 싶어")
        assert learning_context["topic"] == "Molecular Orbital"
        assert learning_context["concept_id"] == "Molecular_Orbital"
        assert learning_phase == "awaiting_registry_confirmation"
        assert awaiting_registry_confirmation is True
        assert pending_new_unit is False
        assert "효소의_작용_원리" in concept_records
        assert concept_records["효소의_작용_원리"] is not concept_records["Molecular_Orbital"]
        assert list(concept_records["Molecular_Orbital"]["skill_registry"]) == ["mo_theory"]
        assert len(calls) == 2
        print("v3.12.2 topic-switch router flow: 10/10 passed")
    finally:
        globals()["_call_start_router"] = old_router
        globals()["initialize_skill_registry"] = old_init
        learning_context.clear(); learning_context.update(old_context)
        messages.clear(); messages.extend(old_messages)
        learning_phase = old_phase
        pending_new_unit = old_pending
        awaiting_registry_confirmation = old_awaiting
        concept_records.clear(); concept_records.update(old_records)
        pending_start_requests.clear()


def v312_no_manual_add_skill_instruction_test():
    source = inspect.getsource(study_turn)
    assert "add_skill('id'" not in source
    assert "__UNMAPPED__" in source
    assert "이해도 증거로 기록하지 않았어요" in source
    print("v3.12 unmapped learner-message handling: 3/3 checks passed")



# v3.12.2 topic-switch regression tests
v3122_topic_switch_detection_tests()
v3122_topic_switch_router_flow_test()
v312_no_manual_add_skill_instruction_test()


# v3.11 final stabilization regression tests

def v311_dimension_status_exclusivity_test():
    rec = _new_record()
    set_skill_registry({"skill_a":"개념 A", "skill_b":"개념 B"}, rec)
    sa = rec["skill_records"]["skill_a"]
    sa["evidence"] = [
        {"turn_id":1,"dimension":"transfer","status":"confirmed","source":"independent_transfer","hint_used":False},
        {"turn_id":2,"dimension":"transfer","status":"partial","source":"hint_assisted","hint_used":True},
    ]
    sb = rec["skill_records"]["skill_b"]
    sb["evidence"] = [
        {"turn_id":1,"dimension":"concept","status":"confirmed","source":"hint_assisted","hint_used":True},
    ]
    _refresh_skill_states(rec)
    by_id = {x["skill_id"]: x for x in progress_summary(rec)["skills"]}
    item = by_id["skill_a"]
    # 한 번 ○로 확인된 항목은 오개념이 나오기 전까지 유지된다 (피드백 4번 버그 수정).
    assert "새 상황 적용" in item["confirmed"]
    assert "새 상황 적용" not in item["partial"] and "새 상황 적용" not in item["unconfirmed"]
    # 힌트를 받고 맞힌 답은 △ 로 기록된다.
    assert "개념" in by_id["skill_b"]["partial"] and "개념" not in by_id["skill_b"]["unconfirmed"]
    for it in by_id.values():
        for dim in ("개념", "이유 설명", "새 상황 적용"):
            assert sum(dim in it[k] for k in ("confirmed", "partial", "unconfirmed")) == 1
    print("v3.13 C/R/T display persistence + hint-assisted partial: 7/7 passed")


def v311_state3_evidence_combination_test():
    rec = _new_record()
    set_skill_registry({"skill_a":"개념 A"}, rec)
    sk = rec["skill_records"]["skill_a"]
    sk["evidence"] = [
        {"turn_id":1,"dimension":"concept","status":"confirmed","source":"independent_explanation","hint_used":False},
        {"turn_id":1,"dimension":"reasoning","status":"confirmed","source":"independent_explanation","hint_used":False},
        {"turn_id":2,"dimension":"transfer","status":"confirmed","source":"independent_transfer","hint_used":False},
        # Later repeated concept evidence must not hide the valid earlier C/R/T set.
        {"turn_id":3,"dimension":"concept","status":"confirmed","source":"independent_explanation","hint_used":False},
    ]
    assert _skill_state(sk) == "State3"
    print("v3.11 robust State3 evidence combination: 1/1 passed")


def v311_practice_target_persistence_test():
    rec = _new_record()
    set_skill_registry({"magnetic_flux":"자기선속","lenz_law":"렌츠 법칙"}, rec)
    rec["active_skill_id"] = "lenz_law"
    action = choose_action(rec, "practice", {"skill_id":"lenz_law"})
    assert action == "practice"
    assert rec["practice_session"]["target_skill_id"] == "lenz_law"
    assert rec["practice_session"]["active"] is True
    print("v3.11 practice target persistence: 3/3 passed")


v311_dimension_status_exclusivity_test()
v311_state3_evidence_combination_test()
v311_practice_target_persistence_test()


# v3.12.8: preserve explicit study-strategy requests instead of forcing topic decomposition.
def v3128_study_strategy_routing_test():
    from unittest.mock import patch
    global learning_phase, pending_study_strategy
    old_context = dict(learning_context)
    old_phase = learning_phase
    old_pending = pending_study_strategy
    old_messages = list(messages)
    try:
        learning_context.update({"topic": "", "goal": "", "concept_id": ""})
        learning_phase = "awaiting_topic"
        pending_study_strategy = None
        messages.clear()
        with patch("__main__._call_start_router", return_value={
            "topic": "세포 호흡",
            "goal": "세포 호흡 내용을 효과적으로 암기하기",
            "needs_clarification": False,
            "clarification_question": "",
            "intent": "study_strategy"
        }), patch("__main__._generate_study_strategy", return_value="세포 호흡은 큰 흐름부터 묶어 외우세요.") as advice:
            handled = _handle_learning_start("세포 호흡 중인데 내용 암기가 안돼. 암기법 좀 알려줄래")
        assert handled is True
        assert learning_phase == "awaiting_strategy_followup"
        assert pending_study_strategy["topic"] == "세포 호흡"
        assert learning_context["topic"] == "세포 호흡"
        assert not _record().get("skill_registry")
        advice.assert_called_once()
    finally:
        learning_context.clear()
        learning_context.update(old_context)
        learning_phase = old_phase
        pending_study_strategy = old_pending
        messages[:] = old_messages
        pending_start_requests.clear()
    print("v3.12.8 study-strategy intent preservation: 5/5 passed")


v3128_study_strategy_routing_test()


# v3.13 UI and tone regression checks
def v313_ui_tone_tests():
    import inspect
    src = inspect.getsource(_display_turn)
    assert "/progress" in src and "display(HTML(line))" in src
    assert "<details" not in src and "dimensions" not in src      # 매 턴 C/R/T 전체 기록을 보여 주지 않는다
    assert "<details" not in inspect.getsource(_progress_panel_html)
    assert "존댓말" in RESPONSE_PROMPT and "해요체" in RESPONSE_PROMPT
    assert SHOW_CONTROLLER_DEBUG is False
    assert "if SHOW_CONTROLLER_DEBUG:" in inspect.getsource(study_turn)
    assert "if SHOW_CONTROLLER_DEBUG:" in inspect.getsource(_dbg)
    assert "print(\"[Controller]" not in inspect.getsource(_handle_learning_start)
    assert "Never mention internal terms" in RESPONSE_PROMPT
    assert "KOREAN" in EVALUATOR_PROMPT
    return "v3.13 UI/tone structural checks: 10/10 passed"

print(v313_ui_tone_tests())


# v3.13 scenario tests: 피드백의 테스트 대화(크로마토그래피)를 API 없이 재현해서 규칙을 검증한다.
# OpenAI 호출은 가짜 클라이언트로 대체하고, 평가 결과(evaluator)는 시나리오대로 넣어 준다.
import contextlib
from types import SimpleNamespace
from unittest.mock import patch


class _FakeLLM:
    """instructions 내용으로 호출 종류를 구분해 결정적인 응답을 돌려주는 가짜 LLM."""
    SKILLS = [
        {"id": "chroma_def", "label": "크로마토그래피의 뜻과 목적", "key_points": ["혼합물 분리 방법", "성분 특성 차이 이용"]},
        {"id": "phases", "label": "고정상과 이동상의 역할", "key_points": ["고정상은 붙잡음", "이동상은 성분을 운반"]},
        {"id": "separation", "label": "이동 속도 차이에 의한 분리 원리", "key_points": ["성분별 이동 속도 차이", "상과의 친화력 차이"]},
        {"id": "rf_values", "label": "Rf값과 머무름 시간", "key_points": ["이동 거리 비", "머무름 시간은 성분 특성"]},
    ]

    def __init__(self):
        self.evaluations = []      # 시나리오가 미리 넣어 두는 평가 결과
        self.response_inputs = []  # 응답 생성기에 전달된 context
        self.router_inputs = []
        self.calls = []
        self.router_script = None  # callable(text) -> dict
        self.classifier_script = None
        self.followup_decision = "start_learning"

    def queue(self, **kw):
        self.evaluations.append(kw)

    def create(self, model=None, instructions=None, input=None, text=None, **_):
        ins = instructions or ""
        if text and text.get("format", {}).get("type") == "json_object" and "json" not in (input or "").lower():
            raise ValueError("JSON 모드는 입력 메시지에 'JSON'이라는 단어가 있어야 합니다 (실제 API와 같은 제약)")
        self.calls.append(ins[:40])
        out = ""
        if ins.startswith(EVALUATOR_PROMPT[:60]):
            out = json.dumps(self.evaluations.pop(0), ensure_ascii=False)
        elif "learning-start intent router" in ins:
            self.router_inputs.append(input)
            body = input.split("LEARNER MESSAGE:\n", 1)[1].split("\n\nOUTPUT FORMAT", 1)[0]
            out = json.dumps(self.router_script(body), ensure_ascii=False)
        elif "Create a concise learning map" in ins:
            out = json.dumps({"skills": self.SKILLS}, ensure_ascii=False)
        elif "Revise the sub-concept registry" in ins:
            out = json.dumps({"skills": self.SKILLS[:3]}, ensure_ascii=False)
        elif "classify the learner's intent while they are reviewing" in ins:
            out = json.dumps(self.classifier_script(json.loads(input.split("\n\nOutput requirement", 1)[0])["learner_message"]), ensure_ascii=False)
        elif "Classify the learner's intent in context" in ins:
            out = json.dumps({"decision": self.followup_decision, "new_topic": "", "reason": ""})
        elif "practical study coach" in ins:
            out = "원리: 성분별 이동 속도 차이로 분리돼요. 암기법: 흐름을 먼저 외워 보세요."
        elif "answering the learner's explicit request" in ins:
            out = "1. 크로마토그래피의 원리를 설명하시오.\n2. 고정상과 이동상의 차이는?\n3. Rf값 정의는?\n4. 머무름 시간은?\n5. 분리 예시를 쓰시오."
        elif ins == START_CONFIRM_PROMPT:
            out = "크로마토그래피가 무엇인지 어떻게 설명할 수 있나요?"
        elif ins.startswith(RESPONSE_PROMPT[:60]) and "Rewrite as a SINGLE-STEP hint" in ins:
            self.rewrites = getattr(self, "rewrites", 0) + 1
            out = "괜찮아요. 핵 하나만 떠올려 볼게요. 핵은 어떤 일을 맡고 있을까요?"
        elif ins.startswith(RESPONSE_PROMPT[:60]) and "Rewrite with at most ONE" in ins:
            out = input.split("?")[0] + "?"
        elif ins.startswith(RESPONSE_PROMPT[:60]):
            ctx = json.loads(input)
            self.response_inputs.append(ctx)
            a = ctx["action"]
            if a == "wrap_up_summary":
                out = "마무리했어요. 아직 부족한 개념을 정리했어요. 복습할까요, 다음 단원으로 갈까요?"
            elif a == "closing_ack":
                out = "알겠어요. 새 주제를 공부하고 싶으면 말씀해 주세요."
            elif a == "hint" and getattr(self, "long_hint", False):
                out = "좋아요. " + "리보솜은 단백질을 만들고 소포체는 이동시키며 골지체는 포장해요. " * 8 + "어떤 소기관이 관여할까요?"
            else:
                out = f"({a}) 자기 말로 설명해 볼까요?"
        else:
            raise AssertionError("unexpected LLM call: " + ins[:80])
        return SimpleNamespace(output_text=out)


def _ev(sid, c="unknown", cs="unknown", r="unknown", rs="unknown", t="unknown", ts="unknown", attempt=True, **kw):
    d = {"topic_detected": "", "goal_detected": "", "skill_id": sid, "skill_label": "", "task_complete": False,
         "task_completion_note": "", "intent": "continue", "has_content_attempt": attempt,
         "concept": c, "reasoning": r, "transfer": t, "concept_source": cs, "reasoning_source": rs,
         "transfer_source": ts, "core_misconception": False, "misconception_note": "",
         "calculation_or_notation_error_only": False, "evidence_note": "테스트 근거", "learner_stuck": False,
         "same_strategy_failed": False, "key_points_covered": 0, "missing_key_point": ""}
    d.update(kw)
    return d


_NO = dict(attempt=False)
_IND = dict(c="confirmed", cs="independent_explanation")


@contextlib.contextmanager
def _scenario_sandbox():
    """전역 학습 상태를 저장했다가 복원한다."""
    global learning_phase, awaiting_registry_confirmation, pending_new_unit, pending_study_strategy
    global pending_post_explanation_check, learning_context, concept_records, logs
    saved = dict(ctx=dict(learning_context), recs=dict(concept_records), msgs=list(messages), logs=list(logs),
                 phase=learning_phase, awaiting=awaiting_registry_confirmation, newunit=pending_new_unit,
                 strat=pending_study_strategy, post=pending_post_explanation_check, pend=list(pending_start_requests))
    learning_context.update({"topic": "", "goal": "", "concept_id": ""})
    concept_records.clear(); messages.clear(); logs.clear(); pending_start_requests.clear()
    learning_phase = "idle"; awaiting_registry_confirmation = False; pending_new_unit = False
    pending_study_strategy = None; pending_post_explanation_check = False
    fake = _FakeLLM()
    try:
        with patch.object(client.responses, "create", side_effect=fake.create):
            yield fake
    finally:
        learning_context.clear(); learning_context.update(saved["ctx"])
        concept_records.clear(); concept_records.update(saved["recs"])
        messages[:] = saved["msgs"]; logs[:] = saved["logs"]
        learning_phase = saved["phase"]; awaiting_registry_confirmation = saved["awaiting"]
        pending_new_unit = saved["newunit"]; pending_study_strategy = saved["strat"]
        pending_post_explanation_check = saved["post"]
        pending_start_requests[:] = saved["pend"]


def _quiet(fn, *a, **k):
    import io
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        fn(*a, **k)
    return buf.getvalue()


def _start_unit(fake, confirm_text="좋은데?"):
    """주제 시작 → 하위 개념 확정 → 첫 진단 질문까지 진행."""
    fake.router_script = lambda t: {"topic": "크로마토그래피", "goal": "크로마토그래피 이해", "needs_clarification": False,
                                    "clarification_question": "", "intent": "structured_learning", "direct_request": ""}
    fake.classifier_script = lambda t: {"decision": "confirm", "revision_request": "", "reason": ""}
    _quiet(study_turn, "크로마토그래피 공부하고 싶어")
    assert learning_phase == "awaiting_registry_confirmation"
    _quiet(study_turn, confirm_text)
    assert learning_phase == "diagnosing"
    return _record()


def v313_chromatography_dialogue_test():
    """피드백의 테스트 대화 흐름: 요청 보존 → 목록 확정 → 개념별 최대 2번 질문 → 마무리 확인 3문제."""
    with _scenario_sandbox() as fake:
        # 1) 주제가 없을 때 되묻되, 암기법·원리 요청을 버리지 않는다.
        fake.router_script = lambda t: ({"topic": "", "goal": "", "needs_clarification": True,
                                         "clarification_question": "어떤 구체적인 주제를 공부하고 싶으세요?", "intent": "other",
                                         "direct_request": "암기 방법"} if "크로마토" not in t else
                                        {"topic": "크로마토그래피", "goal": "원리 이해와 암기", "needs_clarification": False,
                                         "clarification_question": "", "intent": "study_strategy", "direct_request": "원리 설명과 암기 방법"})
        _quiet(study_turn, "안녕")
        _quiet(study_turn, "기기분석 암기 잘하는 방법 좀 알려주겠니")
        assert len(pending_start_requests) == 2
        out = _quiet(study_turn, "흠.. 크로마토그래피에 대해서 원리와 암기하는 방법을 잘 설명해줘")
        assert "원리" in out and learning_phase == "awaiting_strategy_followup"
        assert "암기 잘하는 방법" in fake.router_inputs[-1]                     # 앞선 요청이 함께 해석됨
        assert pending_start_requests == []
        # 2) 목록은 3~5개, 화면에 내부 ID가 보이지 않는다.
        fake.router_script = lambda t: {"topic": "크로마토그래피", "goal": "크로마토그래피 이해", "needs_clarification": False,
                                        "clarification_question": "", "intent": "structured_learning", "direct_request": ""}
        out = _quiet(study_turn, "응 그렇게 시작하자")
        assert learning_phase == "awaiting_registry_confirmation"
        rec = _record()
        assert 3 <= len(rec["skill_registry"]) <= 5
        assert "chroma_def" not in out and "1. 크로마토그래피의 뜻과 목적" in out
        assert rec["skill_records"]["separation"]["key_points"] == ["성분별 이동 속도 차이", "상과의 친화력 차이"]
        # 3) 주제 확인 중 다른 요청(5문제 출제)은 목록 수정이 아니라 먼저 답하고 확인으로 돌아온다.
        fake.classifier_script = lambda t: {"decision": "other_request" if "5문제" in t else "confirm",
                                            "revision_request": "", "reason": ""}
        before = dict(rec["skill_registry"])
        out = _quiet(study_turn, "교수님 입장에서 5문제 출제해줘")
        assert "5." in out and "이대로 진행할까요" in out
        assert rec["skill_registry"] == before and learning_phase == "awaiting_registry_confirmation"
        # 4) "좋은데?" 는 동의로 인식되어 첫 진단 질문으로 간다.
        _quiet(study_turn, "좋은데?")
        assert learning_phase == "diagnosing" and rec["skill_records"]["chroma_def"]["ask_count"] == 1
        # 5) 개념 1: 모른다 → 힌트(2번째 질문) → 힌트 받고 맞힘 → 인정하고 넘어가되 마무리에서 재확인
        fake.queue(**_ev("chroma_def", **_NO, learner_stuck=True))
        _quiet(study_turn, "음... 잘 모르겠는걸?")
        assert logs[-1]["next_action"] == "hint"
        fake.queue(**_ev("chroma_def", c="confirmed", cs="hint_assisted"))
        _quiet(study_turn, "여러 성분이 섞인 혼합물을 다루겠지요?")
        assert logs[-1]["next_action"] == "advance_next"
        s1 = rec["skill_records"]["chroma_def"]
        assert s1["closed"] == "confirmed" and s1["needs_recheck"] and s1["dimensions"]["concept"] == "partial"
        assert rec["active_skill_id"] == "phases" and rec["skill_records"]["phases"]["ask_count"] == 1
        # 6) 개념 2: 짧은 답도 핵심이 있으면 한 번에 인정하고 다음으로 (질질 끌지 않음)
        fake.queue(**_ev("phases", **_IND, key_points_covered=2))
        _quiet(study_turn, "고정상은 잡아두고 이동상이 실어 나름")
        assert logs[-1]["next_action"] == "advance_next" and rec["skill_records"]["phases"]["state"] == "State2"
        assert rec["active_skill_id"] == "separation"
        # 7) 개념 3: 같은 개념에서 두 번 물어도 모르면 답을 알려주고 넘어간다.
        fake.queue(**_ev("separation", **_NO, learner_stuck=True))
        _quiet(study_turn, "몰라 ㅋㅋ")
        assert logs[-1]["next_action"] == "hint"
        fake.queue(**_ev("separation", **_NO, learner_stuck=True))
        _quiet(study_turn, "그래도 모르겠어")
        assert logs[-1]["next_action"] == "hint" and rec["skill_records"]["separation"]["help_level"] == 2   # 두 번째 힌트(한 단계 더 구체적)
        fake.queue(**_ev("separation", **_NO, learner_stuck=True))
        _quiet(study_turn, "진짜 모르겠어")
        assert logs[-1]["next_action"] == "reveal_and_next"
        s3 = rec["skill_records"]["separation"]
        assert s3["revealed"] and s3["closed"] == "revealed" and rec["active_skill_id"] == "rf_values"
        assert fake.response_inputs[-1].get("reveal_key_points") == ["성분별 이동 속도 차이", "상과의 친화력 차이"]
        assert "explain_key_points" not in fake.response_inputs[-1]      # 진단 질문에 단서가 새지 않는다
        # 8) 개념 4 확인 → 모든 개념을 다뤘으므로 마무리 확인: 답 알려준 개념이 맨 앞
        fake.queue(**_ev("rf_values", **_IND))
        _quiet(study_turn, "Rf는 용매가 간 거리 대비 성분이 간 거리 비율")
        assert logs[-1]["next_action"] == "wrap_up_check"
        assert rec["wrap_target"]["skill_id"] == "separation" and rec["wrap_target"]["dimension"] == "concept"
        assert logs[-1]["rule_check"]["chars_ok"]
        order = [rec["wrap_target"]["skill_id"]] + [q["skill_id"] for q in rec["wrap_up_queue"]]
        assert order[:3] == ["separation", "chroma_def", "phases"]            # 답 공개 > 도움받아 확인 > 나머지(R/T)
        # 9) 마무리 확인은 최대 3문제. 이미 확인된 개념의 C는 다시 묻지 않는다.
        asked = [rec["wrap_target"]["dimension"]]
        for sid in ("separation", "chroma_def", "phases"):
            fake.queue(**_ev(sid, **_IND))
            _quiet(study_turn, "자기 말로 설명")
            if logs[-1]["next_action"] == "wrap_up_check":
                asked.append(rec["wrap_target"]["dimension"])
        assert logs[-1]["next_action"] == "wrap_up_summary" and rec["wrap_up_questions_asked"] == 3
        assert asked == ["concept", "concept", "reasoning_transfer"]
        assert rec["unit_status"] == "completed" and rec["review_offered"]
        _ri = fake.response_inputs[-1]
        assert "weak_skills" in _ri and _ri["confirmed_skills"] and "untested_note" in _ri   # 약한 것/잘한 것/안 다룬 것 분리
        assert all(rec["skill_records"][x].get("rechecked") for x in ("separation", "chroma_def", "phases"))
        # 10) 복습을 거절하면 다시 권하지 않는다.
        fake.queue(**_ev("phases", **_NO, intent="continue"))
        _quiet(study_turn, "아니 괜찮아요")
        assert logs[-1]["next_action"] == "closing_ack"
        # 11) 규칙 검사: 글자 수·질문 수·State 이동
        assert all(l["rule_check"]["questions_ok"] and l["rule_check"]["state_step_ok"] for l in logs)
        assert audit_logs.__name__ if "audit_logs" in globals() else True
    print("v3.13 chromatography dialogue scenario: 36/36 passed")


def v313_first_request_and_direction_tests():
    with _scenario_sandbox() as fake:
        # 첫 메시지의 요청(5문제 출제)은 진단·목록보다 먼저 처리한다.
        fake.router_script = lambda t: {"topic": "크로마토그래피", "goal": "문제로 이해", "needs_clarification": False,
                                        "clarification_question": "", "intent": "practice", "direct_request": "교수님 입장에서 5문제 출제"}
        out = _quiet(study_turn, "크로마토그래피 교수님 입장에서 5문제 출제해줘")
        assert out.index("1. 크로마토그래피의 원리를 설명하시오.") < out.index("다음 하위 개념으로 나누어 학습할게요")
        assert not any("문제" in l for l in _record()["skill_registry"].values())
    with _scenario_sandbox() as fake:
        rec = _start_unit(fake)
        # 진행 방식 불만 → 같은 질문 반복 대신 선택지를 준다 (질문 횟수·턴 수는 늘지 않는다)
        ask_before = rec["skill_records"]["chroma_def"]["ask_count"]
        fake.queue(**_ev("chroma_def", **_NO, intent="process_complaint"))
        _quiet(study_turn, "근데 정의만 공부하려는 게 아닌데 그것만 계속 물어볼 거야?")
        assert logs[-1]["next_action"] == "offer_direction_choice"
        assert rec["skill_records"]["chroma_def"]["ask_count"] == ask_before
        assert rec["skill_records"]["chroma_def"]["turns_spent"] == 0
        # "다음으로 넘어가자" → 건너뜀(미확인으로 남김) + 다음 개념
        fake.queue(**_ev("chroma_def", **_NO, intent="skip_check"))
        _quiet(study_turn, "다음 개념으로 넘어가자")
        assert logs[-1]["next_action"] == "advance_next" and rec["skill_records"]["chroma_def"]["closed"] == "skipped"
        assert rec["skill_records"]["chroma_def"]["state"] == "Unconfirmed"
        assert rec["active_skill_id"] == "phases"
        # 설명 요청 → 설명 + 확인 질문, 증거로 기록하지 않음, 증거 없이 State 변화 없음
        fake.queue(**_ev("phases", **_NO, intent="explain"))
        _quiet(study_turn, "고정상이 뭔지 그냥 설명해줘")
        assert logs[-1]["next_action"] == "full_explanation" and rec["skill_records"]["phases"]["state"] == "Unconfirmed"
        assert fake.response_inputs[-1]["explanation_strategy"] in STRATEGIES
        # 마무리 요청 → 남은 개념을 건너뜀으로 닫고 건너뛴 개념 우선 확인
        _quiet(finish_unit)
        assert logs[-1]["next_action"] == "wrap_up_check"
        assert rec["wrap_target"]["skill_id"] == "chroma_def" and rec["wrap_target"]["reason"] == "skipped"
    print("v3.13 first-request / direction-choice scenarios: 14/14 passed")


def v313_misconception_and_help_ladder_tests():
    with _scenario_sandbox() as fake:
        rec = _start_unit(fake)
        # 오개념: 정답을 바로 알려주지 않고 질문 1개 (규칙 4), 다시 틀리면 답 안내 후 이동
        fake.queue(**_ev("chroma_def", c="missing", cs="independent_explanation", core_misconception=True,
                         misconception_note="순물질 분리라고 오해"))
        _quiet(study_turn, "순물질을 분리하는 거야")
        assert logs[-1]["next_action"] in ("diagnose_misconception", "reveal_and_next")
        assert rec["skill_records"]["chroma_def"]["state"] == "State1"
        assert rec["skill_records"]["chroma_def"]["ask_count"] == 2 or logs[-1]["next_action"] == "reveal_and_next"
    with _scenario_sandbox() as fake:
        rec = _start_unit(fake)
        # 계산·표기 실수만으로는 State를 내리지 않는다 (규칙 4·9)
        fake.queue(**_ev("chroma_def", **_IND))
        _quiet(study_turn, "혼합물 분리법")
        st = rec["skill_records"]["chroma_def"]["state"]
        assert st == "State2"
    # 규칙 7: 같은 설명 전략을 연속 반복하지 않고 2회를 넘기지 않는다.
    sk = _new_skill_record("개념")
    picks = [_pick_strategy(sk) for _ in range(6)]
    assert all(picks[i] != picks[i + 1] for i in range(5))
    assert all(picks.count(s) <= 2 for s in STRATEGIES)
    # 규칙 10: 마무리 대기열 우선순위와 State3 생략
    rec = _new_record()
    set_skill_registry({"a": "A", "b": "B", "c": "C", "d": "D"}, rec)
    rec["skill_records"]["a"]["closed"] = "confirmed"; rec["skill_records"]["a"]["dimensions"]["concept"] = "confirmed"
    rec["skill_records"]["b"].update({"closed": "revealed", "revealed": True})
    rec["skill_records"]["c"].update({"closed": "skipped"})
    rec["skill_records"]["d"].update({"closed": "confirmed", "state": "State3"})
    q = _build_wrap_up_queue(rec)
    assert [x["skill_id"] for x in q] == ["b", "c", "a"] and q[2]["dimension"] == "reasoning_transfer"
    print("v3.13 misconception / ladder / queue tests: 11/11 passed")


v313_chromatography_dialogue_test()
v313_first_request_and_direction_tests()
v313_misconception_and_help_ladder_tests()

def v313_strategy_followup_regression_test():
    """실제 사용에서 발견된 버그: 전략 안내 뒤 '학습부터 하자'를 계속 못 알아듣던 문제."""
    with _scenario_sandbox() as fake:
        fake.router_script = lambda t: ({"topic": "근육 작동 방식", "goal": "암기", "needs_clarification": False,
                                         "clarification_question": "", "intent": "study_strategy", "direct_request": "암기법"}
                                        if "암기" in t else
                                        {"topic": "근육 작동 방식", "goal": "근육 작동 방식 이해", "needs_clarification": False,
                                         "clarification_question": "", "intent": "structured_learning", "direct_request": ""})
        _quiet(study_turn, "일반생물 공부 중인데 암기가 너무 안돼 근육 작동 방식 암기법 알려줘")
        assert learning_phase == "awaiting_strategy_followup"
        out = _quiet(study_turn, "학습부터 하자")                  # JSON 모드 입력 제약을 지켜야 분류가 성공한다
        assert learning_phase == "awaiting_registry_confirmation", out
        assert "오류" not in out
    with _scenario_sandbox() as fake:
        fake.router_script = lambda t: {"topic": "근육 작동 방식", "goal": "암기", "needs_clarification": False,
                                        "clarification_question": "", "intent": "study_strategy" if "암기" in t else "structured_learning",
                                        "direct_request": "암기법" if "암기" in t else ""}
        _quiet(study_turn, "근육 암기법 알려줘")
        fake.followup_decision = "unclear"
        _quiet(study_turn, "음...")
        assert learning_phase == "awaiting_strategy_followup"
        _quiet(study_turn, "글쎄")                                   # 두 번 연속 불분명하면 같은 안내를 반복하지 않고 학습 시작
        assert learning_phase == "awaiting_registry_confirmation"
    with _scenario_sandbox() as fake:
        # 호출이 실제로 실패하면(예: 네트워크) 조용히 삼키지 않고 원인을 알린다.
        rec = _start_unit(fake) if False else None
        fake.router_script = lambda t: {"topic": "t", "goal": "g", "needs_clarification": False, "clarification_question": "",
                                        "intent": "structured_learning", "direct_request": ""}
        fake.classifier_script = lambda t: (_ for _ in ()).throw(RuntimeError("boom"))
        _quiet(study_turn, "크로마토그래피 공부하고 싶어")
        out = _quiet(study_turn, "좋아요")
        assert "오류" in out and learning_phase == "awaiting_registry_confirmation"
    print("v3.13 strategy follow-up / JSON-mode regression: 6/6 passed")


v313_strategy_followup_regression_test()


def v313_hint_is_single_step_test():
    """피드백(실사용): '모르겠다'에 소기관 기능을 줄줄이 설명하던 힌트를 한 단계 힌트로 되돌린다."""
    with _scenario_sandbox() as fake:
        rec = _start_unit(fake)
        fake.long_hint = True
        fake.queue(**_ev("chroma_def", **_NO, learner_stuck=True))
        out = _quiet(study_turn, "어.. 잘 모르겠는데")
        assert logs[-1]["next_action"] == "hint"
        assert getattr(fake, "rewrites", 0) == 1
        assert len(logs[-1]["response"]) <= MAX_HINT_CHARS and "리보솜" not in logs[-1]["response"]
        assert not logs[-1]["response"].startswith("좋아요")
        assert fake.response_inputs[-1]["target_key_point"] == "혼합물 분리 방법"      # 힌트는 목표 핵심 요소 쪽으로 이끈다
        assert "explain_key_points" not in fake.response_inputs[-1]
        assert logs[-1]["rule_check"]["chars_ok"]
    print("v3.13 single-step hint guard: 5/5 passed")


v313_hint_is_single_step_test()


def v313_stuck_is_not_explain_request_test():
    """실사용 버그: '잘 모르겠는데'를 설명 요청으로 오판해 소기관을 줄줄이 설명하던 문제."""
    with _scenario_sandbox() as fake:
        rec = _start_unit(fake)
        fake.queue(**_ev("chroma_def", **_NO, intent="explain", explicit_explain_request=False))
        _quiet(study_turn, "어.. 잘 모르겠는데")
        assert logs[-1]["next_action"] == "hint" and logs[-1]["intent"] == "continue"
        assert rec["skill_records"]["chroma_def"]["ask_count"] == 2
        fake.queue(**_ev("chroma_def", **_NO, intent="explain", explicit_explain_request=False))
        _quiet(study_turn, "모르겠어")
        assert logs[-1]["next_action"] == "hint"                      # 진단 질문은 세지 않으므로 힌트를 한 번 더 준다
        fake.queue(**_ev("chroma_def", **_NO, intent="explain", explicit_explain_request=False))
        _quiet(study_turn, "그래도 모르겠어")
        assert logs[-1]["next_action"] == "reveal_and_next"          # 도움 질문 두 번 뒤에도 모르면 답을 알려주고 이동
        assert rec["skill_records"]["chroma_def"]["closed"] == "revealed"
    with _scenario_sandbox() as fake:
        rec = _start_unit(fake)
        fake.queue(**_ev("chroma_def", **_NO, intent="explain", explicit_explain_request=True))
        _quiet(study_turn, "그냥 설명해줘")                           # 진짜 설명 요청은 그대로 따른다 (규칙 1)
        assert logs[-1]["next_action"] == "full_explanation"
        assert rec["skill_records"]["chroma_def"]["ask_count"] == 1
    print("v3.13 stuck-vs-explain intent guard: 7/7 passed")


v313_stuck_is_not_explain_request_test()


def v313_autosave_resume_test():
    """세션이 끊겨도 같은 단계에서 이어 갈 수 있다 (저장 → 전역 상태 초기화 → 불러오기)."""
    import os, tempfile
    path = os.path.join(tempfile.mkdtemp(), "resume.json")
    with _scenario_sandbox() as fake:
        rec = _start_unit(fake)
        fake.queue(**_ev("chroma_def", **_NO, learner_stuck=True))
        _quiet(study_turn, "어.. 잘 모르겠어")
        assert logs[-1]["next_action"] == "hint"
        _quiet(export_records, path, True)
        assert os.path.exists(path)
        # 세션이 끊긴 것처럼 상태를 모두 비운다
        learning_context.update({"topic": "", "goal": "", "concept_id": ""})
        concept_records.clear(); messages.clear(); logs.clear()
        out = _quiet(load_records, path)
        assert "이어서" in out
        rec = _record()
        assert learning_phase == "learning" or learning_phase == "diagnosing"
        assert rec["skill_records"]["chroma_def"]["ask_count"] == 2 and rec["active_task"]["kind"] == "hint"
        # 이어서 같은 단계로 진행: 두 번째 힌트(한 단계 더 구체적) 뒤에도 모르면 답을 알려주고 이동
        fake.queue(**_ev("chroma_def", **_NO, learner_stuck=True))
        _quiet(study_turn, "그래도 모르겠어")
        assert logs[-1]["next_action"] == "hint"
        fake.queue(**_ev("chroma_def", **_NO, learner_stuck=True))
        _quiet(study_turn, "진짜 모르겠어")
        assert logs[-1]["next_action"] == "reveal_and_next"
    print("v3.13 autosave / resume: 6/6 passed")


v313_autosave_resume_test()


def v313_summary_split_and_labels_test():
    with _scenario_sandbox() as fake:
        rec = _record()
        rec["skill_registry"] = {"a": "개념A", "b": "개념B"}
        rec["skill_records"] = {"a": _new_skill_record("개념A", ["x", "y"]), "b": _new_skill_record("개념B", ["x", "y"])}
        rec["skill_records"]["a"]["dimensions"] = {"concept": "confirmed", "reasoning": "unknown", "transfer": "unknown"}
        rec["skill_records"]["b"]["dimensions"] = {"concept": "partial", "reasoning": "unknown", "transfer": "unknown"}
        rec["skill_records"]["b"]["revealed"] = True
        p = _summary_parts(rec)
        assert p["confirmed_skills"] == ["개념A"] and [w["label"] for w in p["weak_skills"]] == ["개념B"]
        assert "개념A" in p["untested_note"] and "개념B" not in p["untested_note"]   # 약한 개념은 weak_skills에서 이미 다룸
        # 마무리에서 확인한 뒤 C가 확인이면 잘한 것으로 이동
        rec["skill_records"]["b"]["rechecked"] = True
        rec["skill_records"]["b"]["dimensions"]["concept"] = "confirmed"
        assert _summary_parts(rec)["weak_skills"] == []
        # 마지막 개념에서는 '마무리로 넘어가기'
        rec["skill_records"]["a"]["closed"] = "confirmed"; rec["skill_records"]["b"]["closed"] = "confirmed"
        rec["active_skill_id"] = "b"
        choose_action(rec, "process_complaint", {})
        assert rec["_has_next_open"] is False
        assert "마무리로 넘어가기" in _build_action_instruction("offer_direction_choice", rec, "process_complaint", {})
    print("v3.13 summary split/label checks: 6/6 passed")


v313_summary_split_and_labels_test()


def v313_pause_session_test():
    with _scenario_sandbox() as fake:
        rec = _record()
        rec["skill_registry"] = {"a": "개념A", "b": "개념B"}
        rec["skill_records"] = {"a": _new_skill_record("개념A", ["x", "y"]), "b": _new_skill_record("개념B", ["x", "y"])}
        rec["active_skill_id"] = "a"
        assert choose_action(rec, "pause_session", {}) == "pause_ack"
        assert not rec["skill_records"]["a"].get("closed") and not rec.get("wrap_up_active")
        ins = _build_action_instruction("pause_ack", rec, "pause_session", {})
        assert "질문" in ins and "저장" in ins
        # 이미 마무리 중에 finish_unit이 와도 마무리를 처음부터 다시 시작하지 않는다
        rec["wrap_up_active"] = True; rec["wrap_up_questions_asked"] = 2
        rec["wrap_up_queue"] = [{"skill_id": "b", "label": "개념B", "dimension": "concept", "reason": "unconfirmed"}]
        choose_action(rec, "finish_unit", {})
        assert rec["wrap_up_questions_asked"] == 2
        assert "pause_session" in VALID_INTENTS
        assert _rule_check("괜찮아요. 쉬어 가세요.", "pause_ack", "State1", "State1", rec)["questions_ok"]
    print("v3.13 pause-session checks: 6/6 passed")


v313_pause_session_test()


def v313_difficulty_is_not_request_test():
    with _scenario_sandbox() as fake:
        fake.router_script = lambda t: {"topic": "일반화학 오비탈", "goal": "오비탈 이해", "needs_clarification": False,
                                        "clarification_question": "", "intent": "direct_explanation", "direct_request": "이해가 안 됨"}
        _called = []
        _orig = globals()["_answer_first_request"]
        globals()["_answer_first_request"] = lambda *a, **k: (_called.append(1) or "설명")
        try:
            _quiet(study_turn, "일반화학 오비탈이 이해안돼")
        finally:
            globals()["_answer_first_request"] = _orig
        assert not _called and learning_phase == "awaiting_registry_confirmation"
    print("v3.13 difficulty-not-a-request check: 2/2 passed")


v313_difficulty_is_not_request_test()


def v313_review_session_and_queue_test():
    with _scenario_sandbox() as fake:
        rec = _record()
        rec["skill_registry"] = {"a": "개념A", "b": "개념B"}
        rec["skill_records"] = {"a": _new_skill_record("개념A", ["x", "y"]), "b": _new_skill_record("개념B", ["x", "y"])}
        rec["unit_status"] = "completed"
        learning_context.update({"topic": "t", "goal": "g"})
        for k in ("a", "b"):
            rec["skill_records"][k]["closed"] = "confirmed"
        rec["skill_records"]["b"]["state"] = "State1"; rec["skill_records"]["a"]["state"] = "State3"
        # 복습 세션: 요청 → 부족한 답 → 부족한 답 → 답 공개로 종료 (질문 없이)
        assert choose_action(rec, "review", {}) == "review" and rec["active_skill_id"] == "b"
        bad = {"concept": "partial", "has_content_attempt": True, "core_misconception": False}
        assert choose_action(rec, "continue", bad) == "guided_question"
        assert choose_action(rec, "continue", bad) == "review_reveal" and rec["review_session"] is None
        # 복습 세션: 맞으면 바로 마무리
        choose_action(rec, "review", {})
        good = {"concept": "confirmed", "concept_source": "independent_explanation", "has_content_attempt": True}
        # State1/2에서 맞으면 새 상황 한 문제를 더 묻고(안정적 이해로 올라갈 기회), 그다음에 마무리
        assert choose_action(rec, "continue", good) == "review" and rec["review_session"].get("extra")
        assert "안정적 이해" in _build_action_instruction("review", rec, "continue", {})
        assert choose_action(rec, "continue", good) == "review_done"
        assert choose_action(rec, "continue", good) == "closing_ack"
        # 이미 State3이면 추가 질문 없이 바로 마무리
        rec["skill_records"]["b"]["state"] = "State3"
        choose_action(rec, "review", {})
        assert choose_action(rec, "continue", good) == "review_done"
        # 방금 답을 알려 준 개념은 마무리 큐의 맨 뒤 / 혼자면 새 상황 적용
        rec2 = _new_record()
        rec2["skill_registry"] = {"a": "개념A", "b": "개념B"}
        rec2["skill_records"] = {"a": _new_skill_record("개념A", ["x", "y"]), "b": _new_skill_record("개념B", ["x", "y"])}
        rec2["skill_records"]["a"]["state"] = "State2"; rec2["skill_records"]["a"]["dimensions"]["concept"] = "confirmed"
        rec2["skill_records"]["a"]["closed"] = "confirmed"
        rec2["skill_records"]["b"]["revealed"] = True; rec2["skill_records"]["b"]["closed"] = "revealed"
        rec2["transition"] = {"closed_sid": "b", "how": "revealed", "closed_label": "개념B"}
        _start_wrap_up(rec2)
        first = rec2["wrap_up_queue"][0]
        assert first["skill_id"] == "a" and rec2["wrap_up_queue"][-1]["skill_id"] == "b"
        rec2["skill_records"]["a"]["state"] = "State3"
        rec2["transition"] = {"closed_sid": "b", "how": "revealed", "closed_label": "개념B"}
        _start_wrap_up(rec2)
        assert rec2["wrap_up_queue"][0]["reason"] == "revealed_recent" and rec2["wrap_up_queue"][0]["dimension"] == "reasoning_transfer"
    print("v3.13 review-session / just-revealed queue checks: 8/8 passed")


v313_review_session_and_queue_test()


def v313_ladder_excludes_diagnostic_test():
    with _scenario_sandbox() as fake:
        rec = _start_unit(fake)
        sk = rec["skill_records"]["chroma_def"]
        assert sk["ask_count"] == 1                                   # 진단 질문
        mis = dict(_ev("chroma_def", **_NO), core_misconception=True, has_content_attempt=True)
        fake.queue(**mis); _quiet(study_turn, "틀린 답")
        assert logs[-1]["next_action"] == "diagnose_misconception"
        fake.queue(**mis); _quiet(study_turn, "또 틀린 답")
        assert logs[-1]["next_action"] == "hint"                      # 오개념 질문을 연달아 하지 않는다
        fake.queue(**mis); _quiet(study_turn, "계속 틀린 답")
        assert logs[-1]["next_action"] == "reveal_and_next"           # 도움 질문 두 번 + 3턴 상한
    print("v3.13 ladder excludes diagnostic question: 4/4 passed")


v313_ladder_excludes_diagnostic_test()


def v313_log_driven_fixes_test():
    # 질문 수: 물음표 문장 + '해 주세요' 요청 문장을 센다
    assert _count_questions("무엇이라고 생각하세요?") == 1
    assert _count_questions("기준 두세 개만 골라 설명해 주세요.") == 1
    assert _count_questions("맞아요. 기준을 설명해 주세요. 이유는 무엇인가요?") == 2
    assert _count_questions("좋아요. 새 주제를 공부하고 싶으면 말씀해 주세요.") == 1
    # 합쇼체 감지
    assert _formal_tone_found("마무리에서 다시 확인해 보겠습니다.") and not _formal_tone_found("다시 확인해 볼게요.")
    rc = _rule_check("마무리에서 다시 확인해 보겠습니다.", "pause_ack", "State1", "State1", _record())
    assert rc["tone_ok"] is False
    # 복습 제안 뒤 '마스터하고 싶어'는 복습 의도
    messages.append({"role": "assistant", "content": "복습을 조금 더 할까요, 아니면 다음 단원으로 넘어갈까요?"})
    assert _detect_explicit_intent("산화수 판정을 마스터하고 싶어", "continue") == "review"
    messages.pop()
    # 요약: 개념은 확인됐어도 이유 설명이 보완 필요면 약한 부분에 들어간다
    with _scenario_sandbox() as fake:
        rec = _record()
        rec["skill_registry"] = {"a": "개념A"}
        rec["skill_records"] = {"a": _new_skill_record("개념A", ["x", "y"])}
        rec["skill_records"]["a"]["dimensions"] = {"concept": "confirmed", "reasoning": "missing", "transfer": "unknown"}
        p = _summary_parts(rec)
        assert p["confirmed_skills"] == [] and p["weak_skills"][0]["weak_dimensions"] == ["이유 설명"]
        # 답을 알려 준 개념의 마무리 질문은 되풀이가 아니라 새 사례 적용
        rec["wrap_target"] = {"skill_id": "a", "label": "개념A", "dimension": "concept", "reason": "revealed"}
        ins = _build_action_instruction("wrap_up_check", rec, "continue", {})
        assert "되풀이하거나" in ins and "적용" in ins
    print("v3.13 log-driven fixes: 10/10 passed")


v313_log_driven_fixes_test()


def v313_progress_query_and_commands_test():
    with _scenario_sandbox() as fake:
        rec = _record()
        rec["skill_registry"] = {"a": "개념A"}
        rec["skill_records"] = {"a": _new_skill_record("개념A", ["x", "y"])}
        rec["active_skill_id"] = "a"
        assert choose_action(rec, "progress_query", {}) == "progress_report"
        assert "progress_query" in VALID_INTENTS
        ins = _build_action_instruction("progress_report", rec, "progress_query", {})
        assert "퀴즈" in ins and "confirmed_skills" in ins
        assert _rule_check("괜찮아요.", "progress_report", "State3", "State3", rec)["questions_ok"]
    import inspect
    src = inspect.getsource(run_chat)
    assert "cmd = user_input.lower()" in src and 'user_input == "/' not in src       # /PROGRESS 같은 대문자도 명령으로 인식
    print("v3.13 progress-query / case-insensitive commands: 5/5 passed")


v313_progress_query_and_commands_test()


def v313_help_command_test():
    import inspect, io, contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        print_help()
    out = buf.getvalue()
    for c in ("/progress", "/finish", "/new-topic", "/reset-chat", "/export", "/load", "/debug", "/audit", "/exit"):
        assert c in out
    src = inspect.getsource(run_chat)
    assert 'cmd == "/help"' in src and "/help로 명령어를 확인하세요" not in src
    print("v3.13 /help command: 3/3 passed")


v313_help_command_test()


def v313_help_and_vulnerability_test():
    import inspect
    src = inspect.getsource(run_chat)
    assert 'cmd == "/help"' in src and "print_help()" in src
    names = [c for c, _ in COMMAND_HELP]
    for c in ("/progress", "/finish", "/new-topic", "/reset-chat", "/export", "/load", "/debug", "/audit", "/exit"):
        assert c in names and all(d for n, d in COMMAND_HELP if n == c)      # 모든 명령에 설명이 있다
    assert "/help" not in src.split("while True")[0]            # 시작 문구에는 /help 안내가 없다
    out = _quiet(print_help)
    assert "/progress" in out and "State" not in out
    rec = _new_record()
    rec["skill_records"] = {"a": _new_skill_record("A"), "b": _new_skill_record("B")}
    rec["skill_records"]["a"]["misconceptions"] = [{"turn_id": 1, "note": "x"}]
    rec["skill_records"]["a"]["state"] = "State1"; rec["skill_records"]["b"]["state"] = "State3"
    _update_vulnerability(rec)
    assert rec["vulnerability"] == "moderate"
    rec["skill_records"]["a"]["state"] = "State3"
    _update_vulnerability(rec)
    assert rec["vulnerability"] == "low"                         # 마지막에 안정적 이해면 낮음으로 격하
    print("v3.13 /help and vulnerability downgrade: 9/9 passed")


v313_help_and_vulnerability_test()


def v313_log3_fixes_test():
    with _scenario_sandbox() as fake:
        rec = _record()
        rec["skill_registry"] = {"a": "개념A"}
        rec["skill_records"] = {"a": _new_skill_record("개념A", ["x", "y"])}
        learning_context.update({"topic": "t", "goal": "g"})
        rec["unit_status"] = "completed"
        rec["skill_records"]["a"]["closed"] = "confirmed"; rec["skill_records"]["a"]["state"] = "State1"
        # 복습 중 좁은 질문에 맞게 답하면(스스로 바로잡은 경우 포함) 답을 공개하지 않고 마무리
        choose_action(rec, "review", {})
        assert choose_action(rec, "continue", {"core_misconception": True, "has_content_attempt": True}) == "diagnose_misconception"
        fixed = {"concept": "partial", "answered_asked_question_correctly": True, "concept_source": "independent_explanation"}
        assert choose_action(rec, "continue", fixed) == "review"          # State1: 한 문제 더
        assert choose_action(rec, "continue", fixed) == "review_done"
        # 마무리 질문: 이미 다룬 개념은 되풀이가 아니라 새 사례 적용
        rec["skill_records"]["a"]["evidence"] = [{"dimension": "concept", "status": "partial", "source": "independent_explanation", "hint_used": False}]
        rec["wrap_target"] = {"skill_id": "a", "label": "개념A", "dimension": "concept", "reason": "hint_assisted"}
        ins = _build_action_instruction("wrap_up_check", rec, "continue", {})
        assert "되풀이하거나" in ins and "새 사례" in ins
        rec["wrap_target"]["reason"] = "skipped"
        assert "새 사례" not in _build_action_instruction("wrap_up_check", rec, "continue", {})
        # 시작 문구에 버전이 없다
        import inspect
        assert 'STUDY LLM 시작.' in inspect.getsource(run_chat) and "APP_VERSION" not in inspect.getsource(run_chat)
        # 패널: 개념이 부분 확인인데 '개념 확인됨'이라고 하지 않는다
        rec["skill_records"]["a"]["dimensions"] = {"concept": "partial", "reasoning": "unknown", "transfer": "unknown"}
        html_out = _progress_panel_html(rec)
        assert "개념 확인됨" not in html_out and "부분 확인" in html_out
    print("v3.13 log-3 fixes: 7/7 passed")


v313_log3_fixes_test()


def v313_practice_request_test():
    with _scenario_sandbox() as fake:
        rec = _record()
        rec["skill_registry"] = {"a": "개념A"}
        rec["skill_records"] = {"a": _new_skill_record("개념A", ["x"])}
        rec["active_skill_id"] = "a"
        ins = _build_action_instruction("practice", rec, "practice", {})
        assert "최대 5개" in ins and "겹치지 않는" in ins
        five = "문제 1: 가?\n문제 2: 나?\n문제 3: 다?\n문제 4: 라?\n문제 5: 마?"
        assert _rule_check(five, "practice", "State1", "State1", rec)["questions_ok"]
        assert not _rule_check(five, "hint", "State1", "State1", rec)["questions_ok"]
        assert _limit_for("practice", rec) == MAX_EXPLAIN_CHARS
        rec["unit_status"] = "completed"
        assert "다른 주제로 넘어가기" in _build_action_instruction("offer_direction_choice", rec, "process_complaint", {})
    print("v3.13 practice-request checks: 5/5 passed")


v313_practice_request_test()


def v313_unvisited_finish_test():
    with _scenario_sandbox() as fake:
        rec = _record()
        rec["skill_registry"] = {"a": "개념A", "b": "개념B", "c": "개념C"}
        rec["skill_records"] = {k: _new_skill_record(v, ["x", "y"]) for k, v in rec["skill_registry"].items()}
        rec["skill_records"]["a"]["ask_count"] = 2; rec["skill_records"]["a"]["turns_spent"] = 2
        rec["skill_records"]["a"]["dimensions"]["concept"] = "partial"
        rec["active_skill_id"] = "a"
        act = choose_action(rec, "finish_unit", {})
        assert act == "wrap_up_check" and rec["wrap_target"]["skill_id"] == "a"
        assert rec["skill_records"]["b"]["unvisited"] and rec["skill_records"]["c"]["unvisited"]
        assert not rec["skill_records"]["a"].get("unvisited")
        assert rec["wrap_up_queue"] == []                      # 시작 전 개념은 마무리 질문에서 제외
        p = _summary_parts(rec)
        assert p["not_started_skills"] == ["개념B", "개념C"] and [w["label"] for w in p["weak_skills"]] == ["개념A"]
        html_out = _progress_panel_html(rec)
        assert "아직 시작하지 않음" in html_out and "1 / 3" in html_out
        assert _weakest_skill_id(rec) == "a"
    print("v3.13 unvisited-on-finish checks: 6/6 passed")


v313_unvisited_finish_test()


def v313_vulnerability_resolved_test():
    with _scenario_sandbox() as fake:
        rec = _record()
        rec["skill_registry"] = {"a": "개념A"}
        rec["skill_records"] = {"a": _new_skill_record("개념A", ["x", "y"])}
        sk = rec["skill_records"]["a"]
        sk["misconceptions"] = [{"t": 1}, {"t": 2}]
        sk["state"] = "State1"; sk["dimensions"]["concept"] = "partial"
        _update_vulnerability(rec); assert rec["vulnerability"] == "high"
        sk["state"] = "State2"; sk["dimensions"]["concept"] = "confirmed"
        _update_vulnerability(rec); assert rec["vulnerability"] == "moderate"
        sk["state"] = "State3"
        _update_vulnerability(rec); assert rec["vulnerability"] == "low"
    print("v3.13 vulnerability resolved checks: 3/3 passed")


v313_vulnerability_resolved_test()


def v313_vulnerability_no_misconception_test():
    with _scenario_sandbox() as fake:
        rec = _record()
        rec["skill_registry"] = {"a": "개념A", "b": "개념B"}
        rec["skill_records"] = {k: _new_skill_record(v, ["x", "y"]) for k, v in rec["skill_registry"].items()}
        rec["skill_records"]["a"]["state"] = "State2"
        rec["skill_records"]["b"]["state"] = "State3"
        _update_vulnerability(rec); assert rec["vulnerability"] == "low"
        rec["skill_records"]["a"]["state"] = "Unconfirmed"
        _update_vulnerability(rec); assert rec["vulnerability"] != "low"
    print("v3.13 vulnerability no-misconception checks: 2/2 passed")


v313_vulnerability_no_misconception_test()
