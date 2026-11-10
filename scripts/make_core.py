"""Builds study_core.py from the notebook (cells 0-4) with web-safe patches."""
import json, sys
nb = json.load(open(sys.argv[1]))
cells = [''.join(c['source']) for c in nb['cells']]

def rep(src, old, new, count=1):
    assert src.count(old) == count, (old[:80], src.count(old))
    return src.replace(old, new)

c0 = cells[0]
c0 = rep(c0, "# Colab setup\n!pip install -q openai\n", "")
c0 = rep(c0, "from google.colab import userdata\nfrom IPython.display import display, Markdown, HTML\n", "")
c0 = rep(c0, 'client = OpenAI(api_key=userdata.get("OPENAI_API_KEY"))\nMODEL = "gpt-5.5"  # 계정에서 사용 가능한 모델명으로 변경 가능\n',
'''# 웹 버전: client 는 요청마다 web/runtime.py 가 주입한다 (서버 환경변수 OPENAI_API_KEY 또는 사용자 키).
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
''')

c3 = cells[3]
# 보조 규칙 2 (취약 개념 재확인): 다른 학습 단위에서 기록된 오개념을 첫 진단 질문에 반영한다.
c3 = rep(c3, '''        q = client.responses.create(model=MODEL, instructions=START_CONFIRM_PROMPT,
            input=json.dumps({"topic": learning_context["topic"], "goal": learning_context["goal"],
                              "first_skill": label, "instruction": "Ask one diagnostic question only. Output polite Korean (해요체)."}, ensure_ascii=False))''',
'''        prior_vulnerable = _cross_unit_vulnerabilities(learning_context.get("concept_id"))
        confirm_input = {"topic": learning_context["topic"], "goal": learning_context["goal"],
                         "first_skill": label, "instruction": "Ask one diagnostic question only. Output polite Korean (해요체)."}
        confirm_instructions = START_CONFIRM_PROMPT
        if prior_vulnerable:
            confirm_input["prior_misconceptions_from_other_units"] = prior_vulnerable
            confirm_instructions = START_CONFIRM_PROMPT + PRIOR_VULNERABILITY_RULE
            _trace_event({"type": "aux_rule_2", "turn_after": len(logs), "first_skill": label,
                          "prior_misconceptions": prior_vulnerable})
        q = client.responses.create(model=MODEL, instructions=confirm_instructions,
            input=json.dumps(confirm_input, ensure_ascii=False))''')

c3 += '''


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
'''

core = "\n\n\n".join([
    '"""STUDY LLM controller core — notebook v3.13 port for the web.\n\nGenerated from STUDY_LLM_modified.ipynb (cells 0-4) by scripts/make_core.py.\nController logic, prompts and state rules are unchanged; only Colab/IPython I/O was replaced\nand auxiliary rule 2 (cross-unit vulnerability re-check) was added.\n"""',
    c0, cells[1], cells[2], c3, cells[4]])
open(sys.argv[2], "w").write(core)

# notebook regression tests (cells 5-8) as one script that runs after the core
tests = "\n\n".join(cells[5:9])
open(sys.argv[3], "w").write(tests)
print("ok", len(core.splitlines()), "lines core;", len(tests.splitlines()), "lines tests")
