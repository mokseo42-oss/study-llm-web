# STUDY — 학습의 주체로 남도록 돕는 학습 LLM (웹 버전)

SLA482 Technoscience and the Public · Section 1 · Team 8

Colab 노트북 `STUDY_LLM v3.13`의 컨트롤러를 그대로 옮겨 Vercel에 배포할 수 있게 만든 웹 앱입니다.
상태 판정·행동 선택·프롬프트 등 컨트롤러 로직은 노트북과 같고, 노트북의 회귀 테스트(셀 5~8) 전체가 웹용 코어에서도 통과합니다.

## 무엇이 추가됐나 (Interim Demo 2 · MVP 계획서 기준)

| 탭 / 기능 | 문서 근거 | 내용 |
|---|---|---|
| **학습** + 연구자 모드 | 2-3 기록 형식 “응답마다 [적용 규칙 / State / 판단 근거]” | 응답마다 적용 규칙, State 전환, C·R·T 판정과 출처(스스로 설명/힌트 후/AI 말 따라함), 판단 근거, 상태 변경 조건, 규칙 검사 결과를 카드로 표시 |
| 학습 진행 패널 | 2-2 ② State, ① C·R·T | 하위 개념별 State와 C·R·T(확인/부분/보완/미확인) |
| **취약 개념 노트** + 보조 규칙 2 | 2-4 보조 규칙 2, 3-2 “며칠 뒤, 등전위선” | 다른 학습 단위에서 기록된 오개념을 모아 보여 주고, 새 단위의 첫 진단 질문에서 관련 선행 개념을 **다른 상황으로** 다시 확인 (코어에 추가된 유일한 컨트롤러 변경) |
| **Baseline 비교** | 3절 Baseline vs. Controlled, 5-2 개발 계획 4 | 같은 모델·같은 입력을 컨트롤러 없는 일반 LLM과 나란히 실행, 핵심 턴 표시, 보고서용 Markdown 비교표 내보내기 |
| **시나리오 실험실** | 5-2 검증 항목 ①~④, 4절 모호한 사례 | 문서 속 시나리오(전기장·전위, 등전위선, 효소, 뉴턴 3법칙, 계산 실수)를 N회 반복 실행해 State 일관성·행동 일관성·근거 있는 상태 변경·질문 과다 여부를 계산, CSV/JSON 내보내기 |
| **기록 · 피드백** | 5-3 사용자 피드백(작성 예정) | 원칙(P1·P2·P3, 보조 규칙 1, 검증 ④)에 맞춘 설문, 응답별 👍/👎/메모, 여러 테스터 파일 합치기, 보고서 5-3 초안 자동 작성 |
| 학습 기록 | 노트북 `export_records` / `load_records` | 브라우저 자동 저장, 노트북과 같은 형식으로 내보내기/불러오기 (노트북 ↔ 웹 왕복 가능), 대화 로그 CSV, 규칙 검사 요약 |

노트북 명령어(`/progress`, `/finish`, `/new-topic`, `/reset-chat`, `/export`, `/debug`, `/audit`, `/help`)도 입력창에서 그대로 쓸 수 있습니다.

## 구조

```
app.py               FastAPI 진입점 (Vercel Python 런타임이 자동 인식)
study_core.py        노트북 셀 0~4를 옮긴 컨트롤러 (scripts/make_core.py 로 생성)
web/runtime.py       요청마다 새 네임스페이스에서 한 턴을 실행하고 상태를 직렬화
web/fake_llm.py      API 없이 돌려 보는 오프라인 데모 모델 (STUDY_FAKE_LLM=1)
public/              프런트엔드 (HTML/CSS/JS, 빌드 단계 없음)
tests/               노트북 회귀 테스트 실행기
notebook/            원본 노트북
```

서버는 아무것도 저장하지 않습니다. 학습 상태는 브라우저(localStorage)에 있고, 매 턴 서버로 보내져 처리된 뒤 돌아옵니다. 그래서 여러 사용자가 동시에 써도 서로 섞이지 않습니다.

## Vercel 배포

1. 이 저장소를 GitHub에 올립니다.
2. [vercel.com/new](https://vercel.com/new) → 저장소 Import → Framework Preset은 자동(FastAPI/Other) 그대로 → Deploy.
3. Project → Settings → Environment Variables 에 추가 후 Redeploy:

| 이름 | 필수 | 설명 |
|---|---|---|
| `OPENAI_API_KEY` | 예* | 서버에서 쓸 OpenAI 키 (*사용자가 설정 화면에서 본인 키를 넣게 할 거면 생략 가능) |
| `OPENAI_MODEL` | 아니요 | 기본 `gpt-5.5` (노트북과 동일) |
| `ACCESS_CODE` | 권장 | 설정하면 이 코드를 입력한 사람만 API를 호출할 수 있어요 (키 남용 방지) |
| `STUDY_FAKE_LLM` | 아니요 | `1`이면 가짜 모델로 동작 (발표 리허설·UI 확인용, 비용 0) |

한 턴에 모델 호출이 3~5번 일어나서 10~40초 정도 걸립니다. 함수 최대 실행 시간은 `vercel.json`에서 300초로 잡혀 있습니다.

## 로컬 실행

```bash
pip install -r requirements.txt uvicorn
OPENAI_API_KEY=sk-... uvicorn app:app --reload        # 실제 모델
STUDY_FAKE_LLM=1 uvicorn app:app --reload             # 오프라인 데모
python tests/run_notebook_tests.py                    # 노트북 회귀 테스트 (API 호출 없음)
```

## 노트북을 고친 뒤 코어 갱신하기

노트북을 수정했다면 `notebook/`의 파일을 바꾸고 다시 생성하세요.

```bash
python scripts/make_core.py notebook/STUDY_LLM_v3_13.ipynb study_core.py tests/notebook_cells_5_8.py
python tests/run_notebook_tests.py
```

`make_core.py`는 Colab 전용 코드(`google.colab`, `IPython.display`, `!pip`)만 바꾸고 보조 규칙 2 훅을 끼워 넣습니다. 바꿀 위치를 찾지 못하면 멈추므로, 노트북 구조가 크게 바뀌면 스크립트의 치환 문자열도 같이 고쳐 주세요.
