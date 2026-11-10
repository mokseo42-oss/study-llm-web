"""STUDY LLM controller core — notebook v3.13 port for the web.

Generated from STUDY_LLM_modified.ipynb (cells 0-4) by scripts/make_core.py.
Controller logic, prompts and state rules are unchanged; only Colab/IPython I/O was replaced
and auxiliary rule 2 (cross-unit vulnerability re-check) was added.
"""



import json
import os
import re
import html
from datetime import datetime
from openai import OpenAI

# 웹 버전: client 는 요청마다 web/runtime.py 가 주입한다 (서버 환경변수 OPENAI_API_KEY 또는 사용자 키).
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY") or "unset")
MODEL = os.environ.get("OPENAI_MODEL", "gpt-5.5")  # 계정에서 사용 가능한 모델명으로 변경 가능


# --- IPython display 대체 (노트북 밖에서도 동작) ---------------------------------
class HTML:
    kind = "html"
    def __init__(self, data):
        self.data = str(data)


class Markdown:
    kind = "markdown"
    def __init__(self, data):
        self.data = str(data)


def display(obj):
    """노트북에서는 IPython.display, 웹에서는 runtime 이 이 함수를 교체해 출력을 수집한다."""
    print(getattr(obj, "data", obj))


def _trace_event(event):
    """웹 연구자 모드용 추적 이벤트 (기본은 아무 것도 하지 않음). runtime 이 교체한다."""
    return None

APP_VERSION = "3.13"
MAX_RESPONSE_CHARS = 300      # 규칙 2: 일반 응답 약 300자 이내
MAX_EXPLAIN_CHARS = 700       # 설명·정답 안내·마무리 요약처럼 사용자가 설명을 받는 턴의 상한
MAX_HINT_CHARS = 200          # 규칙 6: 힌트·유도 질문은 한 단계만, 짧게
MAX_QUESTIONS = 1             # 규칙 2: 한 턴에 학습 질문 1개
MAX_ASKS_PER_SKILL = 2        # 수정 규칙 2·6: 진단 질문을 제외하고, 같은 개념에서 도움 질문(유도 질문·힌트)은 최대 2번
MAX_TURNS_PER_SKILL = 3       # 수정 규칙 7: 하위 개념당 대화 최대 3턴
MAX_WRAPUP_QUESTIONS = 3      # 규칙 10: 마무리 확인 최대 3문제
SHOW_CONTROLLER_DEBUG = False  # Set True to show developer diagnostics after each turn
SAVE_FILE = "study_llm_v3_13_records.json"

VALID_STATES = ["Unconfirmed", "State1", "State2", "State3"]
VALID_STATUS = ["confirmed", "partial", "missing", "unknown"]
VALID_SOURCES = [
    "independent_explanation", "independent_transfer",
    "hint_assisted", "ai_echo", "answer_only", "unknown"
]
VALID_INTENTS = [
    "continue", "explain", "practice", "skip_check",
    "change_goal", "finish_unit", "review", "next_unit", "process_complaint", "pause_session", "progress_query"
]


START_ROUTER_PROMPT = r"""
You are the learning-start intent router for STUDY LLM. Do not reduce every learner message to a topic name.
Return JSON only with keys: topic, goal, needs_clarification, clarification_question, intent, direct_request.
Allowed intent values: "structured_learning", "study_strategy", "direct_explanation", "practice", "other".
Rules:
- Extract the specific learning topic from the complete message. Preserve both course and topic when useful, but use the specific topic as topic.
- Identify what the learner is asking you to DO, not just what subject they mention.
- If the learner asks how to memorize, remember, retain, or study material more effectively (e.g. "암기법 알려줘", "내용이 안 외워져", "어떻게 외우면 돼?"), set intent="study_strategy". Give a topic-specific study-strategy response before proposing a sub-concept map. Do not silently replace this request with automatic topic decomposition.
- Only a LITERAL request counts as an explanation request: "설명해줘", "알려줘", "가르쳐줘", "~가 뭐야?". Statements of difficulty or confusion ("이해안돼", "어려워", "모르겠어", "헷갈려") are NOT requests: use intent="structured_learning" and direct_request="". The tutor first checks what the learner knows.
- If the learner asks for an explanation first, set intent="direct_explanation".
- If the learner asks to solve or practice problems, set intent="practice".
- If the learner wants to begin structured learning or gives a general request for help understanding a topic, set intent="structured_learning".
- If the topic is too broad or missing, set topic="", needs_clarification=true, and ask one concise question.
- If a specific topic is stated (e.g. enzymes, cell respiration, genetics, molecular orbital theory), preserve it concisely.
- Preserve the learner's stated goal and requested format. Do not replace a specific request with a generic goal.
- All learner-facing Korean must use polite Korean honorific speech (해요체).
- direct_request: copy, in the learner's own words, everything the learner explicitly asked you to DO besides being quizzed (e.g. "explain the principle", "tell me how to memorize it", "make 5 exam questions", "solve this problem"). Use an empty string if there is none. NEVER drop such a request. It is answered before any diagnostic question. Fill direct_request even when you also need a clarification question.
- If the learner message contains both a request to explain and a request for a study method, set intent="study_strategy" and keep both parts in direct_request.
- Do not assess knowledge, assign skill IDs, extract C/R/T evidence, or infer a State.
"""


START_CONFIRM_PROMPT = """You are a learning assistant. The learner has confirmed the generated sub-concept map. Ask exactly one concise, open-ended diagnostic question about the first or most foundational sub-concept. Do not reveal definitions, formulas, answers, or hints. The question must contain no answer choices, no fill-in-the-blank, no sentence starter, and must not state the answer. You MAY name the sub-concept itself in plain words, and you should ask directly and plainly (for example "~에 대해 아는 대로 설명해 볼래요?" or "~는 어떤 역할을 한다고 생각해요?"). Never use riddles, metaphors, or roundabout wording that hides the topic. Write in consistent polite Korean honorific speech (해요체), never 반말. Return only the learner-facing Korean question."""



EVALUATOR_PROMPT = r"""
You are the evidence evaluator for STUDY LLM v3.13. Assess ONLY the learner's latest message in the context supplied.
Do not write a learner-facing answer. Do not choose a final State or learning action. State is computed only by Python. Do not output a State.
Return only valid JSON with these exact keys:
{
 "topic_detected": "",
 "goal_detected": "",
 "skill_id": "one_exact_id_from_known_skills",
 "skill_label": "exact_label_from_known_skills",
 "task_complete": false,
 "task_completion_note": "",
 "intent": "continue|explain|practice|skip_check|change_goal|finish_unit|review|next_unit|process_complaint|pause_session|progress_query",
 "has_content_attempt": false,
 "concept": "confirmed|partial|missing|unknown",
 "reasoning": "confirmed|partial|missing|unknown",
 "transfer": "confirmed|partial|missing|unknown",
 "concept_source": "independent_explanation|independent_transfer|hint_assisted|ai_echo|answer_only|unknown",
 "reasoning_source": "independent_explanation|independent_transfer|hint_assisted|ai_echo|answer_only|unknown",
 "transfer_source": "independent_explanation|independent_transfer|hint_assisted|ai_echo|answer_only|unknown",
 "core_misconception": false,
 "misconception_note": "",
 "calculation_or_notation_error_only": false,
 "evidence_note": "",
 "learner_stuck": false,
 "same_strategy_failed": false,
 "key_points_covered": 0,
 "missing_key_point": "",
 "out_of_scope_error": "",
 "answered_asked_question_correctly": false,
 "explicit_explain_request": false
}

Evaluation rules:
Intent interpretation:
- Determine intent from the full learner message and recent dialogue, not from a fixed keyword list.
- Recognize natural paraphrases, colloquial expressions, indirect requests, and polite/informal Korean.
- Distinguish continue, explain, practice, skip_check, change_goal, finish_unit, review, and next_unit by what the learner is trying to do in the current context.
- If the learner asks to explain without solving, choose explain. (The tutor itself adds one short check question after every explanation.)
- If the learner clearly changes subject or goal, choose change_goal; do not treat it as evidence for the current skill.
- If intent is genuinely ambiguous, choose continue only when the learner is substantively answering the active task; otherwise choose the closest non-evidential intent and explain uncertainty in evidence_note.
- A question, self-rating ("I know", "I don't know"), topic/goal statement, or request for an explanation is not a content attempt and is not evidence of understanding or misunderstanding. Set has_content_attempt=false and all three dimensions to unknown for these messages. The JSON schema includes has_content_attempt; always return it.
- Assess Concept, Reasoning, Transfer separately. A correct answer alone does not confirm reasoning or transfer.
- SKILL ROUTING IS STRICT: choose exactly ONE skill_id from CONTEXT.known_skills. Copy its exact label. Never invent an ID, rename a skill, merge two registry skills, or assess evidence for multiple skills in one turn. If the message spans multiple skills, assess only the active_task skill; if no active task, choose the single most directly addressed registry skill. If none fits, set skill_id="__UNMAPPED__", has_content_attempt=false, all dimensions="unknown", and state briefly that the message does not map to the current learning unit. Never instruct the learner to call add_skill(). Use active_task.skill_id only as a routing hint, NOT as an override. Re-read active_task.prompt and required_outcome, then select the registry skill that the task actually tests. If the task prompt clearly tests a different skill from active_task.skill_id, select the skill matching the task prompt. If the prompt is ambiguous or spans multiple skills, choose the single most directly assessed skill; if no single skill is defensible, use __UNMAPPED__ and do not record evidence.
- If an active_task is present, assess whether the learner completed THAT exact task using active_task.prompt and active_task.required_outcome. Set task_complete=true only if the requested task is adequately completed. If the task is partly answered, task_complete=false and identify the missing part. If the learner explicitly asks to stop/skip/change task, do not pretend it was completed.
- Use ai_echo when the learner merely repeats wording or reasoning just supplied by the AI. Do not count it as independent evidence or as a learner misconception.
- Use hint_assisted when the answer was produced after a hint or partial solution. It is progress, but not hint-free independent evidence.
- independent_explanation means the learner independently explains the concept/reasoning in their own words.
- independent_transfer means the learner independently applies the concept to a genuinely new situation without hints.
- A numerical answer or formula substitution can support transfer/application only when it solves a genuinely new task. It does NOT establish independent verbal reasoning. Do not label the same calculation as both independent_transfer and independent_explanation unless the learner separately explains why. A routine calculation that repeats a just-taught formula is not automatically transfer.
- Set has_content_attempt=true only when the learner actually attempts to explain, answer, reason, or apply the target concept in the latest message. A request, self-rating, or statement of confusion is not an attempt.
- Use missing only when an actual content attempt clearly demonstrates a gap or incorrect understanding in that dimension. Missing does NOT mean no evidence was provided. If no attempt was made or the dimension was not addressed, use unknown.
- If has_content_attempt=false, core_misconception must be false and misconception_note must be empty.
- If a dimension was not demonstrated in the latest message, use unknown; do not copy prior status into the latest assessment.
- Mark core_misconception only for a substantive conceptual error, not arithmetic, units, spelling, or notation slips.
- If ambiguous, use unknown/partial and explain the uncertainty in evidence_note. Do not mark an entire skill missing because one sub-part is unanswered; evaluate only dimensions actually attempted.
- `missing` means demonstrated deficiency in a dimension, not merely an unmentioned dimension.
- If the learner gives a correct result plus a wrong conceptual explanation, preserve the distinction: the result may support transfer, while reasoning may be missing or partial.
- Detect explicit user choices: asking for direct explanation, practice questions, skipping a check, changing the topic/goal, finishing, reviewing, or moving to the next unit.
- Never infer that the user wants to skip a check just because they give a short answer.
- Do not infer a new topic/goal unless the learner states it clearly.

v3.13 KEY-POINT AND LENIENCY RULES:
- CONTEXT.active_skill_key_points lists the 2-3 core elements of the active skill. A concept answer is "confirmed" when it carries the core meaning of the key points IN THE LEARNER'S OWN WORDS, even if it is short, informal, or phrased differently from a textbook. For a simple concept, covering 1-2 key points is enough. NEVER mark an answer partial merely because it is short or terse.
- SCOPE RULE: judge the answer only against what the previous tutor question actually asked. If the question asked the learner to pick or give a few examples ("아는 것 두세 개를 골라"), a correct answer with two or three accurate items covers the concept; do NOT withhold confirmation because other items of the concept were not mentioned. Never require more than the question requested.
- If the learner states something clearly wrong that was NOT part of what the tutor asked (an extra claim outside the question), do not let it change the judgment of the asked scope, but put a short Korean description of the wrong claim in out_of_scope_error (empty string if none).
- answered_asked_question_correctly: true only when the learner's answer is correct for exactly what the tutor's previous question asked (a single case, a single rule), regardless of other key points of the skill. A learner who first answers wrongly and then corrects themselves correctly in the next message also counts as true.
- Count the covered key points in key_points_covered. Put the single most important missing element in missing_key_point (empty string if nothing important is missing). Only one missing element at a time.
- Reasoning needs a correct cause / why link in the learner's own words. Transfer needs a correct application to a genuinely new situation.
- Source classification: if the tutor's previous message was a plain open diagnostic question (no answer choices, no blank, no leading cue), the answer is independent_explanation. Use hint_assisted ONLY when the tutor's immediately preceding message actually contained a hint, answer choices, a fill-in blank, or the key term itself. A correct answer must never be downgraded to unknown just because it is short.
- core_misconception is true ONLY when the learner confidently asserts a wrong belief. A learner who is unsure, thinks aloud, offers several candidates (even if one is right), or asks the tutor a clarifying question has NOT shown a misconception: set core_misconception=false and treat it as a partial/unknown attempt.
- If the tutor explained or revealed the answer within the last three turns and the learner's answer mostly restates those same points, set the source to ai_echo, not independent.
- NOT echo (use independent_explanation / independent_transfer): a short correct answer that names or defines a single term the question asked about; and a correct procedure or value applied to a NEW case (different substance, different numbers) even if the procedure itself was mentioned earlier. Echo means the answer repeats the tutor's own wording or the same example, not merely the same correct idea.
- During wrap-up of a concept whose answer the tutor revealed earlier, a correct application of its key points to a new case also confirms the concept.
- A reply that only affirms or jokes ("응", "당연하지 ㅋㅋ", "ㅇㅋ") has no content: has_content_attempt=false and all dimensions unknown.
- If the learner complains about the pace or method of learning (for example "정의만 계속 물어볼 거야?", "왜 같은 걸 계속 물어봐", "너무 길어") instead of answering, choose intent="process_complaint".
- If the learner says they are tired, discouraged or leaving and wants to stop for now ("여기까지만 할게", "나중에 다시 할래", "너무 어렵다 다시 강의 자료 보고 올게", "오늘은 그만"), choose intent="pause_session". This is NOT review and NOT finish_unit (finish_unit means "wrap up and check what is left now"). A remark like "다시 보고 올게" is a pause, never a request for more questions.
- After the tutor offered a review or next step, if the learner says they want to study a concept more or master it ("마스터하고 싶어", "더 해볼래", "복습할래"), choose intent="review".
- If the learner asks about their own progress or what to review ("내 학습 현황이 어때?", "뭘 복습해야 해?", "어디가 부족해?"), choose intent="progress_query". It is a question about the record, not a request to be quizzed.
- If the learner asks to move on to the next sub-concept ("다음으로 넘어가자", "이건 아니까 넘겨"), choose skip_check.
- If the learner asks a new question or makes a request (explain, make exam questions, how to memorize), it is not evidence: choose explain or practice and set has_content_attempt=false.
- "모르겠어", "잘 모르겠는데", "어려워", "몰라" are NOT requests to explain. They are a stuck signal: intent="continue", has_content_attempt=false, learner_stuck=true, explicit_explain_request=false. Choose intent="explain" ONLY when the learner literally asks to be told or taught ("설명해줘", "알려줘", "답이 뭐야?", "~가 뭐야?") and set explicit_explain_request=true. When unsure, intent="continue".
- Write evidence_note, task_completion_note and misconception_note in KOREAN (한국어), one or two short sentences. Never write them in English.
- During wrap-up (CONTEXT.wrap_up_target is present) judge the skill wrap_up_target.skill_id and only the dimension(s) named in wrap_up_target.dimension ("concept", or "reasoning_transfer" = both reasoning and transfer). Use that skill_id exactly.
"""

RESPONSE_PROMPT = r"""
You are STUDY LLM v3.13, a learning dialogue assistant. Follow the controller instruction exactly.
Write in Korean unless the learner requests another language.
KOREAN TONE RULE: Use consistent polite Korean honorific speech (해요체) in EVERY learner-facing response. Never mix 반말 and 존댓말 within a response or across turns. Prefer natural forms such as "좋아요", "설명해 볼까요?", "말씀해 주세요", "확인해 볼게요". Never use formal endings such as "~습니다", "~입니다", "~겠습니다".
If the learner asks a clarifying question about the tutor's own question (e.g. "이거 말하는 거야?"), restate in one sentence what is being asked, without confirming which candidate is correct, and ask again. Avoid informal endings such as "좋아", "해봐", "말해줘", "할게", "있어". Keep scientific terms and equations unchanged.
Use concise, natural language, generally within 300 Korean characters. Explanation turns (full_explanation, reveal_and_next, wrap_up_summary) may use up to 600 Korean characters.
If the context has out_of_scope_error, add one short clause saying that part may not hold in general and suggesting the learner check it in the course material. Do not teach the correct answer and do not praise that part.
Ask at most ONE learner-facing learning question. Do not ask redundant questions.
Respect the learner's explicit goal and chosen method.
For practice, give exactly ONE atomic task/question per response. If a larger exercise has parts, split them across turns. Do not complete the learner's explanation. Identify at most one missing link and invite the learner to supply it. A question expressing uncertainty is not automatically a request for a full explanation.
When giving a hint, give only one step. Do not jump to a full solution unless the user explicitly asks. During diagnosis, do not reveal the correct definition, formula, relationship, or answer before the learner has attempted the diagnostic question. A diagnostic question must test the learner’s current understanding, not teach the answer inside the question.
After an explanation, check understanding with one meaningful question or short application, not "이해했어?".
Do not repeat an already confirmed check without a reason. If an active task is incomplete, continue that task instead of offering a review/next-unit menu. A task is complete only when its required answer and reasoning are supplied or the learner explicitly skips/stops it.
When a specific sub-concept reaches State3, describe only THAT sub-concept as well-supported. Do not claim the entire topic is mastered if other sub-concepts are Unconfirmed, State1, or State2. Offer a next choice only after the current task is complete or explicitly stopped. A learner's answer is not itself a menu choice.
Do not claim that the learner has mastered an entire subject. Refer only to the current concept.
- Do not present more than one atomic learner task/question in a single response. Split multi-part exercises across turns.
- If an active task is incomplete, continue that exact task; do not offer review/next-topic choices.
- Do not ask the learner to choose a next action unless the controller action is `offer_learner_choice`, `offer_direction_choice` or `wrap_up_summary`.
- Do not state that all C/R/T are confirmed from one correct numerical answer.
- Progress summaries must show each sub-concept's own State. Do not calculate, infer, or display one overall/topic-level State. Never use the status of other skills to judge the active skill.


STRICT EVIDENCE RULES FOR v3.9:
- The skill_id must exactly match one key in known_skills. The Python controller rejects any unknown ID.
- `confirmed` requires positive evidence in the latest learner message. Never use confirmed merely because a previous turn confirmed it.
- Use `partial` when the learner demonstrates a correct but incomplete idea. Use `missing` only when an actual attempted explanation demonstrates a specific gap. Use `unknown` when not addressed.
- Source classification must reflect assistance history in recent_dialogue and active_task. Repeating an AI explanation, following an explicit hint, or answering a guided analogy is not hint-free independent transfer. A task statement that supplies only a new situation, values, and the question (without supplying the governing formula, answer, or solution step) is NOT by itself a hint; a correct self-generated application may count as independent_transfer. If the task statement includes a leading formula, partial solution, worked example, or a cue that gives away the key conceptual step, classify the corresponding evidence as hint_assisted.
- For an analogy supplied by the AI, mark the analogous concept as `hint_assisted` unless the learner independently extends it to a genuinely new situation beyond the supplied mapping.
- Do not call a transfer answer independent_transfer merely because it is in a different domain if the AI supplied the analogy or the exact mapping. A newly generated numerical scenario can be a valid transfer task when it requires the learner to select and apply the principle without a solution cue.
- Keep the evidence dimension-specific. A correct concept statement does not confirm reasoning; a correct analogy does not automatically confirm electrical transfer.

v3.13 DIALOGUE RULES:
- Never ask a question that contains its own answer: no multiple choice, no fill-in-the-blank, no sentence starter to complete, no key terms from the answer, no yes/no question whose answer is obvious. A diagnostic question is open-ended and neutral.
- Never repeat the previous tutor question or merely reword it. When a second ask is needed, make it a smaller, different step (a hint) instead of the same question.
- If the learner's answer already contains the core meaning, accept it plainly in one short sentence and move on. Do not ask for the same thing again or demand more length.
- Never mention internal terms: State, Controller, Evidence, C/R/T, skill ID, registry, 증거, 판정. Talk naturally about the "개념".
- Do not output progress tables, logs, or English sentences (scientific terms may stay).
- reveal_and_next: give the short answer in 1-3 sentences using key_points, say naturally that the concept will be checked again at the end, then ask exactly ONE open diagnostic question about the next concept (if next_skill is present). Never ask the revealed concept again.
- advance_next: acknowledge the answer in one short sentence without teaching more, then ask exactly ONE open diagnostic question about the next concept.
- When controller context has explanation_strategy, explain with that strategy (definition | example | analogy | step_breakdown) and do not reuse a strategy from earlier turns.
- When transition.how is "revealed" and the action is a wrap_up action, first give the short answer for transition.closed_label in 1-2 sentences, then continue with the wrap-up instruction.
"""


# ---------------------------
# Persistent learning records
# ---------------------------
learning_context = {"topic": "", "goal": "", "concept_id": ""}
concept_records = {}
messages = []
logs = []
pending_post_explanation_check = False
learning_phase = "idle"
awaiting_registry_confirmation = False
pending_new_unit = False  # True while collecting a new topic after an explicit subject switch
pending_study_strategy = None  # topic/request while offering study-strategy guidance
pending_start_requests = []    # 주제 확인 중 받은 사용자 요청(설명·암기법·문제 출제 등)을 버리지 않고 모아 둠

HELP_ACTIONS = {"hint", "partial_explanation", "prerequisite_explanation", "full_explanation", "reveal_and_next"}
EXPLANATION_ACTIONS = {"full_explanation", "partial_explanation", "prerequisite_explanation", "reveal_and_next"}
STRATEGIES = ["definition", "example", "analogy", "step_breakdown"]  # 규칙 7: 설명 전략 순환


def _new_record():
    return {
        "state": "Unconfirmed",
        "dimensions": {"concept": "unknown", "reasoning": "unknown", "transfer": "unknown"},
        "latest_dimensions": {"concept": "unknown", "reasoning": "unknown", "transfer": "unknown"},
        "skill_records": {},
        "skill_registry": {},
        "registry_locked": False,
        "active_skill_id": None,
        "active_task": None,
        "practice_session": None,
        "awaiting_learner_choice": False,
        "evidence": [],
        "misconceptions": [],
        "vulnerability": "unknown",
        "help_level": 0,  # 0 question, 1 hint, 2 partial explanation, 3 full explanation
        "same_strategy_stuck_count": 0,
        "last_strategy": None,
        "confirmed_checks": [],
        "unconfirmed_checks": ["concept", "reasoning", "transfer"],
        "unit_status": "in_progress",
        "last_action": None,
        "wrap_up_active": False,
        "wrap_up_questions_asked": 0,
        "wrap_up_queue": [],
        "wrap_target": None,
        "review_offered": False,
        "last_help_sid": None,
        "last_help_turn": 0,
        "transition": None,
        "current_strategy": None
    }


def _clean_key_points(kp):
    """규칙 5: 개념마다 핵심 요소 2~3개 기준표."""
    if not kp:
        return []
    if isinstance(kp, str):
        kp = [kp]
    out = []
    for x in list(kp)[:3]:
        x = str(x).strip()[:80]
        if x:
            out.append(x)
    return out


def _new_skill_record(label, key_points=None):
    return {
        "label": label, "state": "Unconfirmed",
        "dimensions": {"concept": "unknown", "reasoning": "unknown", "transfer": "unknown"},
        "latest_dimensions": {"concept": "unknown", "reasoning": "unknown", "transfer": "unknown"},
        "evidence": [], "misconceptions": [], "state_override": None,
        "help_level": 0, "same_strategy_stuck_count": 0, "last_strategy": None,
        "key_points": _clean_key_points(key_points),
        "ask_count": 0,        # 이 개념에서 던진 질문 수 (상한 MAX_ASKS_PER_SKILL)
        "turns_spent": 0,      # 이 개념에서 쓴 학습자 턴 수 (상한 MAX_TURNS_PER_SKILL)
        "closed": None,        # None | "confirmed" | "revealed" | "skipped"
        "revealed": False,     # 답을 알려주고 넘어간 개념: 마무리 확인 맨 앞
        "needs_recheck": False,
        "strategies_used": []
    }


def _ensure_skill_fields(skill):
    """이전 버전 기록을 불러와도 새 필드가 항상 존재하도록 보정."""
    for k, v in (("key_points", []), ("ask_count", 0), ("turns_spent", 0), ("closed", None),
                 ("revealed", False), ("needs_recheck", False), ("strategies_used", []),
                 ("misconceptions", []), ("evidence", []), ("help_level", 0),
                 ("same_strategy_stuck_count", 0), ("rechecked", False)):
        if k not in skill:
            skill[k] = list(v) if isinstance(v, list) else v
    return skill


def _safe_id(value):
    value = re.sub(r"[^a-zA-Z0-9가-힣_-]", "_", str(value).strip())
    return (value[:70] or "general")


def set_learning_context(topic, goal, concept_id=None, skills=None):
    global learning_phase, awaiting_registry_confirmation
    """Set a learning unit and create/fix its atomic sub-concept registry."""
    learning_context["topic"] = str(topic).strip()
    learning_context["goal"] = str(goal).strip()
    learning_context["concept_id"] = _safe_id(concept_id or topic or "general")
    rec = concept_records.setdefault(learning_context["concept_id"], _new_record())
    messages.clear()
    if skills:
        set_skill_registry(skills, rec)
    elif not rec.get("registry_locked"):
        initialize_skill_registry(rec)
    learning_phase = "learning" if rec.get("registry_locked") else "awaiting_registry_confirmation"
    awaiting_registry_confirmation = False
    print("학습 주제와 목표를 설정했습니다.")
    show_progress()


def set_skill_registry(skills, record=None):
    """Explicitly set atomic skills. Accept dict {id: label}, list of (id,label[,key_points]) or dicts."""
    record = record or _record()
    items = skills.items() if isinstance(skills, dict) else skills
    registry = {}
    key_points = {}
    for item in items:
        if isinstance(item, dict):
            sid, label, kp = item.get("id"), item.get("label"), item.get("key_points")
        else:
            sid, label = item[0], item[1]
            kp = item[2] if len(item) > 2 else None
        sid = _safe_id(sid)
        if sid in registry:
            raise ValueError(f"Duplicate skill id: {sid}")
        registry[sid] = str(label).strip()[:100]
        key_points[sid] = _clean_key_points(kp)
    if not registry:
        raise ValueError("Skill registry cannot be empty")
    # Explicit registry replacement: discard stale skill records so old IDs/evidence
    # cannot leak into the revised map. This function is also used for first creation.
    old_registry = dict(record.get("skill_registry", {}))
    if old_registry and old_registry != registry:
        record["legacy_skill_records"] = record.get("legacy_skill_records", {})
        for old_sid, old_skill in record.get("skill_records", {}).items():
            record["legacy_skill_records"][old_sid] = old_skill
        record["skill_records"] = {}
        record["active_skill_id"] = None
        record["active_task"] = None
    record["skill_registry"] = registry
    record["registry_locked"] = True
    for sid, label in registry.items():
        sk = record["skill_records"].setdefault(sid, _new_skill_record(label, key_points[sid]))
        _ensure_skill_fields(sk)
        sk["label"] = label
        if key_points[sid]:
            sk["key_points"] = key_points[sid]
    return registry


def add_skill(skill_id, label, key_points=None):
    """Explicitly add one new atomic sub-concept without merging existing records."""
    rec = _record()
    sid = _safe_id(skill_id)
    if sid in rec.get("skill_registry", {}):
        raise ValueError(f"Skill already exists: {sid}")
    rec.setdefault("skill_registry", {})[sid] = str(label).strip()[:100]
    rec["registry_locked"] = True
    rec["skill_records"][sid] = _new_skill_record(str(label).strip()[:100], key_points)
    return sid


def initialize_skill_registry(record=None):
    """Generate an atomic skill map once, then freeze it for the learning unit."""
    record = record or _record()
    if record.get("registry_locked") and record.get("skill_registry"):
        return record["skill_registry"]
    topic = learning_context.get("topic", "")
    goal = learning_context.get("goal", "")
    learner_request = " / ".join(pending_start_requests) if pending_start_requests else learning_context.get("goal", "")
    if not topic:
        return {}
    prompt = f"""Create a concise learning map for this topic.
Topic: {topic}
Goal: {goal}
Learner request: {learner_request}
Return JSON only: {{"skills":[{{"id":"short_snake_case_id","label":"Korean learner-facing label","key_points":["핵심 요소 1","핵심 요소 2"]}}]}}.
KEY POINT RULE: key_points must be concrete and self-explanatory when read alone (e.g. "전자영역수 4 → sp³ → 정사면체 배치"), never vague phrases. Every skill needs 2-3 key_points: the core elements a correct explanation must contain, as short Korean phrases. A simple concept needs only 2. GRANULARITY RULE: each skill must be a concept a learner can explain in a few sentences. Do not split one calculation into separate one-step skills (e.g. do not make 'unit conversion' and 'formula substitution' separate); use 3-5 skills.
SCOPE RULE: each label names ONE topic that a single question can check. Never join two different topics into one label with "와/과/및" (e.g. "세포의 기본 원리와 세포 유형" must be split or reduced to one topic); grouping closely related terms of the same topic is fine.
REQUEST RULE: the learner may have asked for an explanation, a memorization method or exam questions. Those are requests, NOT sub-concepts; never turn them into skills. Labels name a concept, never a quiz ("~문제") and never a study method.
CORE SIZE RULE: Create normally 3-5 sub-concepts (prefer 3 or 4). Never exceed 5. Use fewer when the topic is narrow; do not create extra items merely to separate every term, formula, property, or example.
GROUPING RULES:
- Group closely related basic terms that are normally learned together (for example, amplitude, wavelength, period, and frequency may be grouped as wave properties when the goal is an introductory overview).
- Do not make a separate sub-concept for every vocabulary word or formula.
- Keep only distinctions that require a meaningfully different understanding or learning activity.
- Avoid overlapping or duplicate skills.
- Include an application/relationship skill only when it is a central independent learning objective.
- Order from foundational understanding to application.
- Use stable short English snake_case IDs and concise Korean learner-facing labels.
- Do not omit an essential major idea merely to meet the preferred count; if the topic genuinely requires more, still cap at 5 and group related ideas."""
    response = client.responses.create(model=MODEL, instructions="Create a concise learning map with 3-5 meaningful sub-concepts, preferring 3-4. Group related vocabulary and formulas rather than making one item per term. Return valid JSON only.", input=prompt, text={"format":{"type":"json_object"}})
    data = json.loads(response.output_text)
    skills = data.get("skills", [])
    if not skills:
        raise ValueError("Could not create a non-empty skill registry")
    if len(skills) > 5:
        # Enforce the cap with a second semantic grouping pass instead of silently
        # dropping concepts from the model-generated map.
        compact_prompt = f"""The generated learning map exceeds the maximum size.
Topic: {topic}
Goal: {goal}
Current map: {json.dumps(skills, ensure_ascii=False)}
Reorganize it into 3-5 broader, non-overlapping learning sub-concepts (prefer 3-4).
Group related vocabulary, formulas, and closely connected ideas. Preserve all essential learning objectives.
Return JSON only: {{"skills":[{{"id":"short_snake_case_id","label":"Korean learner-facing label","key_points":["핵심 요소 1","핵심 요소 2"]}}]}}."""
        compact_response = client.responses.create(
            model=MODEL,
            instructions="Compress the learning map by grouping related concepts. Never return more than 5 skills. Return valid JSON only.",
            input=compact_prompt,
            text={"format": {"type": "json_object"}}
        )
        compact_skills = json.loads(compact_response.output_text).get("skills", [])
        if compact_skills:
            skills = compact_skills[:5]
    if len(skills) > 5:
        raise ValueError("The generated learning map still exceeds the 5-skill limit")
    return set_skill_registry(skills, record)


def _record():
    cid = learning_context.get("concept_id") or "general"
    learning_context["concept_id"] = cid
    return concept_records.setdefault(cid, _new_record())


def _state_num(state):
    return {"Unconfirmed": 0, "State1": 1, "State2": 2, "State3": 3}[state]


def _valid_status(x):
    return x if x in VALID_STATUS else "unknown"


def _valid_source(x):
    return x if x in VALID_SOURCES else "unknown"


def _dimension_entries(skill, dimension, source=None, independent_only=False):
    items = [e for e in skill.get("evidence", [])
             if e["dimension"] == dimension and e["status"] == "confirmed"]
    if source:
        items = [e for e in items if e["source"] == source]
    if independent_only:
        items = [e for e in items
                 if e["source"] in ("independent_explanation", "independent_transfer") and not e["hint_used"]]
    return items


def _skill_state(skill):
    """Evidence-derived eligibility; never trusts an LLM-provided State."""
    ev = list(skill.get("evidence", []))
    latest_gap = max([m.get("turn_id", 0) for m in skill.get("misconceptions", [])] or [0])
    if latest_gap:
        ev = [e for e in ev if e.get("turn_id", 0) >= latest_gap]
    independent = lambda e: (e.get("status") == "confirmed"
        and e.get("source") in ("independent_explanation", "independent_transfer")
        and not e.get("hint_used"))
    c = [e for e in ev if e.get("dimension") == "concept" and independent(e)]
    # A learner may demonstrate reasoning inside a novel application task.
    # The evaluator's dimension label (reasoning) plus independent source is decisive;
    # requiring the source string to be exactly independent_explanation was too strict.
    r = [e for e in ev if e.get("dimension") == "reasoning" and independent(e)]
    t = [e for e in ev if e.get("dimension") == "transfer" and independent(e)
         and e.get("source") == "independent_transfer"]
    # State3 needs independent C/R/T evidence, with evidence spanning at least
    # two distinct turns. C and R may naturally be demonstrated together in one
    # explanation; requiring three separate turns caused endless State2 loops.
    if c and r and t:
        # Search all eligible evidence combinations. This avoids a later repeated
        # dimension entry masking an earlier valid C/R/T combination.
        turn_sets = {
            frozenset((ce.get("turn_id"), re_.get("turn_id"), te.get("turn_id")))
            for ce in c for re_ in r for te in t
            if len({ce.get("turn_id"), re_.get("turn_id"), te.get("turn_id")}) >= 2
        }
        if turn_sets:
            return "State3"
    # Basic concept understanding is enough for State2; reasoning/transfer remain open.
    if c:
        return "State2"
    # State1 requires an actual demonstrated conceptual/reasoning gap, not absent evidence.
    if any(e.get("dimension") in ("concept", "reasoning") and e.get("status") == "missing"
           and e.get("source") not in ("ai_echo", "answer_only", "unknown")
           for e in ev):
        return "State1"
    return "Unconfirmed"


def _aggregate_state(record):
    """Return a descriptive topic-level summary; never use it for skill decisions."""
    states = [s.get("state", "Unconfirmed") for s in record.get("skill_records", {}).values()]
    if not states:
        return "Unconfirmed"
    rank = {"Unconfirmed": 0, "State1": 1, "State2": 2, "State3": 3}
    unique = set(states)
    if len(unique) == 1:
        return states[0]
    # Mixed states are deliberately not collapsed into a misleading single State.
    return "Mixed"


def _append_dimension_evidence(record, assessment, turn_id, hint_used=False):
    sid = _safe_id(assessment.get("skill_id") or "")
    registry = record.get("skill_registry", {})
    if not sid or sid not in registry:
        raise ValueError(f"Rejected evidence for unregistered skill_id: {sid!r}")
    label = registry[sid]
    skill = _ensure_skill_fields(record["skill_records"].setdefault(sid, _new_skill_record(label)))
    skill["label"] = label
    record["active_skill_id"] = sid
    for dim in ("concept", "reasoning", "transfer"):
        status = _valid_status(assessment.get(dim))
        source = _valid_source(assessment.get(dim + "_source"))
        skill["latest_dimensions"][dim] = status
        record["latest_dimensions"][dim] = status
        if status == "unknown":
            continue
        entry = {
            "turn_id": turn_id, "skill_id": sid, "skill_label": label,
            "dimension": dim, "status": status, "source": source,
            "hint_used": bool(hint_used or source in ("hint_assisted", "ai_echo", "answer_only")),
            "note": str(assessment.get("evidence_note", ""))[:500],
            "timestamp": datetime.now().isoformat(timespec="seconds")
        }
        # One record per skill/dimension/turn. A second evaluation cannot inflate evidence count.
        skill["evidence"] = [e for e in skill.get("evidence", [])
                              if not (e.get("turn_id") == turn_id and e.get("dimension") == dim)]
        skill["evidence"].append(entry)
        if status == "confirmed" and entry["source"] in ("independent_explanation", "independent_transfer") and not entry["hint_used"]:
            skill["dimensions"][dim] = "confirmed"
        elif status in ("partial", "missing") and skill["dimensions"].get(dim) != "confirmed":
            skill["dimensions"][dim] = status
    _refresh_skill_states(record)
    return sid, skill


def _refresh_skill_states(record):
    rank = {"Unconfirmed": 0, "State1": 1, "State2": 2, "State3": 3}
    independent = lambda e: (
        e.get("status") == "confirmed"
        and e.get("source") in ("independent_explanation", "independent_transfer")
        and not e.get("hint_used")
    )
    for skill in record.get("skill_records", {}).values():
        # State is refreshed by apply_state_controller, not by a free-running aggregate.
        # This function only refreshes descriptive dimension summaries.
        dims = skill.setdefault("dimensions", {})
        latest_gap = max([m.get("turn_id", 0) for m in skill.get("misconceptions", [])] or [0])
        for d in ("concept", "reasoning", "transfer"):
            vals = [e for e in skill.get("evidence", [])
                    if e.get("dimension") == d and e.get("turn_id", 0) >= latest_gap]
            if not vals:
                dims[d] = "unknown"
            elif any(independent(e) for e in vals):
                # ○ is kept until a real misconception appears; a later hint-assisted
                # or partial answer must not erase it.
                dims[d] = "confirmed"
            elif any(e.get("status") in ("confirmed", "partial") for e in vals):
                # confirmed-with-hint / echo / partial are all recorded as △.
                dims[d] = "partial"
            elif any(e.get("status") == "missing"
                     and e.get("source") not in ("ai_echo", "answer_only", "unknown") for e in vals):
                dims[d] = "missing"
            else:
                dims[d] = "unknown"
    states = [s.get("state", "Unconfirmed") for s in record.get("skill_records", {}).values()]
    if not states: record["state"] = "Unconfirmed"
    elif len(set(states)) == 1: record["state"] = states[0]
    else: record["state"] = "Mixed"
    dims = {d: [] for d in ("concept", "reasoning", "transfer")}
    for skill in record.get("skill_records", {}).values():
        for d in dims: dims[d].append(skill.get("dimensions", {}).get(d, "unknown"))
    record["dimensions"] = {d: ("confirmed" if vals and all(v == "confirmed" for v in vals)
        else "partial" if any(v in ("partial", "missing", "confirmed") for v in vals) else "unknown")
        for d, vals in dims.items()}
    record["confirmed_checks"] = [d for d,v in record["dimensions"].items() if v == "confirmed"]
    record["unconfirmed_checks"] = [d for d in ("concept", "reasoning", "transfer") if record["dimensions"].get(d) != "confirmed"]


def _has_state2_evidence(skill):
    return _skill_state(skill) in ("State2", "State3")


def _has_state3_evidence(skill):
    return _skill_state(skill) == "State3"


def _update_vulnerability(record):
    # Vulnerability is a per-skill signal; topic-level value is a compact summary.
    vals = []
    for skill in record.get("skill_records", {}).values():
        count = len(skill.get("misconceptions", []))
        # 오개념이 있었더라도 이후 안정적 이해(State3)에 도달하면 해소된 것으로 보고 낮음으로 되돌린다.
        if skill.get("state") == "State3":
            vals.append("low")
        elif (count >= 2 and skill.get("state") == "State2"
              and skill.get("dimensions", {}).get("concept") == "confirmed"):
            vals.append("moderate")     # 반복된 오개념이 있었지만 개념이 확인된 State2: 한 단계 낮춘다
        elif count == 0 and skill.get("state") in ("State1", "State2"):
            vals.append("low")          # 증거가 있고 오개념이 한 번도 없었으면 낮음 (평가되지 않음이 아니다)
        else:
            vals.append("high" if count >= 2 else "moderate" if count == 1 else "unknown")
    if "high" in vals:
        record["vulnerability"] = "high"
    elif "moderate" in vals:
        record["vulnerability"] = "moderate"
    elif vals and all(v == "low" for v in vals):
        record["vulnerability"] = "low"
    else:
        record["vulnerability"] = "unknown"


def apply_state_controller(record, assessment, turn_id, hint_used=False, skip_evidence=False):
    """Deterministic per-skill state transition with one-step promotion/demotion."""
    sid = _safe_id(assessment.get("skill_id") or "")
    if sid not in record.get("skill_registry", {}):
        raise ValueError(f"Assessment skill_id {sid!r} is not in the locked skill registry")
    skill = _ensure_skill_fields(record["skill_records"].setdefault(sid, _new_skill_record(record["skill_registry"][sid])))
    old = skill.get("state", "Unconfirmed")
    if skip_evidence or not assessment.get("has_content_attempt", False):
        return old, old, "내용 증거가 없는 입력이므로 해당 하위 개념의 State 유지"
    a = dict(assessment)
    _, skill = _append_dimension_evidence(record, a, turn_id, hint_used)
    core_source = _valid_source(a.get("concept_source", "unknown"))
    core_error = bool(a.get("core_misconception", False)) and core_source not in ("ai_echo", "answer_only", "unknown")
    explicit_gap = None
    for dim in ("concept", "reasoning", "transfer"):
        dim_source = _valid_source(a.get(dim + "_source", "unknown"))
        if a.get(dim) == "missing" and dim_source in ("independent_explanation", "independent_transfer") and not hint_used:
            explicit_gap = dim
            break
    calc_only = bool(a.get("calculation_or_notation_error_only", False))
    if (core_error or explicit_gap) and not calc_only:
        note = str(a.get("misconception_note") or a.get("evidence_note", ""))[:500]
        skill.setdefault("misconceptions", []).append({"turn_id": turn_id, "note": note})
        gap_dim = explicit_gap or ("concept" if a.get("concept") == "missing" else "reasoning")
        skill["evidence"] = [e for e in skill["evidence"] if not (e.get("turn_id") == turn_id and e.get("dimension") == gap_dim)]
        skill["evidence"].append({"turn_id": turn_id, "skill_id": sid, "skill_label": skill["label"],
            "dimension": gap_dim, "status": "missing", "source": core_source,
            "hint_used": bool(hint_used), "note": note, "timestamp": datetime.now().isoformat(timespec="seconds")})
        target = "State1" if old in ("Unconfirmed", "State1") else ("State2" if old == "State3" else "State1")
        skill["state"] = target
        reason = f"실제 핵심 오개념 확인: {old}에서 최대 한 단계 하향하여 {target}"
    else:
        eligible = _skill_state(skill)
        rank = {"Unconfirmed": 0, "State1": 1, "State2": 2, "State3": 3}
        if old == "Unconfirmed":
            # Evidence-based initialization; State3 still requires 3 distinct evidence turns.
            skill["state"] = eligible
            reason = f"초기 증거 판정: {eligible} (해당 하위 개념의 증거만 사용)"
        elif rank[eligible] > rank[old]:
            next_state = {"State1": "State2", "State2": "State3"}.get(old, old)
            if rank[eligible] >= rank[next_state]:
                skill["state"] = next_state
                reason = f"독립 증거 충족: {old}에서 한 단계만 승급하여 {next_state}"
            else:
                skill["state"] = old
                reason = "다음 단계의 증거 기준 미충족: 현재 State 유지"
        else:
            skill["state"] = old
            reason = f"증거 기준 미충족: {old} 유지"
    _refresh_skill_states(record)
    _update_vulnerability(record)
    return old, skill["state"], reason


# ---------------------------
# Explicit intent and action control (v3.5)
# ---------------------------
def _is_explicit_topic_switch_request(text):
    """Detect explicit course/topic changes, including course+topic in one message.

    This runs before evidence evaluation. It should recognize both a broad
    switch request (which may need a topic clarification) and a fully specified
    new course/topic request (which can go directly to the start router).
    """
    t = re.sub(r"\s+", " ", str(text or "").strip().lower())
    if not t:
        return False

    course = r"(?:일반\s*물리학|물리학|일반\s*생물학|일반\s*생물|생물학|일반\s*화학|화학|수학|미적분|통계학|경제학|생물|물리)"
    explicit_switch_patterns = [
        r"(?:다른|새로운)\s*(?:과목|주제|단원|개념)(?:으로|로|을|를|도)?",
        r"다음\s*(?:과목|주제|단원)(?:으로|로|을|를|도)?",   # "다음 개념으로 넘어가자"는 하위 개념 이동이지 주제 전환이 아니다
        r"(?:과목|주제|단원)(?:를|을)?\s*(?:바꾸|변경|전환|옮기)",
        r"(?:공부|학습)\s*(?:주제|과목)(?:를|을)?\s*(?:바꾸|변경|전환)",
        r"(?:과목|주제|단원|질문)으로\s*넘어가(?:도\s*될까|고\s*싶|자|고)?",
        r"(?:공부|학습)할\s*(?:과목|주제|내용)을?\s*(?:바꾸|전환)",
        r"(?:이전|방금|앞의)\s*(?:과목|주제|학습)은?.{0,30}(?:해결|끝|마쳤).{0,45}(?:다른|새로운|다음|에서도)",
    ]
    # Course named as the destination, with an explicit transition/request.
    course_destination_patterns = [
        course + r"(?:\s*(?:과목|수업))?\s*(?:질문|공부|학습)?\s*(?:으로|로)\s*넘어가",
        r"(?:넘어가|전환|바꾸).{0,30}" + course,
    ]
    # A course plus a concrete topic/request in the same message is also a
    # topic-switch signal. The start router decides whether the topic is specific.
    course_topic_patterns = [
        course + r"\s*에서\s*.{1,100}(?:공부하고\s*싶|질문하고\s*싶|물어보고\s*싶|배우고\s*싶|알아보고\s*싶|관련\s*(?:내용|개념))",
        course + r"\s*(?:의|관련)\s*.{1,80}(?:공부하고\s*싶|질문하고\s*싶|물어보고\s*싶|배우고\s*싶|알아보고\s*싶)",
        course + r"(?:에서도|쪽에서도).{0,60}(?:궁금|공부|질문|배우|알고\s*싶)",
    ]
    if any(re.search(p, t) for p in explicit_switch_patterns):
        return True
    if any(re.search(p, t) for p in course_destination_patterns):
        return True
    return any(re.search(p, t) for p in course_topic_patterns)


def _detect_explicit_intent(text, model_intent):
    """Prefer contextual LLM intent; retain narrow deterministic fallbacks for menu choices."""
    t = str(text or "").lower().strip()
    # The evaluator reads the full dialogue and is the primary intent interpreter.
    # Deterministic rules below are only fallbacks when it returns the default.
    if model_intent in VALID_INTENTS and model_intent != "continue":
        return model_intent

    if any(x in t for x in ["그냥 설명", "바로 설명", "정답 알려", "그냥 알려", "전체적으로 설명", "자세히 설명해줘", "설명해줘", "설명해 줘"]):
        return "explain"
    if any(x in t for x in ["더 어려운 적용", "어려운 적용 문제", "적용 문제", "연습문제", "연습 문제", "문제로 확인", "문제 풀", "퀴즈"]):
        return "practice"
    if any(x in t for x in ["넘어가자", "건너뛰", "이건 아니까", "확인하지 않아도"]):
        return "skip_check"
    if any(x in t for x in ["마무리", "오늘은 여기까지", "학습 끝", "끝내자"]):
        return "finish_unit"
    if any(x in t for x in ["복습", "다시 보자", "다시 확인"]):
        return "review"

    last_assistant = next((m.get("content", "") for m in reversed(messages) if m.get("role") == "assistant"), "")
    has_menu = any(k in last_assistant for k in ["더 어려운 적용", "복습", "다음 개념"])
    if has_menu and any(x in t for x in ["마스터", "더 탄탄", "더 공부", "더 해볼", "더 해보", "더 하고", "복습할", "복습 할"]):
        return "review"
    if has_menu and re.fullmatch(r"\\s*1[.)]?\\s*", t): return "practice"
    if has_menu and re.fullmatch(r"\\s*2[.)]?\\s*", t): return "review"
    if has_menu and re.fullmatch(r"\\s*3[.)]?\\s*", t): return "next_unit"
    return "continue"


def _target_skill(record, assessment=None):
    assessment = assessment or {}
    sid = assessment.get("skill_id") or (record.get("active_task") or {}).get("skill_id") or record.get("active_skill_id")
    if sid and sid in record.get("skill_records", {}):
        return record["skill_records"][sid]
    return None


def _target_sid(record, assessment=None):
    assessment = assessment or {}
    for sid in (assessment.get("skill_id"), (record.get("active_task") or {}).get("skill_id"),
                record.get("active_skill_id")):
        if sid and sid in record.get("skill_records", {}):
            return sid
    return None


# ---------------------------
# v3.13 progression engine (수정 규칙 1·2·3·6·7·9·10)
# ---------------------------
def _next_open_skill_id(record, current_sid=None):
    """목록 순서대로 다음 열린 하위 개념. 현재 개념 뒤를 먼저 보고, 없으면 앞쪽의 열린 개념."""
    order = list(record.get("skill_registry", {}))
    recs = record.get("skill_records", {})
    start = order.index(current_sid) + 1 if current_sid in order else 0
    for sid in order[start:] + order[:start]:
        if sid != current_sid and not recs.get(sid, {}).get("closed"):
            return sid
    return None


def _is_untouched(sk):
    """질문도 턴도 증거도 없는, 아직 시작하지 않은 하위 개념."""
    return (not sk.get("ask_count") and not sk.get("turns_spent") and not sk.get("evidence")
            and not sk.get("revealed") and not sk.get("misconceptions"))


def _close_skill(record, sid, how):
    sk = _ensure_skill_fields(record["skill_records"][sid])
    sk["closed"] = "confirmed" if how == "confirmed_with_help" else how
    if how == "revealed":
        sk["revealed"] = True
    if how == "confirmed_with_help":
        sk["needs_recheck"] = True


def _pick_strategy(skill):
    """규칙 7: 같은 설명 방식은 최대 2회, 연속 반복 금지. 가장 덜 쓴 전략을 고른다."""
    used = skill.setdefault("strategies_used", [])
    last = used[-1] if used else None
    order = sorted(STRATEGIES, key=lambda s: (used.count(s), STRATEGIES.index(s)))
    choice = next((s for s in order if s != last), order[0])
    used.append(choice)
    return choice


def _build_wrap_up_queue(record):
    """규칙 10: 미확인 C/R/T만 우선 확인. 답을 알려준 개념 > 건너뛴 개념 > 도움받아 확인된 개념 > 취약 개념 > 나머지.
    개념당 1문제. State3인 개념은 생략."""
    items = []
    for idx, (sid, label) in enumerate(record.get("skill_registry", {}).items()):
        sk = _ensure_skill_fields(record["skill_records"].get(sid) or _new_skill_record(label))
        dims = sk.get("dimensions", {})
        state = sk.get("state", "Unconfirmed")
        vulnerable = bool(sk.get("misconceptions"))
        if state == "State3" or sk.get("unvisited"):
            continue
        if sk.get("revealed"):
            pri, dim, why = 0, "concept", "revealed"
        elif sk.get("closed") == "skipped" and dims.get("concept") != "confirmed":
            pri, dim, why = 1, "concept", "skipped"
        elif sk.get("needs_recheck"):
            pri, dim, why = 2, "concept", "hint_assisted"
        elif dims.get("concept") != "confirmed":
            pri, dim, why = 3, "concept", "unconfirmed"
        elif vulnerable:
            pri, dim, why = 4, "reasoning_transfer", "vulnerable"
        else:
            pri, dim, why = 5, "reasoning_transfer", "unconfirmed"
        items.append((pri, idx, {"skill_id": sid, "label": sk.get("label", label),
                                 "dimension": dim, "reason": why}))
    items.sort(key=lambda x: (x[0], x[1]))
    return [x[2] for x in items]


def _start_wrap_up(record):
    record["wrap_up_active"] = True
    record["wrap_up_questions_asked"] = 0
    queue = _build_wrap_up_queue(record)
    tr = record.get("transition") or {}
    just = tr.get("closed_sid") if tr.get("how") == "revealed" else None
    if just:
        # 방금 답을 알려 준 개념은 곧바로 되묻지 않는다(따라 말하기 방지): 맨 뒤로 보내고, 혼자뿐이면 새 상황 적용으로 묻는다.
        others = [x for x in queue if x["skill_id"] != just]
        mine = [x for x in queue if x["skill_id"] == just]
        for x in mine:
            if not others:
                x["dimension"], x["reason"] = "reasoning_transfer", "revealed_recent"
        queue = others + mine
    record["wrap_up_queue"] = queue
    record["active_task"] = None


def _wrap_up_next_action(record):
    queue = record.get("wrap_up_queue") or []
    if queue and record.get("wrap_up_questions_asked", 0) < MAX_WRAPUP_QUESTIONS:
        target = queue.pop(0)
        record["wrap_target"] = target
        record["active_skill_id"] = target["skill_id"]
        return "wrap_up_check"
    record["wrap_target"] = None
    return "wrap_up_summary"


def _after_skill_closed(record, closed_sid, how, kind):
    """한 하위 개념이 닫힌 뒤: 다음 개념 질문 또는 (모두 닫혔으면) 마무리 확인으로."""
    _close_skill(record, closed_sid, how)
    nxt = _next_open_skill_id(record, closed_sid)
    label = record["skill_records"][closed_sid].get("label", closed_sid)
    record["active_task"] = None
    record["transition"] = {"closed_sid": closed_sid, "closed_label": label,
                            "how": "confirmed" if how == "confirmed_with_help" else how,
                            "next_sid": nxt}
    if nxt:
        record["active_skill_id"] = nxt
        return kind
    _start_wrap_up(record)
    record["transition"]["to_wrap_up"] = True
    return _wrap_up_next_action(record)


def _weakest_skill_id(record):
    rank = {"Unconfirmed": 0, "State1": 1, "State2": 2, "State3": 3}
    cands = []
    for idx, (sid, sk) in enumerate(record.get("skill_records", {}).items()):
        if sid in record.get("skill_registry", {}):
            cands.append((1 if sk.get("unvisited") else 0, 0 if sk.get("revealed") else 1,
                          rank.get(sk.get("state", "Unconfirmed"), 0), idx, sid))
    return sorted(cands)[0][4] if cands else None


def choose_action(record, intent, assessment):
    """Choose the NEXT dialogue action. 상태 전환 로그와 독립적으로 다음 행동만 결정한다."""
    record["transition"] = None
    sid = _target_sid(record, assessment)

    # --- 규칙 1: 사용자가 정한 진행 방식은 그대로 따른다 ---
    if intent in ("explain", "practice", "skip_check", "pause_session", "finish_unit", "next_unit", "change_goal"):
        record["review_session"] = None
    if intent == "explain":
        record["active_task"] = None
        return "full_explanation"
    if intent == "practice":
        target = record.get("active_skill_id") or assessment.get("skill_id")
        if target in record.get("skill_registry", {}):
            record["practice_session"] = {
                "target_skill_id": target,
                "target_label": record["skill_registry"][target],
                "active": True,
                "step": 1
            }
        record["active_task"] = None
        return "practice"
    if intent == "skip_check":
        record["active_task"] = None
        if record.get("wrap_up_active"):
            return _wrap_up_next_action(record)      # 마무리 확인 하나를 건너뜀 (미확인으로 남음)
        sid = sid or next(iter(record.get("skill_registry", {})), None)
        if sid:
            return _after_skill_closed(record, sid, "skipped", "advance_next")
        return "goal_clarification"
    if intent == "pause_session":
        record["active_task"] = None
        return "pause_ack"
    if intent == "progress_query":
        record["active_task"] = None
        return "progress_report"
    if intent == "finish_unit":
        if record.get("wrap_up_active"):
            return _wrap_up_next_action(record)   # 이미 마무리 중이면 다시 시작하지 않는다
        for s in record.get("skill_registry", {}):
            if not record["skill_records"].get(s, {}).get("closed"):
                _sk = record["skill_records"].get(s) or {}
                if _is_untouched(_sk):
                    _sk["unvisited"] = True      # 한 번도 다루지 않은 개념: 약한 개념이 아니라 '시작 전'으로 둔다
                _close_skill(record, s, "skipped")
        _start_wrap_up(record)
        return _wrap_up_next_action(record)
    if intent == "review":
        record["active_task"] = None
        weakest = _weakest_skill_id(record)
        if weakest:
            record["active_skill_id"] = weakest
            record["review_session"] = {"sid": weakest, "rounds": 0}
        return "review"
    if intent == "next_unit":
        record["active_task"] = None
        return "next_unit_choice"
    if intent == "process_complaint":
        record["active_task"] = None
        record["_has_next_open"] = bool(_next_open_skill_id(record, record.get("active_skill_id")))
        return "offer_direction_choice"
    if intent == "change_goal":
        record["active_task"] = None
        return "diagnostic_question" if assessment.get("topic_detected") else "goal_clarification"

    if (not learning_context.get("topic") or not learning_context.get("goal")):
        return "goal_clarification"

    # --- 학습 단위가 끝난 뒤: 복습 권유는 한 번만. 거절하면 다시 묻지 않는다 (규칙 10) ---
    if record.get("unit_status") == "completed":
        rs = record.get("review_session")
        if rs and intent == "continue":
            # 복습 중: 답을 평가하고, 맞으면 마무리, 두 번 부족하면 답을 알려 주고 끝낸다.
            rs["rounds"] = rs.get("rounds", 0) + 1
            miscon = bool(assessment.get("core_misconception")) and not assessment.get("calculation_or_notation_error_only")
            ok = ((assessment.get("concept") == "confirmed" or assessment.get("answered_asked_question_correctly") is True)
                  and not miscon and assessment.get("concept_source") not in ("ai_echo", "answer_only"))
            if ok:
                _rsk = record.get("skill_records", {}).get(rs.get("sid"), {})
                if _rsk.get("state") in ("State1", "State2") and not rs.get("extra"):
                    # 한 번 더 새 상황에서 확인되면 안정적 이해(State3)로 올라간다: 같은 복습에서 한 문제만 더 묻는다.
                    rs["extra"] = True
                    rs["rounds"] = 0
                    return "review"
                record["review_session"] = None
                return "review_done"
            if rs["rounds"] >= 2:
                record["review_session"] = None
                return "review_reveal"
            if miscon:
                return "diagnose_misconception"
            if not assessment.get("has_content_attempt") or assessment.get("learner_stuck"):
                return "hint"
            return "guided_question"
        return "closing_ack"

    # --- 규칙 10: 마무리 확인 단계 ---
    if record.get("wrap_up_active"):
        _wt = record.get("wrap_target") or {}
        if _wt.get("skill_id") in record.get("skill_records", {}) and intent in ("continue", "skip_check"):
            record["skill_records"][_wt["skill_id"]]["rechecked"] = True
        return _wrap_up_next_action(record)

    # --- 일반 학습 흐름: 목록 순서대로, 개념(C)이 확인되면 다음 개념으로 ---
    if sid is None:
        sid = next((s for s in record.get("skill_registry", {})
                    if not record["skill_records"].get(s, {}).get("closed")), None)
        if sid is None:
            _start_wrap_up(record)
            return _wrap_up_next_action(record)
        record["active_skill_id"] = sid
    skill = _ensure_skill_fields(record["skill_records"][sid])
    skill["turns_spent"] += 1
    misconception = bool(assessment.get("core_misconception")) and not assessment.get("calculation_or_notation_error_only")
    concept_ok = (skill.get("state") in ("State2", "State3")
                  and skill.get("dimensions", {}).get("concept") == "confirmed")
    if concept_ok and not misconception:
        return _after_skill_closed(record, sid, "confirmed", "advance_next")
    if (assessment.get("concept") == "confirmed" and not misconception
            and assessment.get("concept_source") == "hint_assisted"):
        # 힌트를 받고 맞힌 답은 바로 인정하고 넘어가되, 마무리 확인에서 다시 본다.
        return _after_skill_closed(record, sid, "confirmed_with_help", "advance_next")
    if skill["ask_count"] >= MAX_ASKS_PER_SKILL + 1 or skill["turns_spent"] >= MAX_TURNS_PER_SKILL:   # +1: 진단 질문은 세지 않는다
        if (assessment.get("concept") == "confirmed" and not misconception
                and assessment.get("concept_source") != "answer_only"):
            # 힌트를 받고 맞힌 경우(설명을 따라 말한 경우 포함): 답을 또 알려 주지 않고 넘어가되 마무리 확인에서 다시 본다.
            return _after_skill_closed(record, sid, "confirmed_with_help", "advance_next")
        return _after_skill_closed(record, sid, "revealed", "reveal_and_next")
    if misconception and record.get("last_action") != "diagnose_misconception":
        return "diagnose_misconception"          # 규칙 4: 정답을 바로 말하지 않고 질문 1개 (연속 두 번은 하지 않는다)
    if misconception:
        skill["help_level"] = 1
        return "hint"
    if skill["ask_count"] == 0:
        return "diagnostic_question"             # 규칙 7: Unconfirmed → 짧은 진단 질문
    if not assessment.get("has_content_attempt") or assessment.get("learner_stuck"):
        skill["help_level"] = 2 if record.get("last_action") == "hint" else 1
        return "hint"                            # 규칙 6: 질문 → 힌트 (한 턴에 한 단계만)
    return "guided_question"                     # 규칙 5: 빠진 핵심 요소 하나만 질문


def _format_state(state):
    labels = {"Unconfirmed": "이해도 확인 중", "State1": "기초 이해 보완 필요",
              "State2": "부분적 이해", "State3": "안정적 이해", "Mixed": "하위 개념별 상태 상이"}
    return labels.get(state, "이해도 확인 중")


def progress_summary(record):
    """Return per-skill progress only; intentionally no topic-level State."""
    labels = {"concept": "개념", "reasoning": "이유 설명", "transfer": "새 상황 적용"}
    skills = []
    for sid, skill in record.get("skill_records", {}).items():
        dims = skill.get("dimensions", {})
        state = skill.get("state", "Unconfirmed")
        skills.append({
            "skill_id": sid,
            "label": skill.get("label", sid),
            "state": state,
            "state_label": _format_state(state),
            "closed": skill.get("closed"),
            "revealed": bool(skill.get("revealed")),
            "unvisited": bool(skill.get("unvisited")),
            # Mutually exclusive current status per dimension.
            "confirmed": [labels[d] for d in labels if dims.get(d) == "confirmed"],
            "partial": [labels[d] for d in labels if dims.get(d) in ("partial", "missing")],
            "unconfirmed": [labels[d] for d in labels if dims.get(d, "unknown") == "unknown"]
        })
    return {"skills": skills, "active_task": record.get("active_task"),
            "vulnerability": record.get("vulnerability", "unknown")}



# ---------------------------
# LLM calls and user-facing dialogue
# ---------------------------
def _call_evaluator(user_text, record, turn_id):
    recs = record.get("skill_records", {})
    active_sid = record.get("active_skill_id") or ""
    active_sk = recs.get(active_sid, {})
    context = {
        "topic": learning_context.get("topic", ""),
        "goal": learning_context.get("goal", ""),
        "active_skill_state": active_sk.get("state", "Unconfirmed"),
        "active_skill_dimensions": active_sk.get("dimensions", {"concept":"unknown", "reasoning":"unknown", "transfer":"unknown"}),
        "active_skill_key_points": active_sk.get("key_points", []),
        "ask_count_for_active_skill": active_sk.get("ask_count", 0),
        "recent_misconceptions": record["misconceptions"][-3:],
        "recent_evidence_by_skill": {sid: sk.get("evidence", [])[-6:] for sid, sk in recs.items()},
        "recent_dialogue": messages[-8:],
        "last_tutor_action": record.get("last_action"),
        "turn_id": turn_id,
        "help_level": active_sk.get("help_level", record["help_level"]),
        "active_task": record.get("active_task"),
        "practice_session": record.get("practice_session"),
        "practice_session_rule": "If active, preserve target_skill_id as the learner's chosen practice goal. Prerequisite checks are substeps inside that practice session; after confirming one prerequisite, return to the next step of the original practice goal.",
        "active_task_routing_rule": "For ordinary diagnosis, route by the concept tested. During an active practice_session, preserve its target goal and treat prerequisite checks as internal practice steps, not a change of learning target.",
        "wrap_up_target": record.get("wrap_target") if record.get("wrap_up_active") else None,
        "known_skill_ids": list(record.get("skill_registry", {}).keys()),
        "skill_registry_locked": record.get("registry_locked", False),
        "skill_registry": record.get("skill_registry", {}),
        "known_skills": {sid: {"label": recs.get(sid, {}).get("label", label),
            "state": recs.get(sid, {}).get("state", "Unconfirmed"),
            "dimensions": recs.get(sid, {}).get("dimensions", {}),
            "key_points": recs.get(sid, {}).get("key_points", [])}
            for sid, label in record.get("skill_registry", {}).items()},
        "active_skill_id": record.get("active_skill_id"),
        "awaiting_learner_choice": record.get("awaiting_learner_choice", False)
    }
    prompt = (
        "CONTEXT:\n" + json.dumps(context, ensure_ascii=False)
        + "\n\nLATEST LEARNER MESSAGE:\n" + user_text
        + "\n\nOutput requirement: Return the assessment as a valid JSON object."
    )
    response = client.responses.create(
        model=MODEL,
        instructions=EVALUATOR_PROMPT,
        input=prompt,
        text={"format": {"type": "json_object"}}
    )
    return json.loads(response.output_text)


def _build_action_instruction(action, record, intent, assessment):
    recs = record.get("skill_records", {})
    cur = recs.get(record.get("active_skill_id") or "", {})
    label = cur.get("label", "현재 개념")
    missing = str(assessment.get("missing_key_point") or "").strip()
    tr = record.get("transition") or {}
    wt = record.get("wrap_target") or {}
    strategy = record.get("current_strategy") or "definition"

    QRULE = (" 질문 규칙: 한 문장에 한 가지만 묻고, 범위가 넓은 개념이면 '각각/모두'를 묻지 말고 '아는 것 두세 개를 골라 설명'하게 하세요. "
             "개념 이름은 써도 되지만, 답에 해당하는 구체적 용어나 값(예: 구조 이름, 수치)은 질문에 넣지 마세요. 개념 이름을 '원자 하나의 상태' 같은 돌려 말하기로 바꾸지 마세요.")
    reveal_first = ""
    if tr.get("how") == "revealed" and action in ("wrap_up_check", "wrap_up_summary"):
        reveal_first = (f"먼저 '{tr.get('closed_label')}'의 핵심 답을 reveal_key_points를 바탕으로 1~2문장으로 알려 주고, "
                        "마무리 확인에서 다시 확인하겠다고 자연스럽게 알려 주세요. 그다음 아래 지시를 수행하세요. ")
    to_wrap = ""
    if tr.get("to_wrap_up") and tr.get("how") != "revealed" and action in ("wrap_up_check", "wrap_up_summary"):
        to_wrap = (f"먼저 방금 학습자의 답('{tr.get('closed_label', '')}')에서 맞은 부분을 한 문장으로 인정하세요(새 설명은 덧붙이지 마세요). "
                   "그다음 정해진 하위 개념을 모두 다뤘다고 짧게 알리고, 이어서 아래 지시를 수행하세요. ")
        if tr.get("how") == "skipped":
            to_wrap = ("건너뛰자는 요청을 받아들였다고 먼저 짧게 알리고(확인하지 않은 부분은 마무리에서 다시 본다고), "
                       "정해진 하위 개념을 모두 다뤘다고 한 문장으로 알린 뒤 아래 지시를 수행하세요. ")

    if action == "wrap_up_check":
        _has_prior = bool(recs.get(wt.get("skill_id"), {}).get("evidence"))
        if wt.get("dimension") == "concept" and (wt.get("reason") == "revealed" or (wt.get("reason") in ("hint_assisted", "unconfirmed") and _has_prior)):
            wrap_q = (f"'{wt.get('label')}'은 이미 대화에서 다룬 개념입니다. 같은 질문을 되풀이하거나 설명을 다시 시키지 말고, recent_dialogue에 이미 나온 사례와 겹치지 않는 구체적인 새 사례 하나에 이 개념을 적용해 보게 하는 질문 하나만 하세요. "
                      "대화에서 비유나 예시로 쓴 물질·소재(예: 소금물, 설탕물)는 다시 쓰지 말고 다른 물질이나 수치를 쓰세요. 단위 변환·절차를 확인하는 질문이라면 변환 결과의 단위나 방법(예: 'L로', '몰질량으로 나눠')을 질문에 적지 말고 '이 값을 계산에 쓰려면 어떻게 다루나요?'처럼 물으세요. 용질·용매처럼 정답에 해당하는 말은 질문에 넣지 마세요. 정답이나 핵심어를 제시하지 마세요.")
        elif wt.get("dimension") == "concept":
            wrap_q = (f"'{wt.get('label')}'의 핵심을 학습자가 자기 말로 설명하게 하는 열린 질문 하나만 하세요. "
                      "정답, 핵심어, 선택지, 빈칸을 제시하지 마세요. 범위가 넓으면 아는 것 두세 개를 골라 설명하게 하세요. 최근 대화에서 이미 한 질문과 같은 내용이 되지 않도록 이 개념만의 초점을 물으세요.")
        else:
            extra = " 이전에 흔들렸던 개념이므로 앞서 쓴 예와 다른 상황을 쓰세요." if wt.get("reason") == "vulnerable" else ""
            if wt.get("reason") == "revealed_recent":
                extra = " 방금 알려 준 내용을 되풀이하게 하지 말고, 앞서 쓰지 않은 새 상황에 적용하게 하세요."
            wrap_q = (f"'{wt.get('label')}'을(를) 힌트 없이 새로운 상황에 적용하고, 그렇게 되는 이유를 자기 말로 한 문장 덧붙이게 하는 질문 하나만 하세요."
                      " 풀이 단서나 정답을 주지 마세요." + extra)
        prev = ""
        if record.get("wrap_up_questions_asked", 0) > 0 and not to_wrap and not reveal_first:
            prev = ("먼저 직전 답에 한 문장으로 반응하세요: 맞은 부분은 구체적으로 인정하고, 빠진 부분이 있으면 정답을 말하지 말고 '마지막 정리에서 다시 짚을게요'라고만 하세요. "
                    "'모르겠다'는 답이면 '괜찮아요'로 짧게 받으세요. ")
        wrap_instruction = prev + "마무리 확인 단계입니다. 이미 확인된 내용은 다시 묻지 말고, " + wrap_q + QRULE
    else:
        wrap_instruction = ""

    instructions = {
        "diagnostic_question": f"현재 개념 '{label}'의 이해를 확인하는 열린 질문 하나만 하세요. 개념 이름은 그대로 써도 되고, 쉬운 말로 직접 물으세요(예: '~에 대해 아는 대로 설명해 볼래요?'). 선택지, 빈칸, 문장 시작 힌트, 답을 말해 주는 질문, 돌려 말하는 비유나 수수께끼는 금지입니다. 설명을 먼저 길게 하지 마세요." + QRULE,
        "advance_next": ("직전 개념 '" + str(tr.get("closed_label", "")) + "'에 대한 학습자의 답을 한 문장으로 인정하세요(새로운 설명을 덧붙이지 마세요)."
                         + (" 학습자가 넘어가자고 했으므로 확인하지 않은 부분은 마무리에서 다시 확인한다고 짧게 알리세요." if tr.get("how") == "skipped" else "")
                         + f" 그다음 새 개념 '{label}'에 대한 열린 진단 질문 하나만 하세요. 쉬운 말로 직접 물으세요(예: '~에 대해 아는 대로 설명해 볼래요?'). 선택지, 빈칸, 핵심어를 쓰지 마세요." + QRULE),
        "reveal_and_next": (f"학습자가 같은 개념에서 두 번 답하지 못했습니다. '{tr.get('closed_label', '')}'의 핵심 답을 reveal_key_points를 바탕으로 1~3문장으로 알려 주고, "
                            f"이 개념은 마무리 확인에서 다시 확인한다고 알리세요. 그다음 새 개념 '{label}'에 대한 열린 진단 질문 하나만 하세요. 쉬운 말로 직접 물으세요(예: '~에 대해 아는 대로 설명해 볼래요?'). 알려 준 개념은 다시 묻지 마세요. 설명은 알려 주는 개념의 범위 안에서만 하고 다음 개념의 내용은 미리 말하지 마세요. 설명 방식은 {strategy}." + QRULE),
        "hint": ("학습자가 막혔습니다. 정답이나 설명을 주지 말고 '단서 하나'만 주세요. 규칙: (1) 전체 2문장 이내, 150자 이내. "
                 "(2) 직전 질문을 이어서, target_key_point로 가는 쉬운 단서가 되게 하세요. target_key_point의 내용을 직접 말하면 안 됩니다. "
                 "(3) 개념·용어는 한 가지만 언급하고, 여러 대상의 기능을 나열하지 마세요. "
                 "(4) 직전 질문보다 한 단계 작고 쉬운 질문 하나로 끝내세요. 직전 질문과 무관한 주제로 바꾸지 마세요. "
                 "(5) '모르겠다'는 말에 '좋아요'라고 반응하지 말고 '괜찮아요' 정도로 짧게 받으세요. "
                 "(6) 직전 질문을 반복하거나 말만 바꿔 다시 묻지 마세요. (8) '~해 보세요' 같은 지시문을 따로 붙이지 말고, 단서가 담긴 질문 하나로만 쓰세요. 단위는 mol/L, g/mol, mL, L처럼 정확히 쓰세요."
                 + (" (7) 이미 힌트를 한 번 줬으므로 이번에는 직전 힌트보다 딱 한 단계만 더 구체적인 단서를 주되, 정답이나 핵심 요소를 직접 말하지는 마세요." if cur.get("help_level") == 2 else "")),
        "guided_question": (f"학습자가 이미 맞힌 부분(앞선 대화에서 이미 말한 내용 포함)은 한 문장으로 인정하고 같은 것을 다시 묻지 마세요. 질문 문장에는 빠진 요소의 내용이나 그 핵심어를 넣지 말고, 그 요소가 속한 영역만 가리키는 열린 질문을 하세요(예: '그 값은 어떻게 정해지나요?'). 인정은 이렇게 하세요(방금 AI가 한 설명을 따라 말한 경우에는 '경로는 설명한 그대로예요'처럼 범위를 한정해 짧게만 받으세요). 빠진 핵심 요소 하나만"
                            + (f"('{missing}')" if missing else "") + " 스스로 말하게 하는 질문 하나만 하세요. 그 요소의 답을 직접 알려 주거나 빈칸 형태로 만들지 마세요. 이전 질문을 반복하지 마세요. 설명을 덧붙이지 말고 150자 이내로 쓰세요." + QRULE),
        "diagnose_misconception": "오개념이 드러난 지점을 '이 부분을 한 번 더 살펴볼게요' 정도로 짧게 짚되, 무엇이 어떻게 틀렸는지(예: 서로 바뀌었다)나 정답은 말하지 말고, 'A가 아니라 B' 같은 대비 표현도 쓰지 말고(정답을 알려 주는 셈이 됩니다), 그 지점을 스스로 드러내게 하는 질문(또는 더 쉬운 선행 개념 질문) 하나만 하세요." + QRULE,
        "full_explanation": (f"사용자의 명시적 요청이므로 {strategy} 방식으로 explain_key_points를 바탕으로 설명하세요(600자 이내). "
                             "설명 끝에 핵심을 확인하는 짧은 적용 질문 하나를 붙이세요('이해했어요?' 같은 질문은 금지). 설명으로 건너뛴 부분은 확인된 것으로 취급하지 않습니다."),
        "partial_explanation": f"필요한 부분만 {strategy} 방식으로 부분 설명하고, 학습자가 나머지를 이어가도록 질문 하나만 하세요.",
        "prerequisite_explanation": f"부족한 선수 개념을 {strategy} 방식으로 아주 짧게 설명하고 확인 질문 하나만 하세요.",
        "practice": f"학습자가 연습을 원합니다. practice_session의 target_label('{label}')을 목표로 고정하고, 새로운 상황의 문제를 내세요. 문제는 등록된 하위 개념 범위 안에서만 내고, 그 범위를 벗어난 개념(예: 다른 단원의 계산)은 쓰지 마세요. 학습자가 문제 개수를 말했다면(최대 5개) 그 개수만큼 번호를 붙여 한 번에 내고, 말하지 않았다면 한 문제만 내세요. "
                     "recent_dialogue에서 이미 나온 사례·질문과 겹치지 않는 서로 다른 사례로 만들고, 정답이나 풀이 단서는 주지 마세요. 마지막에 번호와 함께 답해 달라고 한 문장으로 안내하세요.",
        "review": ((f"먼저 학습자의 직전 복습 답에서 맞은 부분을 한 문장으로 인정하고, 지금은 '부분적 이해(State 2)'라서 새로운 상황에서 한 번 더 확인되면 안정적 이해로 올라간다고 짧게 알리세요. "
                    f"그다음 '{label}'을(를) 이전 복습·대화에 나온 물질이나 사례와 다른 새 상황에 적용해 보게 하고, 그렇게 되는 이유도 한 문장 덧붙이게 하는 질문 하나만 하세요. 정답이나 풀이 단서를 주지 마세요.")
                   if (record.get("review_session") or {}).get("extra") else
                   f"'{label}'을(를) 이전과 다른 상황이나 예시로 짧게 복습하게 하는 질문 하나만 하세요. 정답을 먼저 주지 마세요.") + QRULE,
        "review_done": "해요체로 쓰세요. 학습자의 복습 답에서 맞은 부분을 구체적으로 한 문장 인정하고, 복습이 잘 됐다고 짧게 마무리하세요. 새 질문과 새 설명은 하지 마세요.",
        "review_reveal": "해요체로 쓰세요. 복습 질문에 두 번 충분히 답하지 못했습니다. reveal_key_points를 바탕으로 핵심 답을 2~3문장으로 차분히 알려 주고, 강의 자료로 한 번 더 확인해 보라고 권하세요. 질문은 하지 마세요.",
        "wrap_up_check": reveal_first + to_wrap + wrap_instruction,
        "wrap_up_summary": (reveal_first + to_wrap + "마무리 확인이 끝났습니다. 줄바꿈 목록 없이 3~4문장으로 쓰세요. (1) confirmed_skills가 있으면 잘 확인된 개념을 한 문장으로 먼저 인정하세요. (2) weak_skills는 이름과 아직 부족한 부분(weak_dimensions)을 짧게 알리세요(개념은 확인됐어도 weak_dimensions가 있으면 그 항목만 짚으세요)(정답을 길게 가르치지 마세요). (3) untested_note가 있으면 어느 개념의 어떤 항목이 아직 안 다뤄졌는지 한 문장으로만 알리고 부족하다고 표현하지 마세요. "
                            "(4) not_started_skills가 있으면 아직 시작하지 않은 개념이라고 이름만 한 문장으로 알리세요(약하다고 하지 마세요). weak_skills가 있을 때만 그다음 '복습할지, 다음 단원으로 넘어갈지'를 질문 하나로 물어보세요. 복습 질문은 이번 한 번만 합니다. weak_skills가 비어 있으면 부족한 부분이 없다고 알리고 복습은 권하지 말고 다음에 공부할 방향만 질문 하나로 물어보세요. context의 weak_skills와 untested_note에 없는 부족함은 지어내지 마세요(recent_dialogue의 이전 요약은 낡았을 수 있습니다)."),
        "pause_ack": ("학습자가 지금은 쉬겠다고 했습니다. 해요체로 2~3문장만 쓰세요. (1) 힘들었던 마음을 한 문장으로 받아 주고 쉬어 가는 것이 괜찮다고 하세요. "
                      "(2) 지금까지의 기록은 저장해 두었고 다시 올 때 이어서 할 수 있다고 알리세요. 질문, 새 설명, 정답 공개, 복습 문제는 하지 마세요."),
        "progress_report": ("해요체로 2~3문장만 쓰세요. 학습자가 자신의 학습 현황과 복습할 내용을 물었습니다. 오직 context의 confirmed_skills, weak_skills, untested_note에 있는 사실만 말하세요"
                            "(recent_dialogue의 이전 요약은 낡았을 수 있으니 따르지 마세요). 부족한 항목이 없으면 부족한 부분이 없다고만 하세요. 퀴즈나 새 문제를 내지 말고, "
                            "복습할 항목이 있으면 그 항목을 짚고 '복습하고 싶으면 말씀해 주세요'로 끝내세요. 자세한 표는 /progress에서 볼 수 있다고 한 번 알려도 좋습니다."),
        "closing_ack": "해요체로 쓰세요. 마무리하겠다고 선언하지 말고 학습자의 말에 짧게 반응하세요. 복습을 다시 권하지 말고, 새 주제를 공부하고 싶으면 말씀해 달라고만 안내하세요. 질문은 하지 않아도 됩니다.",
        "offer_direction_choice": ("학습자의 불편을 한 문장으로 인정하고, ① " + ("다른 주제로 넘어가기" if record.get("unit_status") == "completed" else "마무리로 넘어가기" if not record.get("_has_next_open") else "다음 개념으로 넘어가기")
                                   + " ② 이 개념 설명 듣기 ③ 문제로 확인하기 중에서 고르게 하는 질문 하나만 하세요. 같은 질문을 반복하지 마세요."),
        "offer_learner_choice": "현재 완료된 하위 개념의 확인 결과만 간단히 알리고, 더 어려운 적용·복습·다음 개념 중 사용자가 선택하도록 질문 하나만 하세요. 다른 하위 개념의 미확인 상태를 숨기거나 전체 주제 숙달이라고 말하지 마세요.",
        "next_unit_choice": "해요체로 쓰세요. 현재 학습 단위의 미확인 항목은 기록해 둔 채, 다음에 공부할 주제나 범위를 한 가지 질문으로 확인하세요.",
        "goal_clarification": "학습 목표나 범위가 불분명하므로 확인 질문 하나만 하세요. 이미 알려 준 정보는 다시 묻지 마세요.",
        "skip_check": "사용자의 선택을 존중해 현재 확인을 건너뛰고, 미확인으로 남는다고 짧게 알리세요.",
        "continue_task": "현재 진행 중인 과제를 이어가세요. 학습자가 이미 맞힌 부분은 인정하고, 아직 해결하지 못한 가장 작은 단계 하나만 질문하세요.",
        "transfer_task": "새로운 조건의 적용 문제 하나만 제시하세요."
    }
    return instructions.get(action, instructions["diagnostic_question"])


def _make_response(user_text, action, record, assessment, intent):
    recs = record.get("skill_records", {})
    sid = record.get("active_skill_id") or ""
    sk = recs.get(sid, {})
    tr = record.get("transition")
    context = {
        "topic": learning_context.get("topic", ""),
        "goal": learning_context.get("goal", ""),
        "action": action,
        "action_instruction": _build_action_instruction(action, record, intent, assessment),
        "active_skill": {"label": sk.get("label", ""), "state_label": _format_state(sk.get("state", "Unconfirmed"))},
        "transition": tr,
        "wrap_target": record.get("wrap_target") if action == "wrap_up_check" else None,
        "explanation_strategy": record.get("current_strategy"),
        "active_task": record.get("active_task"),
        "practice_session": record.get("practice_session"),
        "recent_dialogue": messages[-6:],
        "evidence_note": assessment.get("evidence_note", ""),
        "misconception_note": assessment.get("misconception_note", ""),
        "learner_message": user_text
    }
    # 핵심 요소는 정답을 알려 주거나 설명해야 하는 행동에만 전달한다 (진단 질문에 단서가 새지 않도록).
    if action in ("full_explanation", "practice", "review", "partial_explanation", "prerequisite_explanation"):
        context["explain_key_points"] = sk.get("key_points", [])
    if action in ("hint", "guided_question"):
        # 힌트가 향할 목표 핵심 요소 하나 (직접 말하지 않고 그쪽으로 이끄는 단서용). 평가기가 짚은 빠진 요소를 우선한다.
        kps = sk.get("key_points", [])
        context["target_key_point"] = (assessment.get("missing_key_point") or (kps[0] if kps else ""))
    if action == "review_reveal":
        context["reveal_key_points"] = sk.get("key_points", [])
    if assessment.get("out_of_scope_error") and action not in ("pause_ack", "closing_ack"):
        context["out_of_scope_error"] = str(assessment.get("out_of_scope_error"))[:200]
    if tr and tr.get("how") == "revealed" and tr.get("closed_sid") in recs:
        context["reveal_key_points"] = recs[tr["closed_sid"]].get("key_points", [])
    if action in ("wrap_up_summary", "progress_report"):
        context.update(_summary_parts(record))
    response = client.responses.create(
        model=MODEL,
        instructions=RESPONSE_PROMPT,
        input=json.dumps(context, ensure_ascii=False)
    )
    return response.output_text.strip()


def _safe_short_response(text, limit=MAX_RESPONSE_CHARS):
    text = re.sub(r"\n{3,}", "\n\n", str(text)).strip()
    if len(text) <= limit:
        return text
    # Prefer a complete sentence boundary; avoid cutting a learner-facing question in half.
    candidates = [text.rfind(mark, 0, limit) for mark in ("。", "！", "？", ".", "!", "?")]
    cut = max(candidates)
    if cut >= int(limit * 0.55):
        return text[:cut + 1].strip()
    # Otherwise keep a safe prefix and close it.
    return text[:limit - 1].rstrip() + "…"


def _count_questions(text):
    """물음표 문장 + '~해 주세요' 식 요청 문장을 센다 (문장당 1회)."""
    n = 0
    for sent in re.split(r"(?<=[.!?？。])\s+|\n+", str(text)):
        if re.search(r"[?？]", sent) or re.search(r"(?:설명|말씀|알려|말해|적어|답해|골라|덧붙여|써|풀어|구해|정리해|들어|짚어)\s*(?:해\s*)?주세요", sent) \
                or re.search(r"(?:설명해|말해|적어|답해|정리해|덧붙여|써)\s*보세요", sent):
            n += 1
    return n


def _formal_tone_found(text):
    return bool(re.search(r"(?:습니다|입니다|합니다|ㅂ니다)[.!?]?(?:\s|$)", str(text)))


def _display_turn(response_text, record):
    """튜터 응답 + 현재 개념의 State 한 줄만 표시한다. 전체 기록은 /progress 에서만 (피드백 5번)."""
    display(Markdown(response_text))
    p = progress_summary(record)
    skills = p.get("skills", [])
    total = len(skills)
    done = sum(1 for x in skills if x.get("closed") and not x.get("unvisited"))
    active_sid = record.get("active_skill_id")
    active = next((x for x in skills if x.get("skill_id") == active_sid), None)
    if record.get("wrap_up_active"):
        where = "마무리 확인 중"
    elif record.get("unit_status") == "completed":
        where = "학습 단위 완료"
    else:
        where = f"현재 개념: {active.get('label')}" if active else "설정 중"
    state_text = f" · 상태: {active.get('state_label')}" if active else ""
    if record.get("unit_status") == "completed":
        state_text = ""      # 단원이 끝나면 한 개념의 State가 전체처럼 보이지 않게 개념별 상태는 /progress에서만 본다
    line = f'<div style="font-size:12px;color:#64748b;margin:6px 0 14px;">{html.escape(where)}{html.escape(state_text)} · 진행 {done}/{total} (전체 기록은 /progress)</div>'
    display(HTML(line))


def _build_start_router_input(user_text):
    """The JSON-mode requirement must appear in the input message, not only instructions."""
    return (
        "LEARNER MESSAGE:\n" + str(user_text).strip()
        + "\n\nOUTPUT FORMAT REQUIREMENT: Return the result as a valid JSON object. "
          "The response must be JSON with the keys topic, goal, needs_clarification, "
          "clarification_question, intent, and direct_request. Do not include markdown fences."
    )


def _call_start_router(user_text):
    """Parse only the learning request. This call never evaluates learner knowledge."""
    router_input = _build_start_router_input(user_text)
    response = client.responses.create(
        model=MODEL,
        instructions=START_ROUTER_PROMPT + "\nReturn a JSON object. JSON output is mandatory.",
        input=router_input,
        text={"format": {"type": "json_object"}}
    )
    data = json.loads(response.output_text)
    raw_intent = str(data.get("intent") or "structured_learning").strip().lower()
    intent_aliases = {
        "memorization": "study_strategy", "memorization_help": "study_strategy",
        "study_method": "study_strategy", "study_advice": "study_strategy",
        "explain": "direct_explanation", "explanation": "direct_explanation",
        "solve": "practice", "problem_solving": "practice",
        "learn": "structured_learning", "continue": "structured_learning"
    }
    normalized_intent = intent_aliases.get(raw_intent, raw_intent)
    if normalized_intent not in {"structured_learning", "study_strategy", "direct_explanation", "practice", "other"}:
        normalized_intent = "structured_learning"
    return {
        "topic": str(data.get("topic") or "").strip()[:150],
        "goal": str(data.get("goal") or "").strip()[:250],
        "needs_clarification": bool(data.get("needs_clarification", False)),
        "clarification_question": str(data.get("clarification_question") or "어떤 구체적인 주제를 공부하고 싶으세요?").strip()[:300],
        "intent": normalized_intent,
        "direct_request": str(data.get("direct_request") or "").strip()[:500]
    }


def _generate_study_strategy(topic, learner_request, additional=False, previous=""):
    """Give topic-specific study-method advice without forcing a sub-concept registry."""
    prompt = {"topic": topic, "learner_request": learner_request, "additional_advice": bool(additional), "previous_advice": previous[-900:]}
    instructions = r"""
You are a practical study coach. The learner asked for a way to memorize or retain material, and may also have asked for an explanation of the principle.
Write in polite Korean (해요체) only.
- If the learner also asked to explain the principle, first explain it in 3-4 short sentences.
- Then give concrete, topic-specific study advice: a sequence/map-based approach (big flow first, attach each stage to a place or cue, connect inputs/outputs, then active recall and spaced review).
- Include one short example tailored to the topic and one simple first action the learner can do now.
If additional_advice is true, provide a genuinely different or more detailed technique rather than repeating the first answer.
FORMAT: plain conversational Korean, at most 450 characters in total, 4-6 short lines. No headings, no tables, no bold markers, no emoji. Give ONE technique, one tiny example, one first action. Finish every sentence; never trail off.
If previous_advice is present, use a technique that is clearly different from it and do not repeat its example.
Do not generate a sub-concept registry, quiz question, or assess understanding.
"""
    response = client.responses.create(model=MODEL, instructions=instructions,
                                       input=json.dumps(prompt, ensure_ascii=False))
    return _safe_short_response(response.output_text.strip(), limit=MAX_EXPLAIN_CHARS + 300)


def _json_call(instructions, payload):
    """JSON 모드 호출. 입력 메시지에 'JSON'이 반드시 들어가야 API가 받아 준다. 오류는 삼키지 않고 호출한 쪽에 전달한다."""
    text_in = json.dumps(payload, ensure_ascii=False) + "\n\nOutput requirement: Return the result as a valid JSON object only."
    response = client.responses.create(model=MODEL, instructions=instructions, input=text_in,
                                       text={"format": {"type": "json_object"}})
    return json.loads(response.output_text)


def _handle_strategy_followup(user_text):
    """Interpret what the learner wants after receiving study-strategy advice."""
    global learning_phase, pending_study_strategy, pending_new_unit
    pending = pending_study_strategy or {}
    context = {
        "phase": "awaiting_strategy_followup",
        "topic": pending.get("topic", ""),
        "original_request": pending.get("request", ""),
        "assistant_offer": "The learner may start structured learning using this strategy, ask for more advice, or change topic.",
        "learner_message": user_text
    }
    instructions = r"""
Classify the learner's intent in context. Return JSON only:
{"decision":"start_learning|more_advice|change_topic|unclear","new_topic":"","reason":""}
- start_learning: clearly wants to begin studying the already identified topic in a structured way.
- more_advice: asks for more memorization/study advice, examples, or a different technique.
- change_topic: explicitly wants to study a different topic; extract it in new_topic.
- unclear: no clear choice or just an acknowledgment that does not specify what to do.
Interpret the full natural-language meaning, not a fixed keyword list. Do not treat mere politeness as consent.
"""
    try:
        data = _json_call(instructions, context)
        decision = data.get("decision")
        if decision not in ("start_learning", "more_advice", "change_topic", "unclear"):
            decision = "unclear"
    except Exception as exc:
        # 분류 호출 자체가 실패한 것은 '의도가 불분명한 것'이 아니다: 원인을 알리고 안전하게 이어간다.
        print("의도 확인 중 오류가 있었어요:", repr(exc))
        decision = "unclear"
        data = {"_error": True}
    # 같은 안내를 반복하지 않는다 (규칙 1·2): 두 번 연속 불분명하면 이미 정한 주제로 구조화 학습을 시작한다.
    if decision == "unclear":
        pending["unclear_count"] = pending.get("unclear_count", 0) + 1
        if pending["unclear_count"] >= 2:
            decision = "start_learning"
    else:
        pending["unclear_count"] = 0
    if decision == "start_learning":
        topic = pending.get("topic", "")
        pending_study_strategy = None
        learning_context.update({"topic": "", "goal": "", "concept_id": ""})
        learning_phase = "awaiting_topic"
        pending_new_unit = True
        pending_start_requests.clear()
        return _handle_learning_start(topic, force_new=True)
    if decision == "more_advice":
        try:
            advice = _generate_study_strategy(pending.get("topic", ""), user_text, additional=True, previous=pending.get("last_advice", ""))
            pending["last_advice"] = advice
            print(advice)
            print("이 방법을 적용해 학습을 시작하거나, 다른 암기 전략을 더 요청해도 돼요.")
            messages.extend([{"role":"user","content":user_text},{"role":"assistant","content":advice}])
        except Exception as exc:
            print("학습 전략 생성 오류:", repr(exc))
            print("원하는 암기 방식이나 어려운 부분을 조금 더 구체적으로 말씀해 주세요.")
        return True
    if decision == "change_topic":
        pending_study_strategy = None
        learning_context.update({"topic": "", "goal": "", "concept_id": ""})
        learning_phase = "awaiting_topic"
        pending_new_unit = True
        return _handle_learning_start(data.get("new_topic") or user_text, force_new=True)
    print("이 주제로 바로 학습을 시작할까요, 아니면 암기 전략을 더 볼까요? \"학습 시작\"이나 \"전략 더\"처럼 짧게 말씀해 주셔도 돼요.")
    _dbg("[Controller] Phase: awaiting_strategy_followup | Evidence: none | State: unchanged")
    return True


def _handle_learning_start(user_text, force_new=False):
    """Handle initial topic acquisition or an explicit new-unit request; never evaluates knowledge."""
    global learning_phase, awaiting_registry_confirmation, pending_new_unit, pending_post_explanation_check
    global pending_study_strategy
    if learning_context.get("topic") and not force_new:
        return False
    text = str(user_text).strip()
    # 주제를 다시 묻는 동안 받은 요청(설명·암기법·문제 출제 등)을 버리지 않고 함께 해석한다.
    combined = "\n".join(pending_start_requests + [text])
    try:
        route = _call_start_router(combined)
    except Exception as e:
        print("학습 주제 확인 단계 오류:", repr(e))
        print("아직 학습 상태를 평가하지 않았어요. 구체적인 학습 주제를 다시 입력해 주세요.")
        return True

    topic = route["topic"]
    direct_request = route.get("direct_request", "") or ""
    # 막힘·어려움 표현은 요청이 아니다: 문자 그대로의 요청어가 없으면 먼저 설명하지 않고 진단부터 시작한다.
    if not re.search(r"설명|알려|가르|문제|출제|풀어|암기|외우|정리|요약|예시|예를 들|해줘|해 줘|뭐야|뭐예요|뭔데", combined):
        direct_request = ""
        if route.get("intent") in ("direct_explanation", "practice"):
            route["intent"] = "structured_learning"
    if not topic or route["needs_clarification"]:
        pending_start_requests.append(text)
        question = route["clarification_question"] or "어떤 구체적인 주제를 공부하고 싶으세요?"
        messages.extend([{"role": "user", "content": text}, {"role": "assistant", "content": question}])
        learning_phase = "awaiting_topic"
        if force_new:
            pending_new_unit = True
        print(question)
        _dbg("[Controller] Phase: awaiting_topic | Evidence: none | State: unchanged")
        return True

    goal = route["goal"] or "핵심 개념을 이해하고 새로운 상황에 적용하기"
    route_intent = route.get("intent", "structured_learning")
    request_text = direct_request or combined

    if route_intent == "study_strategy":
        pending_study_strategy = {"topic": topic, "request": combined}
        learning_context.update({"topic": topic, "goal": goal, "concept_id": ""})
        learning_phase = "awaiting_strategy_followup"
        pending_start_requests.clear()
        try:
            advice = _generate_study_strategy(topic, combined)
            pending_study_strategy["last_advice"] = advice
            messages.extend([{"role": "user", "content": combined}, {"role": "assistant", "content": advice}])
            print(advice)
            print("원하시면 이 방법을 적용해 함께 학습을 시작하거나, 암기 전략을 더 구체적으로 살펴볼 수 있어요.")
            _dbg("[Controller] Phase: awaiting_strategy_followup | Evidence: none | State: unchanged")
        except Exception as e:
            print("학습 전략 생성 오류:", repr(e))
            print("요청하신 주제와 암기하기 어려운 부분을 조금 더 말씀해 주시면 맞춰서 도와드릴게요.")
            _dbg("[Controller] Phase: awaiting_strategy_followup | Evidence: none | State: unchanged")
        return True

    cid = _safe_id(topic)
    if force_new or pending_new_unit:
        pending_post_explanation_check = False
        awaiting_registry_confirmation = False
    learning_context.update({"topic": topic, "goal": goal, "concept_id": cid})
    record = concept_records.setdefault(cid, _new_record())
    messages.append({"role": "user", "content": combined})

    # 규칙 1: 첫 메시지에 담긴 요청(설명·문제 출제 등)은 진단보다 먼저 처리한다.
    if direct_request or route_intent in ("direct_explanation", "practice"):
        try:
            answer = _answer_first_request(topic, request_text, route_intent)
            print(answer)
            messages.append({"role": "assistant", "content": answer})
        except Exception as e:
            print("요청 답변 생성 오류:", repr(e))
            print("요청하신 내용은 학습을 진행하면서 다시 다룰게요.")

    try:
        initialize_skill_registry(record)
        if not record.get("skill_registry"):
            raise ValueError("Registry is empty")
    except Exception as e:
        learning_context.update({"topic": "", "goal": "", "concept_id": ""})
        messages.clear()
        pending_start_requests.clear()
        learning_phase = "awaiting_topic"
        print("하위 개념 목록 생성 오류:", repr(e))
        print("증거 평가는 시작하지 않았어요. 주제를 다시 입력해 주세요.")
        return True
    pending_start_requests.clear()

    learning_phase = "awaiting_registry_confirmation"
    awaiting_registry_confirmation = True
    pending_new_unit = False
    print(f"\n학습 주제: {topic}")
    _print_registry(record, "다음 하위 개념으로 나누어 학습할게요:")
    confirmation_prompt = "이 구성이 괜찮으세요? 바꾸고 싶은 항목이 있으면 말씀해 주세요."
    print(confirmation_prompt)
    messages.append({"role": "assistant", "content": confirmation_prompt})
    _dbg("[Controller] Phase: awaiting_registry_confirmation | Evidence: none | State: unchanged")
    return True


def _classify_registry_confirmation(user_text, record):
    """Understand a registry-confirmation reply from its full meaning and dialogue context."""
    recent = messages[-6:]
    context = {
        "phase": "awaiting_registry_confirmation",
        "topic": learning_context.get("topic", ""),
        "goal": learning_context.get("goal", ""),
        "proposed_skills": record.get("skill_registry", {}),
        "recent_dialogue": recent,
        "learner_message": str(user_text)
    }
    instructions = r"""
You classify the learner's intent while they are reviewing a proposed list of sub-concepts.
Interpret the COMPLETE message in context, not by matching a list of keywords.
Return JSON only:
{"decision":"confirm|revise|other_request|unclear","revision_request":"","reason":""}

Rules:
- confirm: decide whether the learner's communicative intent is to accept the current proposal and proceed. Short, colloquial, indirect, abbreviated, or nonstandard expressions ("좋은데?", "ㅇㅋ", "그대로 가자") are clear confirmation when the context makes the meaning clear.
- revise: the learner wants to change THE LIST itself: remove, add, regroup, reorder, rename, or switch topic. Extract the requested changes in revision_request.
- other_request: the learner asks a question or makes a request that is NOT an edit of the list (for example asks you to explain something, make exam questions, or teach a memorization method). Such a request must be answered first; it is never a list revision.
- unclear: use only when the message genuinely does not reveal whether the learner wants to proceed, revise, or ask something.
- If the message contains both approval and a requested change to the list, choose revise.
- Do not mistake a question for confirmation. Do not overuse unclear: when a reasonable partner would understand the learner is accepting the proposal, choose confirm.
- Keep revision_request empty unless the decision is revise.
"""
    try:
        data = _json_call(instructions, context)
        decision = data.get("decision")
        if decision not in ("confirm", "revise", "other_request", "unclear"):
            return {"decision": "unclear", "revision_request": "", "reason": "판정 결과가 유효하지 않습니다."}
        return {
            "decision": decision,
            "revision_request": str(data.get("revision_request") or "").strip()[:500] if decision == "revise" else "",
            "reason": str(data.get("reason") or "").strip()[:300]
        }
    except Exception as exc:
        # Fail closed: never start learning when confirmation could not be interpreted. 단, 오류는 알린다.
        print("의도 확인 중 오류가 있었어요:", repr(exc))
        return {"decision": "unclear", "revision_request": "", "reason": "의도 판정에 실패했습니다."}


def _revise_pending_registry(user_text):
    """Interpret an explicit registry edit request, replace the map, and ask for confirmation."""
    global learning_phase, awaiting_registry_confirmation
    record = _record()
    prompt = f"""The learner is revising the proposed sub-concept registry for this learning unit.
Current topic: {learning_context.get('topic','')}
Learning goal: {learning_context.get('goal','')}
Current registry: {json.dumps([{'id':k,'label':v,'key_points':record.get('skill_records',{}).get(k,{}).get('key_points',[])} for k,v in record.get('skill_registry',{}).items()], ensure_ascii=False)}
Learner's requested revision: {user_text}

Return JSON only: {{"skills":[{{"id":"short_snake_case_id","label":"Korean learner-facing label","key_points":["핵심 요소 1","핵심 요소 2"]}}]}}
Rules:
- Follow the learner's explicit requested grouping/count and labels as closely as possible.
- Keep concepts distinct and non-overlapping. Keep 3-5 concepts unless the learner asked for a different count.
- Keep an unchanged concept's id, label and key_points as they are. Every skill needs 2-3 key_points.
- Apply ONLY edits to the list. A question or a request (explain, exam questions, memorization) is never a concept; never turn it into one, and never rename concepts into quiz items ("~문제").
- Use stable short IDs in English snake_case.
- Do not add more concepts than requested. If they request three, return exactly three.
- This is registry editing only; do not assess learner understanding or create evidence."""
    result = client.responses.create(
        model=MODEL,
        instructions="Revise the sub-concept registry exactly as requested. Return valid JSON only.",
        input=prompt,
        text={"format": {"type": "json_object"}}
    )
    skills = json.loads(result.output_text).get("skills", [])
    if not skills:
        raise ValueError("Revised registry is empty")
    set_skill_registry(skills, record)
    record["dimensions"] = {"concept": "unknown", "reasoning": "unknown", "transfer": "unknown"}
    record["latest_dimensions"] = {"concept": "unknown", "reasoning": "unknown", "transfer": "unknown"}
    learning_phase = "awaiting_registry_confirmation"
    awaiting_registry_confirmation = True
    _print_registry(record, "수정한 하위 개념 구성은 다음과 같아요:")
    confirmation_prompt = "이 구성이 괜찮으면 그대로 진행할게요. 더 바꾸고 싶은 내용이 있으면 말씀해 주세요."
    print(confirmation_prompt)
    messages.append({"role": "assistant", "content": confirmation_prompt})
    _dbg("[Controller] Phase: awaiting_registry_confirmation | Evidence: none | State: unchanged")
    return True


def _begin_diagnostic_after_registry_confirmation(user_text):
    """Use contextual LLM intent classification; confirmation is setup metadata, not evidence."""
    global learning_phase, awaiting_registry_confirmation
    record = _record()
    decision = _classify_registry_confirmation(user_text, record)

    if decision["decision"] == "other_request":
        # 목록 확인 중에 다른 질문·요청이 오면 먼저 답하고 확인으로 돌아온다 (피드백 1번).
        try:
            answer = _answer_first_request(learning_context.get("topic", ""), user_text, "auto")
            print(answer)
            messages.extend([{"role": "user", "content": user_text}, {"role": "assistant", "content": answer}])
        except Exception as e:
            print("요청 답변 생성 오류:", repr(e))
        follow = "하위 개념 구성은 그대로 두었어요. 이대로 진행할까요? 바꾸고 싶은 항목이 있으면 말씀해 주세요."
        print(follow)
        messages.append({"role": "assistant", "content": follow})
        _dbg("[Controller] Phase: awaiting_registry_confirmation | Evidence: none | State: unchanged")
        return True

    if decision["decision"] == "revise":
        revision_text = decision["revision_request"] or user_text
        try:
            return _revise_pending_registry(revision_text)
        except Exception as e:
            print("하위 개념 구성 수정 오류:", repr(e))
            print("기존 구성은 유지했어요. 원하시는 변경 내용을 다시 말씀해 주세요.")
            _dbg("[Controller] Phase: awaiting_registry_confirmation | Evidence: none | State: unchanged")
            return True

    if decision["decision"] != "confirm":
        print("이 구성으로 진행할지, 고치고 싶은 부분이 있는지 편하게 말씀해 주세요.")
        _dbg("[Controller] Phase: awaiting_registry_confirmation | Evidence: none | State: unchanged")
        return True

    awaiting_registry_confirmation = False
    learning_phase = "diagnosing"
    sid, label = next(iter(record["skill_registry"].items()))
    record["active_skill_id"] = sid
    try:
        prior_vulnerable = _cross_unit_vulnerabilities(learning_context.get("concept_id"))
        confirm_input = {"topic": learning_context["topic"], "goal": learning_context["goal"],
                         "first_skill": label, "instruction": "Ask one diagnostic question only. Output polite Korean (해요체)."}
        confirm_instructions = START_CONFIRM_PROMPT
        if prior_vulnerable:
            confirm_input["prior_misconceptions_from_other_units"] = prior_vulnerable
            confirm_instructions = START_CONFIRM_PROMPT + PRIOR_VULNERABILITY_RULE
            _trace_event({"type": "aux_rule_2", "turn_after": len(logs), "first_skill": label,
                          "prior_misconceptions": prior_vulnerable})
        q = client.responses.create(model=MODEL, instructions=confirm_instructions,
            input=json.dumps(confirm_input, ensure_ascii=False))
        question = _safe_short_response(q.output_text.strip())
    except Exception as e:
        learning_phase = "awaiting_registry_confirmation"
        awaiting_registry_confirmation = True
        print("진단 질문 생성 오류:", repr(e))
        print("하위 개념 구성은 저장되어 있어요. 다시 진행 의사를 말씀해 주시면 질문 생성을 다시 시도할게요.")
        return True
    messages.extend([{"role": "user", "content": user_text}, {"role": "assistant", "content": question}])
    record["last_action"] = "diagnostic_question"
    _ensure_skill_fields(record["skill_records"][sid])["ask_count"] = 1
    record["active_task"] = {"kind": "diagnostic_question", "skill_id": sid,
                             "label": label, "prompt": question, "required_outcome": label,
                             "attempt_count": 0}
    print(question)
    _dbg("[Controller] Phase: diagnosing | Evidence: none | State: unchanged")
    return True


def study_turn(user_text, forced_intent=None):
    global pending_post_explanation_check
    if not user_text or not user_text.strip():
        print("내용을 입력해 주세요.")
        return
    # Topic-switch and setup gates run BEFORE the evidence evaluator.
    # A new subject is a new learning unit, not an unmapped answer in the old registry.
    global learning_phase, awaiting_registry_confirmation, pending_new_unit, pending_study_strategy
    if learning_phase == "awaiting_strategy_followup" and pending_study_strategy:
        return _handle_strategy_followup(user_text)
    if _is_explicit_topic_switch_request(user_text) and learning_context.get("topic"):
        # Preserve the previous unit in concept_records; only clear the active
        # dialogue/task context before routing the new learner request.
        messages.clear()
        pending_post_explanation_check = False
        pending_start_requests.clear()
        pending_new_unit = True
        learning_phase = "awaiting_topic"
        awaiting_registry_confirmation = False
        _handle_learning_start(user_text, force_new=True)
        return
    if pending_new_unit or learning_phase == "awaiting_topic" or not learning_context.get("topic"):
        if _handle_learning_start(user_text, force_new=pending_new_unit):
            return
    if awaiting_registry_confirmation or learning_phase == "awaiting_registry_confirmation":
        _begin_diagnostic_after_registry_confirmation(user_text)
        return

    if not learning_context.get("concept_id"):
        learning_context["concept_id"] = _safe_id(learning_context.get("topic") or "general")
        concept_records.setdefault(learning_context["concept_id"], _new_record())

    record = _record()
    turn_id = len(logs) + 1
    active_task_before = record.get("active_task")
    if not record.get("registry_locked") or not record.get("skill_registry"):
        try:
            initialize_skill_registry(record)
        except Exception as e:
            print("하위 개념 목록 생성 오류:", repr(e))
            print("증거 평가를 실행하지 않았어요. 학습 주제를 확인해 주세요.")
            return
    for _sk in record.get("skill_records", {}).values():
        _ensure_skill_fields(_sk)

    if forced_intent:
        assessment = _neutral_assessment(record, forced_intent)
    else:
        try:
            assessment = _call_evaluator(user_text, record, turn_id)
        except Exception as e:
            print("평가 단계 오류:", repr(e))
            print("이번 입력은 학습 상태에 반영되지 않았어요.")
            return

    intent = forced_intent or _detect_explicit_intent(user_text, assessment.get("intent", "continue"))
    if intent == "explain" and assessment.get("explicit_explain_request") is False:
        # "모르겠어"는 설명 요청이 아니라 막힘 신호다: 질문→힌트→(답 안내) 순서로 도움을 올린다 (규칙 6).
        intent = "continue"
        assessment["learner_stuck"] = True
    if intent in NON_EVIDENCE_INTENTS:
        # 질문·요청·진행 방식 선택은 이해 증거가 아니다 (규칙 3).
        assessment["has_content_attempt"] = False

    # Strict registry validation: never silently create or merge a skill from model output.
    practice_session = record.get("practice_session") or {}
    proposed_sid = _safe_id(assessment.get("skill_id") or "")
    if practice_session.get("active") and intent == "continue":
        # Keep the practice goal stable.
        record["active_skill_id"] = practice_session.get("target_skill_id")
    if record.get("wrap_up_active") and record.get("wrap_target") and intent == "continue":
        # 마무리 확인의 답은 질문한 개념의 증거로만 기록한다.
        proposed_sid = record["wrap_target"]["skill_id"]
    if proposed_sid not in record.get("skill_registry", {}) and intent != "continue":
        # 진행 방식 선택·질문·요청은 증거가 아니므로 현재 개념을 기준으로 그대로 처리한다.
        fallback = record.get("active_skill_id")
        if fallback not in record.get("skill_registry", {}):
            fallback = next(iter(record.get("skill_registry", {})), None)
        if fallback:
            proposed_sid = fallback
    if proposed_sid not in record.get("skill_registry", {}):
        # Never expose internal registry-edit commands to learners. Explicit topic
        # switches are handled above; otherwise ask naturally whether this is a new unit.
        if proposed_sid == "__UNMAPPED__":
            print("이 내용은 현재 학습 중인 하위 개념과 직접 연결되지 않아 이해도 증거로 기록하지 않았어요.")
            print("새로운 학습 주제로 전환하려면 구체적인 주제를 말씀해 주세요. 이미 알려 주신 정보는 다시 묻지 않을게요.")
            _dbg("[Controller] Phase: learning | Evidence: none | State: unchanged")
        else:
            print("현재 학습 범위와 연결되는 하위 개념을 확인하지 못해 이번 입력은 증거에 반영하지 않았어요.")
            print("새로운 주제를 공부하려면 구체적인 개념을 말씀해 주세요.")
            _dbg("[Controller] Phase: learning | Evidence: none | State: unchanged")
        return
    assessment["skill_id"] = proposed_sid
    assessment["skill_label"] = record["skill_registry"][proposed_sid]

    learning_phase = "learning"
    # 규칙 6: 직전 턴에 도움(힌트·설명·정답 안내)을 준 바로 그 개념의 답만 hint_assisted로 취급한다.
    hint_used = (record.get("last_help_turn") == turn_id - 1 and record.get("last_help_sid") == proposed_sid)
    old_skill_state, new_skill_state, transition_reason = apply_state_controller(
        record, assessment, turn_id, hint_used=hint_used,
        skip_evidence=(intent == "skip_check")
    )

    if active_task_before and assessment.get("has_content_attempt"):
        active_task_before["attempt_count"] = active_task_before.get("attempt_count", 0) + 1
        active_task_before["last_learner_attempt_turn"] = turn_id
        active_task_before["last_completion_note"] = str(assessment.get("task_completion_note", ""))[:400]

    action = choose_action(record, intent, assessment)
    tr = record.get("transition")

    # 규칙 7: 설명 방식은 같은 것을 반복하지 않고 순환한다.
    record["current_strategy"] = None
    explain_sid = None
    if action in EXPLANATION_ACTIONS or (tr and tr.get("how") == "revealed"):
        explain_sid = tr["closed_sid"] if (tr and tr.get("how") == "revealed") else (record.get("active_skill_id") or proposed_sid)
        if explain_sid in record["skill_records"]:
            record["current_strategy"] = _pick_strategy(record["skill_records"][explain_sid])
    if action in HELP_ACTIONS or (tr and tr.get("how") == "revealed"):
        record["last_help_sid"] = explain_sid or record.get("active_skill_id") or proposed_sid
        record["last_help_turn"] = turn_id

    if action == "offer_learner_choice":
        record["awaiting_learner_choice"] = True
    elif intent in ("practice", "review", "next_unit", "skip_check", "finish_unit", "pause_session", "progress_query"):
        record["awaiting_learner_choice"] = False
    record["last_action"] = action

    try:
        response_text = _make_response(user_text, action, record, assessment, intent)
    except Exception as e:
        print("응답 생성 단계 오류:", repr(e))
        print("평가와 상태 기록은 저장되었지만, 사용자 응답 생성에 실패했어요.")
        return

    if action in ("hint", "guided_question") and len(response_text) > MAX_HINT_CHARS:
        # 힌트가 설명으로 변하면 다시 쓰게 한다 (규칙 6: 한 턴에 도움 한 단계만).
        repair = client.responses.create(
            model=MODEL,
            instructions=RESPONSE_PROMPT + "\nRewrite as a SINGLE-STEP hint: at most 2 short Korean sentences (about 150 characters), mention at most ONE concept as a cue, do not list the functions of several things, do not give or imply the answer, and end with exactly one easier question.",
            input=response_text
        )
        response_text = repair.output_text.strip()
    response_text = _safe_short_response(response_text, limit=_limit_for(action, record))
    if action == "wrap_up_check":
        record["wrap_up_questions_asked"] += 1
    elif action == "wrap_up_summary":
        record["wrap_up_active"] = False
        record["wrap_target"] = None
        record["unit_status"] = "completed"
        record["review_offered"] = True

    if _count_questions(response_text) > MAX_QUESTIONS:
        repair = client.responses.create(
            model=MODEL,
            instructions=RESPONSE_PROMPT + "\nRewrite with at most ONE learner-facing question. Preserve the task and do not introduce additional sub-questions.",
            input=response_text
        )
        response_text = _safe_short_response(repair.output_text.strip(), limit=_limit_for(action, record))
    if _count_questions(response_text) > MAX_QUESTIONS:
        marks = [m.start() for m in re.finditer(r"[?？]", response_text)]
        response_text = response_text[:marks[1]].strip()

    # Save the generated task prompt so the evaluator can judge the next answer.
    if action in TASK_ACTIONS:
        sid = proposed_sid if action == "full_explanation" else (record.get("active_skill_id") or proposed_sid)
        skill = record.get("skill_records", {}).get(sid, {})
        if action in ASK_COUNT_ACTIONS and sid in record.get("skill_records", {}):
            skill["ask_count"] = skill.get("ask_count", 0) + 1     # 같은 개념에서 질문은 최대 2번
        previous_task = record.get("active_task")
        record["active_task"] = {
            "kind": action,
            "skill_id": sid,
            "skill_label": skill.get("label", assessment.get("skill_label", sid)),
            "created_turn": turn_id,
            "attempt_count": 0,
            "status": "open",
            "prompt": response_text[:1200],
            "required_outcome": "Answer the single learner-facing task and provide requested reasoning if requested.",
            "last_prompt": response_text[:1200],
            "target_dimension": (record.get("wrap_target") or {}).get("dimension") if action == "wrap_up_check" else None
        }
    else:
        record["active_task"] = None

    messages.append({"role": "user", "content": user_text})
    messages.append({"role": "assistant", "content": response_text})

    log = {
        "turn_id": turn_id,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "concept_id": learning_context["concept_id"],
        "topic": learning_context.get("topic", ""),
        "goal": learning_context.get("goal", ""),
        "user_input": user_text,
        "intent": intent,
        "applied_rules": ACTION_RULES.get(action, []),
        "target_skill_id": assessment.get("skill_id", ""),
        "previous_skill_state": old_skill_state,
        "current_skill_state": new_skill_state,
        "concept": assessment.get("concept", "unknown"),
        "reasoning": assessment.get("reasoning", "unknown"),
        "transfer": assessment.get("transfer", "unknown"),
        "concept_source": assessment.get("concept_source", "unknown"),
        "reasoning_source": assessment.get("reasoning_source", "unknown"),
        "transfer_source": assessment.get("transfer_source", "unknown"),
        "key_points_covered": assessment.get("key_points_covered", 0),
        "missing_key_point": assessment.get("missing_key_point", ""),
        "task_complete": bool(assessment.get("task_complete", False)),
        "next_action": action,
        "core_misconception": bool(assessment.get("core_misconception", False)),
        "vulnerability": record.get("vulnerability", "unknown"),
        "evidence_note": assessment.get("evidence_note", ""),
        "transition_reason": transition_reason,
        "closed_skill": (tr or {}).get("closed_sid"),
        "closed_how": (tr or {}).get("how"),
        "rule_check": _rule_check(response_text, action, old_skill_state, new_skill_state, record),
        "response": response_text
    }
    logs.append(log)
    _display_turn(response_text, record)
    if SHOW_CONTROLLER_DEBUG:
        print("\n[Controller]")
        active_sid_for_log = record.get("active_skill_id") or assessment.get("skill_id")
        active_state_for_log = record.get("skill_records", {}).get(active_sid_for_log, {}).get("state", "Unconfirmed")
        print(f"Active skill: {active_sid_for_log} | State: {active_state_for_log} | Evaluated skill transition: {old_skill_state} -> {new_skill_state} | Next action: {action} | Intent: {intent}")
        print("Transition reason:", transition_reason)
        print("Evidence:", assessment.get("evidence_note", ""))
        print("Rule check:", log["rule_check"])


def _dbg(msg):
    """개발자용 로그는 SHOW_CONTROLLER_DEBUG=True 일 때만 보인다 (피드백 5번)."""
    if SHOW_CONTROLLER_DEBUG:
        print(msg)


def _limit_for(action, record):
    tr = record.get("transition") or {}
    if action in ("full_explanation", "reveal_and_next", "wrap_up_summary", "review_reveal", "practice"):
        return MAX_EXPLAIN_CHARS
    if action in ("hint", "guided_question"):
        return MAX_HINT_CHARS      # 규칙 6: 힌트는 한 단계만, 짧게
    if tr.get("how") == "revealed" and action in ("wrap_up_check",):
        return MAX_EXPLAIN_CHARS
    return MAX_RESPONSE_CHARS


def _summary_parts(record):
    """규칙 10: 요약용. 약한 개념(C 미확인/답 안내/건너뜀/오개념)과 잘 확인된 개념, 아직 다루지 않은 R·T를 분리한다."""
    weak, ok, untested, not_started = [], [], [], []
    for sid, label in record.get("skill_registry", {}).items():
        sk = record.get("skill_records", {}).get(sid, {})
        dims = sk.get("dimensions", {})
        name = sk.get("label", label)
        if sk.get("unvisited"):
            not_started.append(name)
            continue
        concept_ok = dims.get("concept") == "confirmed"
        weak_dims = [n for k, n in (("concept", "개념"), ("reasoning", "이유 설명"), ("transfer", "새 상황 적용"))
                     if dims.get(k, "unknown") in ("missing", "partial")]
        if concept_ok and not weak_dims and (sk.get("rechecked") or (not sk.get("revealed") and sk.get("closed") != "skipped")):
            ok.append(name)
        else:
            weak.append({"label": name, "answer_was_given": bool(sk.get("revealed")),
                         "skipped": sk.get("closed") == "skipped",
                         "concept_status": dims.get("concept", "unknown"),
                         "weak_dimensions": weak_dims or (["개념"] if not concept_ok else [])})
        miss = [n for k, n in (("reasoning", "이유 설명"), ("transfer", "새 상황 적용")) if dims.get(k, "unknown") == "unknown"]
        if miss and name in ok:
            untested.append(f"{name}: {', '.join(miss)}")
    out = {"weak_skills": weak, "confirmed_skills": ok}
    if untested:
        out["untested_note"] = "아직 다루지 않은 항목 — " + "; ".join(untested)
    if not_started:
        out["not_started_skills"] = not_started
    return out


def _weak_skills(record):
    return _summary_parts(record)["weak_skills"]


def _state_tag(state):
    """/progress 패널에서만 State 번호를 함께 보여 준다."""
    return {"State1": " (State 1)", "State2": " (State 2)", "State3": " (State 3)"}.get(state or "", " (확인 전)")


def _progress_panel_html(record):
    """학습 진행 상황 전체 패널 (/progress 입력 시에만 표시)."""
    p = progress_summary(record)
    skills = p.get("skills", [])
    active_sid = record.get("active_skill_id")
    completed = sum(1 for x in skills if x.get("closed") and not x.get("unvisited"))
    total = len(skills)
    topic = learning_context.get("topic") or "학습 주제 설정 중"
    vuln_labels = {"unknown": "아직 평가되지 않음", "low": "낮음", "moderate": "보통", "high": "높음"}
    vuln_text = vuln_labels.get(p.get("vulnerability", "unknown"), str(p.get("vulnerability")))
    status_labels = {
        "confirmed": ("○ 확인", "#15803d", "#dcfce7"),
        "partial": ("△ 부분 확인", "#a16207", "#fef3c7"),
        "missing": ("✕ 보완 필요", "#b91c1c", "#fee2e2"),
        "unknown": ("– 미확인", "#64748b", "#f1f5f9")
    }
    dim_labels = [("concept", "개념 이해 (C)"), ("reasoning", "이유 설명 (R)"), ("transfer", "새 상황 적용 (T)")]
    closed_text = {"confirmed": "개념 확인됨", "revealed": "답 안내 후 마무리에서 재확인", "skipped": "건너뜀(마무리에서 확인)"}
    rows = []
    for idx, item in enumerate(skills, 1):
        skill = record.get("skill_records", {}).get(item.get("skill_id"), {})
        dims = skill.get("dimensions", {})
        dim_html = []
        for key, label in dim_labels:
            text, fg, bg = status_labels.get(dims.get(key, "unknown"), status_labels["unknown"])
            dim_html.append(
                f'<span style="display:inline-block;margin:3px 5px 3px 0;padding:4px 8px;'
                f'border-radius:7px;background:{bg};color:{fg};font-size:12px;">{html.escape(label)}: {text}</span>')
        border = "2px solid #64748b" if item.get("skill_id") == active_sid else "1px solid #e2e8f0"
        note = closed_text.get(item.get("closed") or "", "")
        if item.get("closed") == "confirmed" and skill.get("needs_recheck") and not skill.get("rechecked"):
            note = "도움을 받고 통과 · 마무리에서 재확인"
        elif item.get("closed") == "confirmed" and dims.get("concept") != "confirmed":
            note = "다음으로 넘어감 · 개념은 아직 부분 확인" if not skill.get("rechecked") else "마무리에서 확인했으나 아직 부분적"
        if skill.get("rechecked") and item.get("closed") in ("revealed", "skipped"):
            if dims.get("concept") == "confirmed":
                note = "마무리에서 확인함"
            elif dims.get("concept", "unknown") == "unknown":
                note = "마무리에서 물었지만 확인할 답이 없었어요"
            else:
                note = "마무리에서 확인했으나 아직 부분적"
        if skill.get("unvisited"):
            note = "아직 시작하지 않음"
        rows.append(
            f'<div style="padding:10px 12px;margin:8px 0;border:{border};border-radius:9px;">'
            f'<div style="font-weight:600;margin-bottom:5px;">{idx}. {html.escape(str(item.get("label", "")))}'
            f'<span style="float:right;font-size:12px;color:#64748b;">{html.escape(str(item.get("state_label", "")))}{html.escape(_state_tag(skill.get("state")))}</span></div>'
            f'<div>{"".join(dim_html)}</div>'
            + (f'<div style="font-size:12px;color:#64748b;">{html.escape(note)}</div>' if note else '') + '</div>')
    body = "".join(rows) if rows else '<div style="color:#64748b;">아직 등록된 하위 개념이 없습니다.</div>'
    return f"""
    <div style="font-family:Arial,'Apple SD Gothic Neo',sans-serif;margin:14px 0 18px;border:1px solid #d1d5db;
                border-radius:12px;padding:13px 15px;background:var(--jp-layout-color0,#fff);color:var(--jp-ui-font-color1,#222);">
      <div style="font-size:15px;font-weight:700;margin-bottom:9px;">학습 진행 상황</div>
      <div style="font-size:13px;line-height:1.9;">
        <div><b>현재 주제:</b> {html.escape(str(topic))}</div>
        <div><b>다룬 하위 개념:</b> {completed} / {total}</div>
        <div><b>취약도:</b> {html.escape(vuln_text)}</div>
      </div>
      <div style="margin-top:10px;">{body}</div>
      <div style="font-size:11px;color:#64748b;margin-top:8px;">C: 개념 이해 · R: 이유 설명 · T: 새로운 상황 적용</div>
    </div>"""


def _answer_first_request(topic, request, intent_hint="auto"):
    """규칙 1·피드백 1번: 사용자가 처음부터 요청한 것(설명·암기법·문제 출제 등)은 진단보다 먼저 처리한다."""
    prompt = {"topic": topic, "learner_request": request, "intent_hint": intent_hint}
    instructions = r"""
You are a study tutor answering the learner's explicit request BEFORE any quizzing starts.
Do exactly what was asked, in polite Korean (해요체) only. Never mix 반말.
- Explanation request: explain the principle clearly in 3-6 short sentences, not a textbook dump.
- Memorization / study-method request: give concrete, topic-specific techniques, one short example, and one first action.
- Exam-question request ("N문제 출제"): list exactly N distinct questions as a numbered list. Questions only, no answers unless asked.
- Problem-solving request: solve it step by step, briefly.
If several things were asked, do all of them briefly. Keep it within about 600 Korean characters (an N-question list may be somewhat longer).
Do not ask the learner anything. Do not mention sub-concepts, learning maps, evidence or states.
"""
    response = client.responses.create(model=MODEL, instructions=instructions,
                                       input=json.dumps(prompt, ensure_ascii=False))
    return _safe_short_response(response.output_text.strip(), limit=MAX_EXPLAIN_CHARS + 400)


def _print_registry(record, header):
    print(header)
    for i, label in enumerate(record["skill_registry"].values(), 1):
        print(f"{i}. {label}")   # 내부 ID는 학습자에게 보이지 않는다


def _neutral_assessment(record, intent=""):
    sid = record.get("active_skill_id") or next(iter(record.get("skill_registry", {})), "")
    return {"skill_id": sid, "has_content_attempt": False, "concept": "unknown", "reasoning": "unknown",
            "transfer": "unknown", "concept_source": "unknown", "reasoning_source": "unknown",
            "transfer_source": "unknown", "core_misconception": False,
            "calculation_or_notation_error_only": False, "evidence_note": "학습자가 직접 진행 방식을 선택함",
            "task_complete": False, "learner_stuck": False, "same_strategy_failed": False,
            "topic_detected": "", "intent": intent, "key_points_covered": 0, "missing_key_point": ""}


ACTION_RULES = {
    "diagnostic_question": [3, 7], "advance_next": [7, 9], "reveal_and_next": [6, 7, 10],
    "hint": [6], "guided_question": [5, 6], "diagnose_misconception": [4],
    "full_explanation": [1, 8], "practice": [1], "review": [1, 10], "wrap_up_check": [10],
    "wrap_up_summary": [10], "closing_ack": [10], "pause_ack": [10], "progress_report": [1], "review_done": [1], "review_reveal": [1, 10], "offer_direction_choice": [1],
    "next_unit_choice": [1], "goal_clarification": [1], "offer_learner_choice": [9]
}


ASK_COUNT_ACTIONS = {"diagnostic_question", "guided_question", "hint", "diagnose_misconception",
                     "advance_next", "reveal_and_next"}


TASK_ACTIONS = ASK_COUNT_ACTIONS | {"wrap_up_check", "practice", "review", "full_explanation"}


NON_EVIDENCE_INTENTS = {"explain", "practice", "skip_check", "finish_unit", "review",
                        "next_unit", "process_complaint", "change_goal", "pause_session", "progress_query"}


def _rule_check(response_text, action, old_state, new_state, record):
    """규칙 2·9를 코드로 검증 가능한 값으로 기록 (규칙 문서 5절)."""
    rank = {"Unconfirmed": 0, "State1": 1, "State2": 2, "State3": 3}
    limit = _limit_for(action, record)
    chars = len(response_text)
    q = _count_questions(response_text)
    step = rank.get(new_state, 0) - rank.get(old_state, 0)
    return {"chars": chars, "char_limit": limit, "chars_ok": chars <= int(limit * 1.15),
            "questions": q, "questions_ok": q <= (5 if action == "practice" else MAX_QUESTIONS), "tone_ok": not _formal_tone_found(response_text),
            "state_step": step, "state_step_ok": abs(step) <= 1 or old_state == "Unconfirmed"}



# ---------------------------
# Web v1: 보조 규칙 2 — 학습 단위를 넘어서는 취약 개념 재확인 (Interim Demo 2, 2-4절)
# ---------------------------
PRIOR_VULNERABILITY_RULE = """
Auxiliary rule 2 (re-check vulnerable concepts): CONTEXT.prior_misconceptions_from_other_units lists misconceptions the learner showed in EARLIER learning units (with how often they reappeared).
- If one of them is a prerequisite that the first sub-concept clearly depends on, make your single diagnostic question check THAT prerequisite in a NEW situation the learner has not seen (a concrete comparison or small case), and ask for the reason.
- Do not state the earlier misconception, do not say the learner was wrong before, and do not reveal the answer.
- If none of them is clearly related to the first sub-concept, ignore the list and ask the normal diagnostic question.
"""


def _cross_unit_vulnerabilities(current_cid=None, limit=5):
    """다른 학습 단위(concept_records)에서 기록된 오개념을 최근 순으로 모은다. 극복한 개념(State3 + 재확인)은 제외."""
    out = []
    for cid, rec in concept_records.items():
        if cid == current_cid:
            continue
        for sid, sk in rec.get("skill_records", {}).items():
            mis = sk.get("misconceptions") or []
            if not mis:
                continue
            if sk.get("state") == "State3" and sk.get("rechecked"):
                continue
            out.append({"unit": cid, "skill": sk.get("label", sid), "times": len(mis),
                        "vulnerability": "high" if len(mis) >= 2 else "moderate",
                        "latest_note": str(mis[-1].get("note", ""))[:200]})
    out.sort(key=lambda x: (-x["times"]))
    return out[:limit]



# ---------------------------
# Unit wrap-up, persistence, and controls
# ---------------------------
def show_progress(raw=False):
    """학습 진행 상황. 기본은 보기 쉬운 패널, raw=True 는 개발자용 JSON."""
    record = _record()
    if not raw:
        display(HTML(_progress_panel_html(record)))
        return
    p = progress_summary(record)
    print(json.dumps({
        "topic": learning_context.get("topic", ""),
        "goal": learning_context.get("goal", ""),
        "concept_id": learning_context.get("concept_id", ""),
        "skills": p["skills"],
        "active_skill_id": record.get("active_skill_id"),
        "skill_records": {sid: record.get("skill_records", {}).get(sid, {})
                          for sid in record.get("skill_registry", {})},
        "active_task": record.get("active_task"),
        "wrap_up_queue": record.get("wrap_up_queue"),
        "vulnerability": p["vulnerability"],
        "evidence_count": sum(len(sk.get("evidence", [])) for sk in record.get("skill_records", {}).values()),
        "misconception_count": sum(len(sk.get("misconceptions", [])) for sk in record.get("skill_records", {}).values())
    }, ensure_ascii=False, indent=2))


def finish_unit():
    """학습 단위를 마무리한다: 남은 개념은 '건너뜀'으로 닫고 미확인 항목만 최대 3문제로 확인한다."""
    study_turn("학습 단위를 마무리하고 아직 확인되지 않은 부분을 점검해 줘.", forced_intent="finish_unit")


def export_records(filename=SAVE_FILE, quiet=False):
    payload = {
        "version": 3.13,
        "saved_at": datetime.now().isoformat(timespec="seconds"),
        "learning_context": learning_context,
        "concept_records": concept_records,
        "logs": logs,
        # 세션이 끊겨도 같은 단계에서 이어 갈 수 있도록 대화 단계도 함께 저장한다.
        "session": {
            "learning_phase": learning_phase,
            "awaiting_registry_confirmation": awaiting_registry_confirmation,
            "pending_new_unit": pending_new_unit,
            "pending_study_strategy": pending_study_strategy,
            "pending_start_requests": list(pending_start_requests),
            "messages": list(messages)[-12:]
        }
    }
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    if not quiet:
        print("저장 완료:", filename)


def _autosave():
    """매 턴 조용히 저장한다. 실패해도 학습 흐름을 막지 않는다."""
    try:
        export_records(quiet=True)
    except Exception as exc:
        _dbg(f"[autosave 실패] {exc!r}")


def load_records(filename=SAVE_FILE):
    global learning_context, concept_records, logs
    global learning_phase, awaiting_registry_confirmation, pending_new_unit, pending_study_strategy
    if not os.path.exists(filename):
        print("저장 파일을 찾을 수 없어요:", filename)
        return
    with open(filename, "r", encoding="utf-8") as f:
        payload = json.load(f)
    learning_context = payload.get("learning_context", {"topic": "", "goal": "", "concept_id": ""})
    concept_records = payload.get("concept_records", {})
    logs = payload.get("logs", [])
    learning_context.setdefault("concept_id", "general")
    concept_records.setdefault(learning_context["concept_id"], _new_record())
    for rec in concept_records.values():
        rec.setdefault("latest_dimensions", {"concept": "unknown", "reasoning": "unknown", "transfer": "unknown"})
        rec.setdefault("skill_registry", {})
        rec.setdefault("registry_locked", False)
        rec.setdefault("skill_records", {})
        if not rec.get("skill_registry"):
            # v3.6 used model-generated IDs; archive them rather than pretending they are a valid registry.
            rec["legacy_skill_records"] = rec.get("skill_records", {})
            rec["skill_records"] = {}
        rec.setdefault("active_skill_id", None)
        rec.setdefault("active_task", None)
        rec.setdefault("awaiting_learner_choice", False)
        for _k, _v in (("wrap_up_queue", []), ("wrap_target", None), ("review_offered", False),
                       ("last_help_sid", None), ("last_help_turn", 0), ("transition", None), ("current_strategy", None)):
            rec.setdefault(_k, _v)
        # Migrate v3.5 skill records with missing per-skill misconception lists.
        for skill in rec.get("skill_records", {}).values():
            _ensure_skill_fields(skill)
            skill.setdefault("state_override", None)
            skill.setdefault("help_level", 0)
            skill.setdefault("same_strategy_stuck_count", 0)
            skill.setdefault("last_strategy", None)
            skill.setdefault("latest_dimensions", {"concept": "unknown", "reasoning": "unknown", "transfer": "unknown"})
            skill.setdefault("dimensions", {"concept": "unknown", "reasoning": "unknown", "transfer": "unknown"})
        rec.setdefault("dimensions", {"concept": "unknown", "reasoning": "unknown", "transfer": "unknown"})
    sess = payload.get("session") or {}
    learning_phase = sess.get("learning_phase", "learning" if learning_context.get("topic") else "idle")
    awaiting_registry_confirmation = bool(sess.get("awaiting_registry_confirmation", False))
    pending_new_unit = bool(sess.get("pending_new_unit", False))
    pending_study_strategy = sess.get("pending_study_strategy")
    pending_start_requests[:] = sess.get("pending_start_requests", [])
    messages[:] = sess.get("messages", [])
    print("학습 기록을 불러왔어요. 이어서 입력해 주세요.")
    show_progress()


def reset_conversation():
    """Clear dialogue context and pending interaction; preserve learning records and logs."""
    global pending_post_explanation_check, pending_study_strategy, learning_phase
    messages.clear()
    pending_post_explanation_check = False
    pending_study_strategy = None
    pending_start_requests.clear()
    if learning_phase == "awaiting_strategy_followup":
        learning_phase = "awaiting_topic"
    print("현재 대화 문맥만 초기화했어요. State와 학습 기록은 유지돼요.")


def reset_all_records(confirm=False):
    global concept_records, logs
    if not confirm:
        print("전체 기록 삭제를 확인하려면 reset_all_records(confirm=True)를 실행하세요.")
        return
    concept_records = {learning_context.get("concept_id") or "general": _new_record()}
    logs = []
    messages.clear()
    print("전체 학습 기록과 로그를 초기화했습니다.")


def set_next_concept(topic, goal):
    """Switch concept while retaining previous concept's record."""
    set_learning_context(topic, goal, _safe_id(topic))


def audit_logs():
    """규칙 문서 5절: 대화 로그로 규칙 준수 여부를 코드로 검사한다."""
    bad = [(l["turn_id"], l["next_action"], l["rule_check"]) for l in logs
           if l.get("rule_check") and not (l["rule_check"]["chars_ok"] and l["rule_check"]["questions_ok"]
                                           and l["rule_check"]["state_step_ok"]
                                           and l["rule_check"].get("tone_ok", True))]
    print(f"검사한 턴: {len(logs)} / 규칙 위반 의심: {len(bad)}")
    for item in bad:
        print(" -", item)
    return bad


COMMAND_HELP = [
    ("/progress", "하위 개념별 학습 진행 상황(이해 상태와 개념·이유·적용 확인 여부)을 표로 보여 줘요."),
    ("/finish", "지금 단계를 마무리하고, 아직 확인되지 않은 부분을 점검한 뒤 요약해 줘요."),
    ("/new-topic", "새 학습 주제를 시작해요. 이전 학습 기록은 그대로 보존돼요."),
    ("/reset-chat", "지금까지의 대화 문맥만 비워요. 이해 상태와 학습 기록은 그대로 유지돼요."),
    ("/export", "학습 기록을 파일로 저장해요. (대화할 때마다 자동 저장도 돼요.)"),
    ("/load", "저장해 둔 학습 기록을 불러와 이어서 공부해요."),
    ("/debug", "개발자용 로그(상태 판정, 다음 행동, 규칙 검사)를 켜거나 꺼요."),
    ("/audit", "지금까지의 대화가 규칙(글자 수, 질문 수, 상태 이동, 말투)을 지켰는지 검사해요."),
    ("/exit", "학습 기록을 저장하고 종료해요."),
]


def print_help():
    print("사용할 수 있는 명령어예요.")
    width = max(len(c) for c, _ in COMMAND_HELP)
    for cmd_name, desc in COMMAND_HELP:
        print(f"  {cmd_name.ljust(width)}  {desc}")
    print("명령어가 아닌 문장은 그대로 학습 대화로 이어져요.")


def run_chat():
    global SHOW_CONTROLLER_DEBUG, learning_phase, awaiting_registry_confirmation, pending_study_strategy
    print("STUDY LLM 시작. 공부하고 싶은 내용을 편하게 입력해 주세요.")
    while True:
        user_input = input("\nYou: ").strip()
        cmd = user_input.lower()
        if cmd == "/exit":
            export_records()
            print("종료합니다.")
            break
        elif cmd == "/new-topic":
            pending_study_strategy = None
            pending_start_requests.clear()
            learning_context.update({"topic": "", "goal": "", "concept_id": ""})
            messages.clear()
            learning_phase = "awaiting_topic"
            awaiting_registry_confirmation = False
            print("새 학습 주제를 입력해 주세요. 이전 학습 기록은 보존돼요.")
        elif cmd == "/progress":
            show_progress()
        elif cmd == "/debug":
            SHOW_CONTROLLER_DEBUG = not SHOW_CONTROLLER_DEBUG
            print("개발자 로그:", "켜짐" if SHOW_CONTROLLER_DEBUG else "꺼짐")
        elif cmd == "/audit":
            audit_logs()
        elif cmd == "/finish":
            finish_unit()
        elif cmd == "/export":
            export_records()
        elif cmd == "/load":
            load_records()
        elif cmd == "/reset-chat":
            reset_conversation()
        elif cmd == "/help":
            print_help()
        elif user_input.startswith("/"):
            print("알 수 없는 명령이에요. /help로 명령어 목록을 볼 수 있어요.")
        elif user_input:
            study_turn(user_input)
            _autosave()
