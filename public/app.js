/* STUDY LLM web client — keeps all learner data in this browser and sends the controller
   state to the server with each turn (the server stores nothing). */
(() => {
  "use strict";

  // ------------------------------------------------------------------ constants
  const LS_KEY = "study.web.v1";
  const STATE_LABEL = { Unconfirmed: "확인 전", State1: "State 1 · 기초 이해 부족", State2: "State 2 · 부분적 이해", State3: "State 3 · 안정적 이해" };
  const STATE_SHORT = { Unconfirmed: "확인 전", State1: "S1", State2: "S2", State3: "S3" };
  const ACTION_LABEL = {
    diagnostic_question: "진단 질문", diagnose_misconception: "오개념 확인 질문", guided_question: "유도 질문(이유 확인)",
    hint: "힌트 한 단계", partial_explanation: "부분 설명", prerequisite_explanation: "선행 개념으로 돌아가기",
    full_explanation: "설명 + 확인 질문", reveal_and_next: "답 안내 후 다음 개념", advance_next: "다음 개념으로",
    practice: "연습 문제", review: "복습 질문", review_done: "복습 완료", review_reveal: "복습 답 안내",
    wrap_up_check: "마무리 확인 질문", wrap_up_summary: "마무리 요약", closing_ack: "마무리 인사", pause_ack: "잠시 멈춤",
    progress_report: "진행 상황 안내", offer_direction_choice: "방향 선택 제안", next_unit_choice: "다음 단원 선택",
    goal_clarification: "목적지 확인", offer_learner_choice: "학습자 선택 제안"
  };
  const DIM_LABEL = { concept: "C", reasoning: "R", transfer: "T" };
  const DIM_KO = { confirmed: "확인", partial: "부분", missing: "보완", unknown: "미확인" };
  const SOURCE_KO = { independent_explanation: "스스로 설명", independent_transfer: "스스로 적용", hint_assisted: "힌트 후",
    ai_echo: "AI 말 따라함", answer_only: "답만", unknown: "-" };
  const AUX1 = new Set(["goal_clarification", "offer_direction_choice", "next_unit_choice", "offer_learner_choice"]);

  const SCENARIOS = [
    { id: "field", title: "전기장과 전위 (Demo 2 · 3-1 첫 번째 대화)",
      desc: "오개념 확인 → 이유 → 적용 순서로 근거를 쌓는지, 고쳤던 오개념이 다시 나올 때 한 단계씩 내리는지 확인해요.",
      lines: ["전기장이랑 전위가 어떻게 다른지 잘 모르겠어.", "좋아요, 그대로 진행해 주세요.",
        "꼭 그런 건 아닌 것 같아. 그런데 정확히 왜 다른지는 잘 모르겠어.", "A는 변화가 없으니까 0이고, B는 변하니까 B가 더 커.",
        "높은 쪽에서 낮은 쪽이니까 왼쪽에서 오른쪽이고, 약 10 V/m야.", "근데 전위가 100 V인 지점은 10 V인 지점보다 전기장이 반드시 크지 않아?"] },
    { id: "equipotential", title: "등전위선, 며칠 뒤 (Demo 2 · 3-2 두 번째 대화)",
      desc: "‘현재 학습 기록 이어받기’를 켜고 실행하세요. 첫 대화에서 기록된 취약 개념을 첫 진단 질문에서 다른 상황으로 다시 확인하는지(보조 규칙 2) 봐요.",
      carry: true,
      lines: ["등전위선이 잘 이해가 안 돼.", "좋아요. 내일 퀴즈에 그림 보고 전기장 센 곳 고르는 게 나와요.",
        "50 V 쪽…? 지난번에 값이 아니라고 했던 것 같은데 이유는 모르겠어.", "안 밀려나지. 그럼 거긴 0이고, 옆과 차이가 있는 5 V 쪽이 커.",
        "선이 촘촘하니까… 세다?", "짧은 거리에서 전위가 많이 바뀐다는 거구나. 옆이랑 차이가 클수록 세게 밀리니까 세. 숫자가 크다고 센 게 아니고."] },
    { id: "enzyme", title: "효소와 활성화 에너지 (MVP 계획서 · 3절)",
      desc: "오답(열을 공급한다)에 곧바로 정답을 주지 않고 비교 질문이나 선행 개념 질문을 거치는지, 첫 턴을 Unconfirmed로 두는지 확인해요.",
      lines: ["효소가 활성화 에너지를 낮추는 원리를 잘 모르겠어.", "네, 이 구성으로 진행해 주세요.",
        "효소가 반응 과정에서 열을 공급해서 반응 속도를 빠르게 하는 거 아니야?", "반응물에 효소가 결합해서 활성화 에너지를 낮추는 건가?",
        "반응물들을 알맞은 방향으로 가까이 붙잡아 주니까 서로 부딪쳐 반응하기 쉬워지고, 그래서 필요한 에너지가 줄어드는 거야."] },
    { id: "newton", title: "모호 사례 1 · 정답이지만 근거가 하나뿐 (Demo 2 · 4-3)",
      desc: "정의만 맞힌 답으로 State 3을 확정하지 않고 Reasoning 질문을 하나 더 하는지 확인해요.",
      lines: ["뉴턴 제3법칙 공부하고 싶어.", "좋아요.",
        "뉴턴 제3법칙은 두 물체가 서로 같은 크기의 힘을 반대 방향으로 주고받는 거잖아요. 그럼 다음 단원 넘어가도 되죠?",
        "질량이 달라도 힘은 상호작용 한 쌍이라 크기가 같아요. 대신 질량이 작은 쪽 가속도가 더 커요."] },
    { id: "calc", title: "모호 사례 2 · 개념 오류인지 계산 실수인지 (Demo 2 · 4-3)",
      desc: "방법은 맞고 값만 틀린 답에서 State를 내리지 않고 과정을 묻는지 확인해요.",
      lines: ["전위차로 전기장 세기 구하는 거 연습하고 싶어.", "좋아요, 진행해 주세요.",
        "전기장은 거리에 따라 전위가 얼마나 변하는지로 정해져요. 그래서 전위 차이를 거리로 나눠요.",
        "20을 2로 나누면… 5 V/m?", "아 20 나누기 2라서 10 V/m예요. 전위 차이를 거리로 나눈 거예요."] },
    { id: "custom", title: "직접 입력", desc: "한 줄에 학습자 발화 하나씩 적어 주세요. 두 번째 줄은 보통 하위 개념 구성 확인(예: 좋아요)이에요.", lines: [] }
  ];

  const SURVEY = [
    { id: "q1", text: "AI가 설명하기 전에 내 생각을 먼저 물어봤다.", tag: "P1 이해 상태 진단" },
    { id: "q2", text: "AI의 질문과 설명 수준이 내 실제 이해 상태에 맞았다.", tag: "State 판정" },
    { id: "q3", text: "정답을 듣기보다 내가 직접 설명하고 고치게 되었다.", tag: "P2 직접 설명·검증" },
    { id: "q4", text: "이해가 안 될 때 같은 설명을 반복하지 않고 방식(예시·비유·작은 단계)을 바꿨다.", tag: "P3 설명 전략 변경" },
    { id: "q5", text: "질문이 너무 많거나 진행이 답답하지 않았다.", tag: "검증 ④ 과도한 질문" },
    { id: "q6", text: "무엇을 공부할지(목적지)를 내가 정할 수 있었다.", tag: "보조 규칙 1" }
  ];

  // ------------------------------------------------------------------ storage
  const defaults = () => ({
    settings: { accessCode: "", apiKey: "", model: "", research: false },
    learn: { state: null, chat: [], progress: null, units: [] },
    compare: { state: null, history: [], turns: [] },
    feedback: { ratings: [], surveys: [] },
    lab: { last: null }
  });
  let store = defaults();
  try {
    const raw = localStorage.getItem(LS_KEY);
    if (raw) store = Object.assign(defaults(), JSON.parse(raw));
  } catch (e) { /* storage unavailable: run in memory */ }
  let saveTimer = null;
  function save() {
    clearTimeout(saveTimer);
    saveTimer = setTimeout(() => {
      try { localStorage.setItem(LS_KEY, JSON.stringify(store)); }
      catch (e) { toast("브라우저 저장 공간이 부족해요. 기록을 내보낸 뒤 초기화해 주세요."); }
    }, 150);
  }

  // ------------------------------------------------------------------ helpers
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => Array.from(el.querySelectorAll(s));
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const uid = () => Math.random().toString(36).slice(2, 10) + Date.now().toString(36).slice(-4);
  const nowIso = () => new Date().toISOString();
  const clone = (o) => (o == null ? o : JSON.parse(JSON.stringify(o)));
  function md(text) {
    try {
      if (window.marked && window.DOMPurify) return DOMPurify.sanitize(marked.parse(String(text), { breaks: true }));
    } catch (e) { /* fall through */ }
    return esc(text).replace(/\n/g, "<br>");
  }
  function toast(msg, ms = 2600) {
    const t = $("#toast"); t.textContent = msg; t.classList.add("show");
    clearTimeout(t._h); t._h = setTimeout(() => t.classList.remove("show"), ms);
  }
  function download(name, text, type = "application/json") {
    const blob = new Blob([text], { type: type + ";charset=utf-8" });
    const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = name;
    document.body.appendChild(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(a.href), 2000);
  }
  function csv(rows) {
    const cell = (v) => { const s = v == null ? "" : String(v); return /[",\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s; };
    return "﻿" + rows.map((r) => r.map(cell).join(",")).join("\n");
  }
  const stamp = () => new Date().toISOString().slice(0, 16).replace(/[-:T]/g, "");
  function statePill(state) { const s = state || "Unconfirmed"; return `<span class="state-pill st-${esc(s)}">${esc(STATE_LABEL[s] || s)}</span>`; }
  function dimMini(dim, status, src) {
    const st = status || "unknown";
    const title = `${dim}: ${DIM_KO[st] || st}${src && src !== "unknown" ? " (" + (SOURCE_KO[src] || src) + ")" : ""}`;
    return `<span class="mini d-${esc(st)}" title="${esc(title)}">${esc(DIM_LABEL[dim] || dim)}</span>`;
  }

  // ------------------------------------------------------------------ API
  let health = null;
  async function api(path, body) {
    const headers = { "Content-Type": "application/json" };
    if (store.settings.accessCode) headers["X-Access-Code"] = store.settings.accessCode;
    if (store.settings.apiKey) headers["X-OpenAI-Key"] = store.settings.apiKey;
    const res = await fetch(path, { method: "POST", headers, body: JSON.stringify(body) });
    let data = null;
    try { data = await res.json(); } catch (e) { /* non-JSON */ }
    if (!res.ok) {
      const msg = (data && data.detail) || `요청 실패 (${res.status})`;
      const err = new Error(typeof msg === "string" ? msg : JSON.stringify(msg)); err.status = res.status; throw err;
    }
    return data;
  }
  const turnBody = (command, text, state) => ({ command, text, state, model: store.settings.model || null });

  async function checkHealth() {
    try {
      health = await (await fetch("/api/health")).json();
    } catch (e) { health = null; }
    const banner = $("#banner");
    let msg = "";
    if (!health) msg = "서버에 연결하지 못했어요. 잠시 뒤 새로고침해 주세요.";
    else if (health.fake_llm) msg = "오프라인 데모 모드예요. 실제 모델 대신 정해진 가짜 응답을 써요 (STUDY_FAKE_LLM=1).";
    else if (!health.has_server_key && !store.settings.apiKey) msg = "서버에 OpenAI API 키가 설정되지 않았어요. ⚙ 설정에서 본인 키를 입력하면 바로 쓸 수 있어요.";
    banner.textContent = msg; banner.classList.toggle("hidden", !msg);
    if (health) $("#serverInfo").textContent = `서버 기본 모델: ${health.model} · 서버 키 ${health.has_server_key ? "있음" : "없음"}${health.access_code_required ? " · 접근 코드 필요" : ""}`;
    if (health && health.access_code_required && !store.settings.accessCode) openSettings();
  }

  // ------------------------------------------------------------------ tabs & research mode
  $$(".tab").forEach((b) => b.addEventListener("click", () => switchTab(b.dataset.tab)));
  function switchTab(id) {
    $$(".tab").forEach((b) => b.classList.toggle("active", b.dataset.tab === id));
    $$(".panel").forEach((p) => p.classList.toggle("active", p.id === "tab-" + id));
    if (id === "records") renderRecords();
  }
  const researchToggle = $("#researcherToggle");
  function applyResearch() { document.body.classList.toggle("research", !!store.settings.research); researchToggle.checked = !!store.settings.research; }
  researchToggle.addEventListener("change", () => { store.settings.research = researchToggle.checked; applyResearch(); save(); });

  // ------------------------------------------------------------------ settings
  const settingsDialog = $("#settingsDialog");
  function openSettings() {
    $("#setAccess").value = store.settings.accessCode || "";
    $("#setKey").value = store.settings.apiKey || "";
    $("#setModel").value = store.settings.model || "";
    if (!settingsDialog.open) settingsDialog.showModal();
  }
  $("#settingsBtn").addEventListener("click", openSettings);
  settingsDialog.addEventListener("close", () => {
    if (settingsDialog.returnValue !== "save") return;
    store.settings.accessCode = $("#setAccess").value.trim();
    store.settings.apiKey = $("#setKey").value.trim();
    store.settings.model = $("#setModel").value.trim();
    save(); checkHealth(); toast("설정을 저장했어요.");
  });

  // ------------------------------------------------------------------ chat rendering (shared)
  function traceHtml(entry) {
    const log = entry.log, events = entry.events || [];
    let h = "";
    for (const ev of events) {
      if (ev.type === "aux_rule_2") {
        const items = (ev.prior_misconceptions || []).map((m) => `${esc(m.skill)} (${m.times}회, ${m.vulnerability === "high" ? "취약도 높음" : "보통"})`).join(", ");
        h += `<div class="trace-head"><span class="tag">보조 규칙 2 · 취약 개념 재확인</span></div><div><span class="k">참고한 이전 오개념:</span> ${items}</div>`;
      }
    }
    if (!log) {
      if (!h) h = `<div class="trace-head"><span class="tag">설정 단계</span><span class="k">주제·하위 개념 확인 — 이해 증거로 기록하지 않음</span></div>`;
      return `<div class="trace">${h}</div>`;
    }
    const action = log.next_action;
    let ruleTag = "핵심 규칙";
    if (AUX1.has(action)) ruleTag = "보조 규칙 1 · 목적지 확인";
    else if (log.missing_key_point && (action === "guided_question" || action === "hint")) ruleTag = "보조 규칙 3 · 빠진 요소 하나";
    const rc = log.rule_check || {};
    const flags = [];
    if (rc.chars_ok === false) flags.push(`글자 수 초과(${rc.chars}/${rc.char_limit})`);
    if (rc.questions_ok === false) flags.push(`질문 ${rc.questions}개`);
    if (rc.state_step_ok === false) flags.push("State 2단계 이동");
    if (rc.tone_ok === false) flags.push("말투(합니다체)");
    const changed = log.previous_skill_state !== log.current_skill_state;
    h += `<div class="trace-head"><span class="tag">${esc(ruleTag)}</span>`
      + `<b>${esc(ACTION_LABEL[action] || action)}</b>`
      + `<span class="k">규칙 ${esc((log.applied_rules || []).join("·") || "-")}</span>`
      + `<span>${statePill(log.previous_skill_state)} → ${statePill(log.current_skill_state)}</span>`
      + `<span class="crt">${dimMini("concept", log.concept, log.concept_source)}${dimMini("reasoning", log.reasoning, log.reasoning_source)}${dimMini("transfer", log.transfer, log.transfer_source)}</span>`
      + `</div>`;
    h += `<div><span class="k">판단 근거:</span> ${esc(log.evidence_note || "-")}</div>`;
    if (changed || log.transition_reason) h += `<div><span class="k">상태 변경 조건:</span> ${esc(log.transition_reason || "-")}</div>`;
    if (log.core_misconception) h += `<div><span class="k">오개념:</span> 핵심 오개념 감지</div>`;
    if (log.missing_key_point) h += `<div><span class="k">빠진 핵심 요소:</span> ${esc(log.missing_key_point)}</div>`;
    h += `<div><span class="k">의도:</span> ${esc(log.intent)} · <span class="k">턴</span> ${esc(log.turn_id)}`
      + (flags.length ? ` · <span class="flag-bad">규칙 검사: ${esc(flags.join(", "))}</span>` : ` · <span class="k">규칙 검사 통과</span>`) + `</div>`;
    return `<div class="trace">${h}</div>`;
  }

  function msgHtml(entry, opts = {}) {
    if (entry.role === "user") return `<div class="msg user">${esc(entry.content)}</div>`;
    if (entry.role === "system") return `<div class="msg bot"><div class="bubble system">${esc(entry.content)}</div></div>`;
    const body = entry.kind === "markdown" ? md(entry.content) : esc(entry.content).replace(/\n/g, "<br>");
    let meta = "";
    if (entry.status && entry.status.total) {
      const st = entry.status;
      meta += `<span>${esc(st.where || "")}</span>` + (st.state && st.where && st.where.startsWith("현재 개념") ? statePill(st.state) : "") + `<span>진행 ${st.done}/${st.total}</span>`;
    }
    if (!opts.noFeedback) {
      const r = entry.rating;
      meta += `<span class="fb-btns">`
        + `<button class="fb-btn ${r === 1 ? "on" : ""}" data-fb="1" data-id="${entry.id}" title="도움이 됐어요">👍</button>`
        + `<button class="fb-btn ${r === -1 ? "on" : ""}" data-fb="-1" data-id="${entry.id}" title="아쉬워요">👎</button>`
        + `<button class="fb-btn ${entry.note ? "on" : ""}" data-fb="note" data-id="${entry.id}" title="메모 남기기">✎</button></span>`;
    }
    const trace = opts.noTrace ? "" : traceHtml(entry);
    return `<div class="msg bot" data-id="${entry.id}"><div class="bubble">${body}</div>${meta ? `<div class="msg-meta">${meta}</div>` : ""}${trace}</div>`;
  }

  // Convert a server result into chat entries
  function entriesFromResult(r) {
    const out = [];
    const log = (r.new_logs || [])[0] || null;
    for (const o of r.outputs || []) {
      if (o.kind === "html") continue;  // notebook-only HTML panels are rendered natively
      out.push({ id: uid(), role: "bot", kind: o.kind === "markdown" ? "markdown" : "text", content: o.content, ts: nowIso() });
    }
    if (!out.length) out.push({ id: uid(), role: "system", content: "(응답이 비어 있어요)", ts: nowIso() });
    const mdEntry = out.find((e) => e.kind === "markdown");
    if (log) (mdEntry || out[out.length - 1]).log = log;
    if ((r.events || []).length) out[out.length - 1].events = r.events;
    const p = r.progress || {};
    const active = (p.skills || []).find((s) => s.active);
    out[out.length - 1].status = { where: p.where, done: p.done, total: p.total, state: active ? active.state : null };
    return out;
  }

  // ------------------------------------------------------------------ learn tab
  const chatEl = $("#chat");
  const input = $("#chatInput");
  let busy = false;

  function renderWelcome() {
    chatEl.innerHTML = `<div class="welcome">
      <span class="eyebrow">Study · Learner-led LLM</span>
      <h1>무엇을 <em>공부</em>하고 싶으세요?</h1>
      <p>STUDY는 바로 설명하지 않아요. 먼저 지금 어떻게 이해하고 있는지 듣고, 그 답을 근거로 다음 질문과 설명 방식을 골라요.</p>
      <div class="principles">
        <div class="principle"><span class="num">01</span><b>이해 상태 진단</b>개념·이유·적용(C·R·T)을 따로 확인하고, 근거가 없으면 상태를 정하지 않아요.</div>
        <div class="principle"><span class="num">02</span><b>직접 설명·검증</b>빠진 요소 하나만 짚어 묻고, 대신 완성하지 않아요.</div>
        <div class="principle"><span class="num">03</span><b>대화·학습 조정</b>같은 설명이 안 통하면 예시·비유·작은 단계로 바꿔요.</div>
      </div>
      <div class="starters">
        <button class="chip-btn" data-start="전기장이랑 전위가 어떻게 다른지 잘 모르겠어.">전기장과 전위가 헷갈려요</button>
        <button class="chip-btn" data-start="효소가 활성화 에너지를 낮추는 원리를 잘 모르겠어.">효소와 활성화 에너지</button>
        <button class="chip-btn" data-start="유도 쌍극자가 왜 생기는지 모르겠어요.">유도 쌍극자</button>
        <button class="chip-btn" data-start="뉴턴 제3법칙 공부하고 싶어.">뉴턴 제3법칙</button>
      </div></div>`;
  }
  function renderChat() {
    const c = store.learn.chat;
    if (!c.length) { renderWelcome(); return; }
    chatEl.innerHTML = c.map((e) => msgHtml(e)).join("");
    chatEl.scrollTop = chatEl.scrollHeight;
  }
  function appendTyping(el, label = "응답을 준비하고 있어요 · 평가 → 상태 판정 → 응답 생성 (보통 10~40초)") {
    const d = document.createElement("div");
    d.className = "msg bot typing-row";
    d.innerHTML = `<div class="typing"><span class="dots"><span></span><span></span><span></span></span>${esc(label)}</div>`;
    el.appendChild(d); el.scrollTop = el.scrollHeight; return d;
  }
  chatEl.addEventListener("click", (ev) => {
    const s = ev.target.closest("[data-start]");
    if (s) { send(s.dataset.start); return; }
    handleFeedbackClick(ev, store.learn.chat);
  });

  function setBusy(b) { busy = b; $("#sendBtn").disabled = b; $$(".quick-actions .chip-btn").forEach((x) => (x.disabled = b)); }

  async function runLearnCommand(command, text = "", label = "") {
    if (busy) return;
    setBusy(true);
    if (label) { store.learn.chat.push({ id: uid(), role: "user", content: label, ts: nowIso() }); renderChat(); }
    const typing = appendTyping(chatEl, command === "turn" || command === "finish" ? undefined : "처리 중…");
    try {
      const r = await api("/api/turn", turnBody(command, text, store.learn.state));
      store.learn.state = r.state; store.learn.progress = r.progress; store.learn.units = r.units;
      store.learn.chat.push(...entriesFromResult(r));
      save();
    } catch (e) {
      store.learn.chat.push({ id: uid(), role: "system", content: "⚠ " + e.message, ts: nowIso() });
      if (e.status === 401) openSettings();
    } finally {
      typing.remove(); setBusy(false); renderChat(); renderSide();
    }
  }

  const COMMAND_HELP = [
    ["/progress", "하위 개념별 진행 상황(오른쪽 패널)으로 이동"], ["/finish", "지금 단계를 마무리하고 미확인 부분을 점검"],
    ["/new-topic", "새 학습 주제 시작 (이전 기록 보존)"], ["/reset-chat", "대화 문맥만 비우기 (State·기록 유지)"],
    ["/export", "학습 기록 파일로 내보내기"], ["/debug", "연구자 모드 켜기/끄기"], ["/audit", "규칙 검사 결과 보기"], ["/help", "명령어 목록"]
  ];
  function systemMsg(text) { store.learn.chat.push({ id: uid(), role: "system", content: text, ts: nowIso() }); renderChat(); save(); }

  function send(raw) {
    const text = String(raw || "").trim();
    if (!text || busy) return;
    const cmd = text.toLowerCase();
    if (cmd.startsWith("/")) {
      if (cmd === "/finish") return runLearnCommand("finish", "", "/finish");
      if (cmd === "/new-topic") return runLearnCommand("new_topic", "", "/new-topic");
      if (cmd === "/reset-chat") return runLearnCommand("reset_chat", "", "/reset-chat");
      if (cmd === "/progress") { $("#progressCard").scrollIntoView({ behavior: "smooth" }); $("#progressCard").animate([{ boxShadow: "0 0 0 3px var(--accent-2)" }, { boxShadow: "none" }], 1200); return; }
      if (cmd === "/export") return exportRecords();
      if (cmd === "/debug") { store.settings.research = !store.settings.research; applyResearch(); save(); return toast("연구자 모드 " + (store.settings.research ? "켜짐" : "꺼짐")); }
      if (cmd === "/audit") return switchTab("records");
      if (cmd === "/help") return systemMsg("사용할 수 있는 명령어예요.\n" + COMMAND_HELP.map(([c, d]) => `${c}  ${d}`).join("\n") + "\n명령어가 아닌 문장은 그대로 학습 대화로 이어져요.");
      return systemMsg("알 수 없는 명령이에요. /help로 명령어 목록을 볼 수 있어요.");
    }
    store.learn.chat.push({ id: uid(), role: "user", content: text, ts: nowIso() });
    renderChat();
    runLearnCommand("turn", text);
  }

  $("#chatForm").addEventListener("submit", (e) => { e.preventDefault(); const t = input.value; input.value = ""; autosize(input); send(t); });
  function bindEnter(el, form) {
    el.addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); form.requestSubmit(); } });
    el.addEventListener("input", () => autosize(el));
  }
  function autosize(el) { el.style.height = "auto"; el.style.height = Math.min(el.scrollHeight, 180) + "px"; }
  bindEnter(input, $("#chatForm"));
  $$(".quick-actions [data-cmd]").forEach((b) => b.addEventListener("click", () => {
    const map = { finish: "/finish", new_topic: "/new-topic", reset_chat: "/reset-chat" };
    runLearnCommand(b.dataset.cmd, "", map[b.dataset.cmd]);
  }));
  $("#helpBtn").addEventListener("click", () => send("/help"));

  // logo → back to the start screen. Same as /new-topic on the server (topic and chat context
  // are cleared; learning records and the weak-concept note are kept), then the welcome screen.
  $("#homeBtn").addEventListener("click", async (e) => {
    e.preventDefault();
    switchTab("learn");
    if (busy) { toast("응답을 받는 중이에요. 끝난 뒤 다시 눌러 주세요."); return; }
    if (!store.learn.chat.length) { renderChat(); return; }
    if (!confirm("지금 대화를 끝내고 처음 화면으로 돌아갈까요?\n학습 기록과 취약 개념 노트는 그대로 남아요.")) return;
    if (store.learn.state) {
      setBusy(true);
      try {
        const r = await api("/api/turn", turnBody("new_topic", "", store.learn.state));
        store.learn.state = r.state; store.learn.progress = r.progress; store.learn.units = r.units;
      } catch (err) {
        toast("처음 화면으로 돌아가지 못했어요: " + err.message);
        if (err.status === 401) openSettings();
        return;
      } finally { setBusy(false); }
    }
    store.learn.chat = [];
    save(); renderChat(); renderSide();
    input.value = ""; autosize(input); input.focus();
  });

  // side panel
  function renderSide() {
    const p = store.learn.progress;
    const body = $("#progressBody");
    if (!p || !p.skills || !p.skills.length) {
      body.innerHTML = `<p class="muted">주제를 정하면 하위 개념별 이해 상태가 여기에 표시돼요.</p>`; $("#progressWhere").textContent = "";
    } else {
      $("#progressWhere").textContent = `${p.done}/${p.total}`;
      const closedText = { confirmed: "개념 확인됨", revealed: "답 안내 후 마무리에서 재확인", skipped: "건너뜀 (마무리에서 확인)" };
      body.innerHTML = `<div class="small" style="margin-bottom:8px"><b>${esc(p.topic)}</b><br><span class="muted">${esc(p.goal || "")}</span></div>`
        + p.skills.map((s, i) => {
          let note = s.unvisited ? "아직 시작하지 않음" : (closedText[s.closed] || "");
          if (s.closed === "confirmed" && s.needs_recheck && !s.rechecked) note = "도움을 받고 통과 · 마무리에서 재확인";
          const d = s.dimensions || {};
          return `<div class="skill ${s.active ? "active" : ""}"><div class="skill-top"><span class="skill-name">${i + 1}. ${esc(s.label)}</span>${statePill(s.state)}</div>`
            + `<div class="skill-dims">${dimMini("concept", d.concept)}${dimMini("reasoning", d.reasoning)}${dimMini("transfer", d.transfer)}</div>`
            + (note ? `<div class="skill-note">${esc(note)}</div>` : "") + `</div>`;
        }).join("")
        + `<div class="small muted">현재 단위 취약도: ${esc({ unknown: "아직 평가되지 않음", low: "낮음", moderate: "보통", high: "높음" }[p.vulnerability] || p.vulnerability)}</div>`;
    }
    // vulnerability note across units (보조 규칙 2)
    const items = [];
    for (const u of store.learn.units || []) for (const s of u.skills || []) {
      if ((s.misconceptions || []).length) items.push({ unit: u.concept_id, label: s.label, n: s.misconceptions.length, last: s.misconceptions[s.misconceptions.length - 1], state: s.state });
    }
    $("#vulnBody").innerHTML = items.length
      ? items.map((it) => `<div class="vuln-item"><span class="${it.n >= 2 ? "vh" : "vm"}">${it.n >= 2 ? "취약도 높음" : "보통"}</span> · <b>${esc(it.label)}</b> <span class="muted">(${esc(it.unit)})</span><br><span class="muted small">${esc(it.last)}</span></div>`).join("")
      : `<p class="muted small">고친 오개념이 기록되면 다음 학습 단위의 첫 진단 질문에서 다른 상황으로 다시 확인해요.</p>`;
    $("#sessionAudit").innerHTML = auditHtml((store.learn.state || {}).logs || [], true);
  }

  // ------------------------------------------------------------------ feedback on messages
  let noteTarget = null;
  function handleFeedbackClick(ev, list) {
    const b = ev.target.closest("[data-fb]");
    if (!b) return;
    const entry = list.find((x) => x.id === b.dataset.id);
    if (!entry) return;
    if (b.dataset.fb === "note") {
      noteTarget = entry; $("#noteText").value = entry.note || ""; $("#noteDialog").showModal(); return;
    }
    const v = Number(b.dataset.fb);
    entry.rating = entry.rating === v ? 0 : v;
    syncRating(entry); save(); renderChat(); renderCompare();
  }
  $("#noteDialog").addEventListener("close", () => {
    if ($("#noteDialog").returnValue === "save" && noteTarget) { noteTarget.note = $("#noteText").value.trim(); syncRating(noteTarget); save(); renderChat(); renderCompare(); }
    noteTarget = null;
  });
  function syncRating(entry) {
    const list = store.feedback.ratings;
    const i = list.findIndex((r) => r.msg_id === entry.id);
    const rec = { id: i >= 0 ? list[i].id : uid(), msg_id: entry.id, ts: nowIso(), rating: entry.rating || 0, note: entry.note || "",
      response: entry.content, action: entry.log ? entry.log.next_action : "", state: entry.log ? entry.log.current_skill_state : "",
      topic: (store.learn.progress || {}).topic || "", source: entry.source || "learn" };
    if (!rec.rating && !rec.note) { if (i >= 0) list.splice(i, 1); return; }
    if (i >= 0) list[i] = rec; else list.push(rec);
  }

  // ------------------------------------------------------------------ compare tab
  const chatB = $("#chatBaseline"), chatC = $("#chatControlled"), compareInput = $("#compareInput");
  let compareBusy = false;
  function renderCompare() {
    const turns = store.compare.turns;
    if (!turns.length) {
      const empty = `<p class="muted small">아래에 학습자 발화를 입력하면 두 응답이 여기에 나란히 쌓여요. 예: “등전위선이 잘 이해가 안 돼.”</p>`;
      chatB.innerHTML = empty; chatC.innerHTML = empty; return;
    }
    const keyBtn = (t, i) => `<button class="key-turn-btn ${t.key ? "on" : ""}" data-key="${i}">${t.key ? "◀ 핵심 턴" : "핵심 턴 표시"}</button>`;
    chatB.innerHTML = turns.map((t, i) => `<div class="msg user">${esc(t.user)}</div>`
      + (t.baseline ? msgHtml(t.baseline, { noTrace: true }) : (t.pending ? `<div class="muted small">…</div>` : ""))
      + `<div class="msg-meta">${keyBtn(t, i)}</div>`).join("");
    chatC.innerHTML = turns.map((t, i) => `<div class="msg user">${esc(t.user)}</div>`
      + (t.controlled || []).map((e) => msgHtml(e)).join("") + (t.pending ? `<div class="muted small">…</div>` : "")
      + `<div class="msg-meta">${keyBtn(t, i)}</div>`).join("");
    chatB.scrollTop = chatB.scrollHeight; chatC.scrollTop = chatC.scrollHeight;
  }
  function compareEntries() { return store.compare.turns.flatMap((t) => [t.baseline, ...(t.controlled || [])].filter(Boolean)); }
  [chatB, chatC].forEach((el) => el.addEventListener("click", (ev) => {
    const k = ev.target.closest("[data-key]");
    if (k) { const t = store.compare.turns[Number(k.dataset.key)]; t.key = !t.key; save(); renderCompare(); return; }
    handleFeedbackClick(ev, compareEntries());
  }));
  $("#compareForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    const text = compareInput.value.trim();
    if (!text || compareBusy) return;
    compareInput.value = ""; autosize(compareInput);
    compareBusy = true; $("#compareSend").disabled = true;
    const turn = { user: text, baseline: null, controlled: [], pending: true, key: false };
    store.compare.turns.push(turn); renderCompare();
    const tB = appendTyping(chatB, "Baseline 응답 중…"), tC = appendTyping(chatC, "Controlled 응답 중…");
    const history = clone(store.compare.history);
    const pB = api("/api/baseline", { text, history, model: store.settings.model || null })
      .then((r) => { turn.baseline = { id: uid(), role: "bot", kind: "markdown", content: r.reply, source: "baseline", ts: nowIso() };
        store.compare.history.push({ role: "user", content: text }, { role: "assistant", content: r.reply }); })
      .catch((err) => { turn.baseline = { id: uid(), role: "system", content: "⚠ " + err.message }; })
      .finally(() => tB.remove());
    const pC = api("/api/turn", turnBody("turn", text, store.compare.state))
      .then((r) => { store.compare.state = r.state; turn.controlled = entriesFromResult(r).map((x) => Object.assign(x, { source: "controlled" })); })
      .catch((err) => { turn.controlled = [{ id: uid(), role: "system", content: "⚠ " + err.message }]; })
      .finally(() => tC.remove());
    await Promise.allSettled([pB, pC]);
    turn.pending = false; compareBusy = false; $("#compareSend").disabled = false; save(); renderCompare();
  });
  bindEnter(compareInput, $("#compareForm"));
  $("#compareReset").addEventListener("click", () => {
    if (store.compare.turns.length && !confirm("비교 대화를 지우고 새로 시작할까요?")) return;
    store.compare = { state: null, history: [], turns: [] }; save(); renderCompare();
  });
  $("#compareExport").addEventListener("click", () => {
    const turns = store.compare.turns;
    if (!turns.length) return toast("내보낼 비교 대화가 없어요.");
    const cellText = (s) => String(s || "").replace(/\|/g, "\\|").replace(/\n+/g, " ");
    let doc = `# Baseline vs. Controlled 비교\n\n- 내보낸 시각: ${new Date().toLocaleString("ko-KR")}\n- 모델: ${store.settings.model || (health && health.model) || ""}\n\n`;
    doc += `| 턴 | 학습자 | Baseline | Controlled | Controlled 판정 |\n|---|---|---|---|---|\n`;
    turns.forEach((t, i) => {
      const ctrl = (t.controlled || []).map((e) => e.content).join(" / ");
      const log = (t.controlled || []).map((e) => e.log).find(Boolean);
      const judge = log ? `${ACTION_LABEL[log.next_action] || log.next_action} · ${STATE_SHORT[log.previous_skill_state]}→${STATE_SHORT[log.current_skill_state]} · ${log.evidence_note || ""}` : "설정 단계";
      doc += `| ${i + 1}${t.key ? " ◀ 핵심 턴" : ""} | ${cellText(t.user)} | ${cellText(t.baseline && t.baseline.content)} | ${cellText(ctrl)} | ${cellText(judge)} |\n`;
    });
    download(`study_compare_${stamp()}.md`, doc, "text/markdown");
  });

  // ------------------------------------------------------------------ lab tab
  const sel = $("#scenarioSelect");
  sel.innerHTML = SCENARIOS.map((s) => `<option value="${s.id}">${esc(s.title)}</option>`).join("");
  function loadScenario(id) {
    const s = SCENARIOS.find((x) => x.id === id) || SCENARIOS[0];
    $("#scenarioDesc").textContent = s.desc;
    if (s.id !== "custom") $("#scenarioLines").value = s.lines.join("\n");
    $("#labCarry").checked = !!s.carry;
  }
  sel.addEventListener("change", () => loadScenario(sel.value));
  loadScenario(SCENARIOS[0].id);

  let labStop = false;
  $("#labStop").addEventListener("click", () => { labStop = true; $("#labProgress").textContent = "현재 턴이 끝나면 멈춰요…"; });
  $("#labRun").addEventListener("click", async () => {
    const lines = $("#scenarioLines").value.split("\n").map((s) => s.trim()).filter(Boolean);
    if (!lines.length) return toast("학습자 발화를 한 줄 이상 입력해 주세요.");
    const runs = Math.max(1, Math.min(5, Number($("#labRuns").value) || 1));
    const withBase = $("#labBaseline").checked, carry = $("#labCarry").checked;
    if (carry && !(store.learn.state && Object.keys((store.learn.state || {}).concept_records || {}).length))
      toast("이어받을 학습 기록이 없어 빈 기록으로 실행해요.", 3500);
    labStop = false; $("#labRun").disabled = true; $("#labStop").disabled = false;
    const result = { scenario: sel.value, title: (SCENARIOS.find((s) => s.id === sel.value) || {}).title, lines, runs: [],
      started_at: nowIso(), model: store.settings.model || (health && health.model) || "", carry, with_baseline: withBase };
    store.lab.last = result;
    const total = runs * lines.length * (withBase ? 2 : 1); let done = 0;
    const progress = () => { $("#labProgress").textContent = `진행 ${done}/${total} 호출 단위`; };
    progress();
    for (let r = 0; r < runs && !labStop; r++) {
      let state = null;
      if (carry && store.learn.state) {
        state = clone(store.learn.state);
        state.learning_context = { topic: "", goal: "", concept_id: "" }; state.messages = []; state.learning_phase = "awaiting_topic";
        state.awaiting_registry_confirmation = false; state.pending_new_unit = false; state.pending_start_requests = []; state.pending_study_strategy = null;
      }
      const run = { run: r + 1, turns: [] }; result.runs.push(run);
      let history = [];
      for (let t = 0; t < lines.length && !labStop; t++) {
        const row = { turn: t + 1, input: lines[t] };
        try {
          const res = await api("/api/turn", turnBody("turn", lines[t], state));
          state = res.state;
          row.response = (res.outputs || []).filter((o) => o.kind !== "html").map((o) => o.content).join("\n");
          row.log = (res.new_logs || [])[0] || null; row.events = res.events || [];
          const act = (res.progress.skills || []).find((s) => s.active); row.active_state = act ? act.state : null;
          row.phase = res.progress.phase; row.elapsed = res.elapsed_sec;
        } catch (e) { row.error = e.message; if (e.status === 401) { labStop = true; openSettings(); } }
        done++; progress();
        if (withBase && !labStop) {
          try { const b = await api("/api/baseline", { text: lines[t], history, model: store.settings.model || null });
            row.baseline = b.reply; history.push({ role: "user", content: lines[t] }, { role: "assistant", content: b.reply }); }
          catch (e) { row.baseline = "⚠ " + e.message; }
          done++; progress();
        }
        run.turns.push(row); renderLab(); save();
      }
    }
    result.finished_at = nowIso(); result.stopped = labStop;
    $("#labRun").disabled = false; $("#labStop").disabled = true;
    $("#labProgress").textContent = labStop ? "중지했어요." : "완료했어요.";
    renderLab(); save();
  });

  function labStats(res) {
    const T = res.lines.length, R = res.runs.length;
    const cellKey = (row) => row ? (row.error ? "오류" : row.log ? row.log.current_skill_state : "설정") : null;
    const actKey = (row) => row ? (row.log ? row.log.next_action : row.error ? "오류" : "설정") : null;
    const perTurn = [];
    let stateAgree = [], actAgree = [];
    for (let t = 0; t < T; t++) {
      const rows = res.runs.map((r) => r.turns[t]).filter(Boolean);
      if (!rows.length) { perTurn.push(null); continue; }
      const mode = (vals) => { const c = {}; vals.forEach((v) => (c[v] = (c[v] || 0) + 1)); const m = Math.max(...Object.values(c)); return m / vals.length; };
      const sa = mode(rows.map(cellKey)), aa = mode(rows.map(actKey));
      perTurn.push({ state: sa, action: aa, n: rows.length });
      if (rows.length > 1 && rows.some((r) => r.log)) { stateAgree.push(sa); actAgree.push(aa); }
    }
    const logs = res.runs.flatMap((r) => r.turns.map((x) => x.log).filter(Boolean));
    const changes = logs.filter((l) => l.previous_skill_state !== l.current_skill_state);
    const grounded = changes.filter((l) => (l.evidence_note || "").trim() && (l.transition_reason || "").trim());
    const qok = logs.filter((l) => (l.rule_check || {}).questions_ok !== false);
    const allok = logs.filter((l) => { const c = l.rule_check || {}; return c.chars_ok !== false && c.questions_ok !== false && c.state_step_ok !== false && c.tone_ok !== false; });
    let repeats = 0;
    for (const r of res.runs) { let prev = null, streak = 0; for (const x of r.turns) { const a = x.log && x.log.next_action; if (a && a === prev) { streak++; if (streak === 2) repeats++; } else streak = 0; prev = a; } }
    const avg = (a) => (a.length ? a.reduce((s, x) => s + x, 0) / a.length : null);
    return { perTurn, stateAgree: avg(stateAgree), actAgree: avg(actAgree), changes: changes.length, grounded: grounded.length,
      qok: logs.length ? qok.length / logs.length : null, allok: logs.length ? allok.length / logs.length : null, repeats, logs: logs.length, R };
  }
  const pct = (x) => (x == null ? "–" : Math.round(x * 100) + "%");
  const agreeClass = (x) => (x == null ? "" : x >= 0.99 ? "agree-hi" : x >= 0.66 ? "agree-mid" : "agree-lo");

  function renderLab() {
    const res = store.lab.last;
    const has = res && res.runs.length;
    $("#labCsv").disabled = !has; $("#labJson").disabled = !has;
    if (!has) return;
    const st = labStats(res);
    $("#labMetrics").innerHTML = [
      ["① State 판정 일관성", pct(st.stateAgree), `턴별 최빈 State 일치율 (실행 ${st.R}회)`],
      ["③ 행동 선택 일관성", pct(st.actAgree), "턴별 최빈 행동 일치율"],
      ["② 근거 있는 상태 변경", st.changes ? `${st.grounded}/${st.changes}` : "–", "판단 근거와 변경 조건이 모두 기록됨"],
      ["④ 질문 1개 이하", pct(st.qok), `같은 행동 3연속 ${st.repeats}회`],
      ["규칙 검사 통과", pct(st.allok), "글자 수·질문 수·State 이동·말투"],
    ].map(([l, v, s]) => `<div class="metric"><div class="l">${esc(l)}</div><div class="v">${esc(v)}</div><div class="l">${esc(s)}</div></div>`).join("");
    const head = `<tr><th>턴</th><th>학습자 발화</th>${res.runs.map((r) => `<th>실행 ${r.run}</th>`).join("")}<th>State 일치</th><th>행동 일치</th></tr>`;
    const body = res.lines.map((line, t) => {
      const cells = res.runs.map((r) => {
        const row = r.turns[t];
        if (!row) return `<td class="muted">…</td>`;
        if (row.error) return `<td class="flag-bad">오류</td>`;
        if (!row.log) return `<td class="muted">설정 단계${(row.events || []).length ? '<br><span class="tag">보조 규칙 2</span>' : ""}</td>`;
        return `<td>${statePill(row.log.current_skill_state)}<br><span class="small">${esc(ACTION_LABEL[row.log.next_action] || row.log.next_action)}</span></td>`;
      }).join("");
      const p = st.perTurn[t];
      return `<tr><td>${t + 1}</td><td class="utt">${esc(line)}</td>${cells}<td class="${agreeClass(p && p.state)}">${p ? pct(p.state) : "–"}</td><td class="${agreeClass(p && p.action)}">${p ? pct(p.action) : "–"}</td></tr>`;
    }).join("");
    $("#labMatrix").innerHTML = `<table><thead>${head}</thead><tbody>${body}</tbody></table>`;
    $("#labTranscripts").innerHTML = res.runs.map((r) => `<details class="transcript"><summary>실행 ${r.run} 대화 보기</summary>`
      + r.turns.map((x) => `<div class="tline"><span class="who">학습자</span>${esc(x.input)}</div>`
        + `<div class="tline"><span class="who">STUDY</span>${esc(x.error ? "⚠ " + x.error : x.response)}${x.log ? `<br><span class="muted small">[${esc(ACTION_LABEL[x.log.next_action] || x.log.next_action)} / ${esc(STATE_SHORT[x.log.previous_skill_state])}→${esc(STATE_SHORT[x.log.current_skill_state])} / ${esc(x.log.evidence_note)}]</span>` : ""}</div>`
        + (x.baseline ? `<div class="tline"><span class="who">Baseline</span>${esc(x.baseline)}</div>` : "")).join("")
      + `</details>`).join("");
  }
  $("#labCsv").addEventListener("click", () => {
    const res = store.lab.last; if (!res) return;
    const rows = [["scenario", "run", "turn", "input", "phase", "prev_state", "state", "action", "rules", "concept", "reasoning", "transfer",
      "concept_source", "reasoning_source", "transfer_source", "core_misconception", "evidence_note", "transition_reason", "missing_key_point",
      "chars_ok", "questions_ok", "state_step_ok", "tone_ok", "aux_rule_2", "response", "baseline_response", "error", "elapsed_sec"]];
    for (const r of res.runs) for (const x of r.turns) {
      const l = x.log || {}, c = l.rule_check || {};
      rows.push([res.scenario, r.run, x.turn, x.input, x.phase, l.previous_skill_state, l.current_skill_state, l.next_action, (l.applied_rules || []).join("·"),
        l.concept, l.reasoning, l.transfer, l.concept_source, l.reasoning_source, l.transfer_source, l.core_misconception, l.evidence_note,
        l.transition_reason, l.missing_key_point, c.chars_ok, c.questions_ok, c.state_step_ok, c.tone_ok, (x.events || []).length > 0,
        x.response, x.baseline, x.error, x.elapsed]);
    }
    download(`study_lab_${res.scenario}_${stamp()}.csv`, csv(rows), "text/csv");
  });
  $("#labJson").addEventListener("click", () => { const res = store.lab.last; if (res) download(`study_lab_${res.scenario}_${stamp()}.json`, JSON.stringify(res, null, 2)); });

  // ------------------------------------------------------------------ records & feedback tab
  function renderSurvey() {
    $("#surveyForm").innerHTML = SURVEY.map((q, i) => `<div class="q"><div class="q-text">${i + 1}. ${esc(q.text)}<span class="q-tag">${esc(q.tag)}</span></div>
      <div class="likert"><span class="muted anchor">전혀 아니다</span>${[1, 2, 3, 4, 5].map((v) => `<label><input type="radio" name="${q.id}" value="${v}"><span>${v}</span></label>`).join("")}<span class="muted anchor">매우 그렇다</span></div></div>`).join("")
      + `<label class="field-label" for="svGood">좋았던 점</label><textarea id="svGood" rows="2"></textarea>
         <label class="field-label" for="svBad">아쉬웠던 점 · 불편했던 장면</label><textarea id="svBad" rows="2"></textarea>
         <label class="field-label" for="svIdea">바라는 점</label><textarea id="svIdea" rows="2"></textarea>
         <label class="field-label" for="svName">이름 또는 별칭 (선택)</label><input type="text" id="svName" placeholder="예: 테스터 A">
         <div class="row-actions"><button class="btn primary" type="submit">설문 저장</button></div>`;
  }
  $("#surveyForm").addEventListener("submit", (e) => {
    e.preventDefault();
    const answers = {}; SURVEY.forEach((q) => { const c = $(`input[name=${q.id}]:checked`); if (c) answers[q.id] = Number(c.value); });
    if (!Object.keys(answers).length && !$("#svGood").value.trim() && !$("#svBad").value.trim()) return toast("한 문항 이상 답해 주세요.");
    const logs = (store.learn.state || {}).logs || [];
    store.feedback.surveys.push({ id: uid(), ts: nowIso(), name: $("#svName").value.trim(), topic: (store.learn.progress || {}).topic || "",
      answers, good: $("#svGood").value.trim(), bad: $("#svBad").value.trim(), idea: $("#svIdea").value.trim(), turns: logs.length });
    save(); renderSurvey(); renderRecords(); toast("설문을 저장했어요. 고마워요!");
  });

  function feedbackStats() {
    const s = store.feedback.surveys, r = store.feedback.ratings;
    const avg = {}; SURVEY.forEach((q) => { const v = s.map((x) => x.answers[q.id]).filter((x) => x); avg[q.id] = v.length ? v.reduce((a, b) => a + b, 0) / v.length : null; });
    return { n: s.length, avg, up: r.filter((x) => x.rating === 1).length, down: r.filter((x) => x.rating === -1).length, notes: r.filter((x) => x.note) };
  }
  function renderRecords() {
    const st = feedbackStats();
    $("#feedbackSummary").innerHTML = `<div class="metrics">
        <div class="metric"><div class="l">설문 응답</div><div class="v">${st.n}</div></div>
        <div class="metric"><div class="l">응답 평가</div><div class="v">👍 ${st.up} · 👎 ${st.down}</div></div></div>`
      + (st.n ? `<table><thead><tr><th>문항</th><th>평균 (1–5)</th></tr></thead><tbody>${SURVEY.map((q, i) => `<tr><td>${i + 1}. ${esc(q.text)} <span class="q-tag">${esc(q.tag)}</span></td><td>${st.avg[q.id] == null ? "–" : st.avg[q.id].toFixed(2)}</td></tr>`).join("")}</tbody></table>` : `<p class="muted">아직 설문 응답이 없어요.</p>`)
      + (st.notes.length ? `<div class="field-label">응답 메모</div>` + st.notes.slice(-6).map((n) => `<div class="vuln-item">${n.rating === -1 ? "👎" : n.rating === 1 ? "👍" : "✎"} ${esc(n.note)} <span class="muted small">— ${esc(ACTION_LABEL[n.action] || n.action || n.source)}</span></div>`).join("") : "");
    const logs = (store.learn.state || {}).logs || [];
    $("#auditSummary").innerHTML = auditHtml(logs, false);
    $("#logTable").innerHTML = logs.length ? `<table><thead><tr><th>턴</th><th>학습자 입력</th><th>의도</th><th>행동 / 적용 규칙</th><th>State</th><th>C·R·T</th><th>판단 근거</th><th>규칙 검사</th></tr></thead><tbody>`
      + logs.map((l) => { const c = l.rule_check || {}; const bad = [c.chars_ok === false && "글자", c.questions_ok === false && "질문", c.state_step_ok === false && "State", c.tone_ok === false && "말투"].filter(Boolean);
        return `<tr><td>${l.turn_id}</td><td class="utt">${esc(l.user_input)}</td><td>${esc(l.intent)}</td><td>${esc(ACTION_LABEL[l.next_action] || l.next_action)}<br><span class="muted">규칙 ${esc((l.applied_rules || []).join("·"))}</span></td>`
          + `<td>${esc(STATE_SHORT[l.previous_skill_state])} → ${esc(STATE_SHORT[l.current_skill_state])}</td><td>${dimMini("concept", l.concept, l.concept_source)}${dimMini("reasoning", l.reasoning, l.reasoning_source)}${dimMini("transfer", l.transfer, l.transfer_source)}</td>`
          + `<td class="utt">${esc(l.evidence_note)}</td><td>${bad.length ? `<span class="flag-bad">${esc(bad.join(", "))}</span>` : "통과"}</td></tr>`; }).join("") + `</tbody></table>`
      : `<p class="muted">학습 탭에서 대화를 하면 턴마다 로그가 쌓여요.</p>`;
  }
  function auditHtml(logs, compact) {
    if (!logs.length) return `<span class="muted">아직 기록된 턴이 없어요.</span>`;
    const n = logs.length, f = (k) => logs.filter((l) => (l.rule_check || {})[k] === false).length;
    const items = [["검사한 턴", n], ["글자 수 초과", f("chars_ok")], ["질문 2개 이상", f("questions_ok")], ["State 2단계 이동", f("state_step_ok")], ["합니다체", f("tone_ok")]];
    const changes = logs.filter((l) => l.previous_skill_state !== l.current_skill_state).length;
    items.push(["State 변경", changes]);
    if (compact) return items.map(([l, v]) => `<div>${esc(l)}: <b class="${v && l !== "검사한 턴" && l !== "State 변경" ? "flag-bad" : ""}">${v}</b></div>`).join("");
    return items.map(([l, v]) => `<div class="metric"><div class="l">${esc(l)}</div><div class="v ${v && l !== "검사한 턴" && l !== "State 변경" ? "flag-bad" : ""}">${v}</div></div>`).join("");
  }

  $("#fbExport").addEventListener("click", () => {
    download(`study_feedback_${stamp()}.json`, JSON.stringify({ type: "study-feedback", version: 1, exported_at: nowIso(), surveys: store.feedback.surveys, ratings: store.feedback.ratings }, null, 2));
  });
  $("#fbImport").addEventListener("change", async (e) => {
    let added = 0;
    for (const file of e.target.files) {
      try {
        const data = JSON.parse(await file.text());
        if (data.type !== "study-feedback") { toast(`${file.name}: 피드백 파일이 아니에요.`); continue; }
        const ids = new Set(store.feedback.surveys.map((s) => s.id)), rids = new Set(store.feedback.ratings.map((s) => s.id));
        for (const s of data.surveys || []) if (!ids.has(s.id)) { store.feedback.surveys.push(s); added++; }
        for (const r of data.ratings || []) if (!rids.has(r.id)) store.feedback.ratings.push(r);
      } catch (err) { toast(`${file.name}을(를) 읽지 못했어요.`); }
    }
    e.target.value = ""; save(); renderRecords(); toast(`설문 ${added}건을 합쳤어요.`);
  });
  $("#fbReport").addEventListener("click", async () => {
    const st = feedbackStats(), s = store.feedback.surveys;
    if (!st.n && !st.notes.length) return toast("아직 모은 피드백이 없어요.");
    let t = `5-3. 사용자 피드백 (MVP 테스트 ${st.n}명)\n\n`;
    SURVEY.forEach((q, i) => { if (st.avg[q.id] != null) t += `- ${q.text} (${q.tag}): 평균 ${st.avg[q.id].toFixed(1)}/5\n`; });
    t += `- 응답 단위 평가: 👍 ${st.up}건, 👎 ${st.down}건\n\n`;
    const quotes = (k, title) => { const v = s.map((x) => x[k]).filter(Boolean); if (v.length) { t += `${title}\n` + v.map((x) => `  · “${x}”`).join("\n") + "\n\n"; } };
    quotes("good", "좋았던 점"); quotes("bad", "아쉬웠던 점"); quotes("idea", "바라는 점");
    if (st.notes.length) t += "응답에 남긴 메모\n" + st.notes.map((n) => `  · [${ACTION_LABEL[n.action] || n.action || n.source}] ${n.note}`).join("\n") + "\n";
    try { await navigator.clipboard.writeText(t); toast("보고서 초안을 복사했어요."); }
    catch (e) { download(`study_feedback_report_${stamp()}.txt`, t, "text/plain"); }
  });

  function exportRecords() {
    const st = store.learn.state || {};
    const payload = {
      version: 3.13, saved_at: nowIso().slice(0, 19),
      learning_context: st.learning_context || { topic: "", goal: "", concept_id: "" },
      concept_records: st.concept_records || {}, logs: st.logs || [],
      session: { learning_phase: st.learning_phase || "idle", awaiting_registry_confirmation: !!st.awaiting_registry_confirmation,
        pending_new_unit: !!st.pending_new_unit, pending_study_strategy: st.pending_study_strategy || null,
        pending_start_requests: st.pending_start_requests || [], messages: (st.messages || []).slice(-12) },
      web: { chat: store.learn.chat, pending_post_explanation_check: !!st.pending_post_explanation_check }
    };
    download(`study_llm_v3_13_records.json`, JSON.stringify(payload, null, 2));
  }
  $("#recExport").addEventListener("click", exportRecords);
  $("#recImport").addEventListener("change", async (e) => {
    const file = e.target.files[0]; e.target.value = "";
    if (!file) return;
    try {
      const p = JSON.parse(await file.text());
      if (!p.concept_records || !p.learning_context) throw new Error("STUDY 기록 파일 형식이 아니에요.");
      const sess = p.session || {};
      const state = { learning_context: p.learning_context, concept_records: p.concept_records, logs: p.logs || [],
        messages: sess.messages || [], learning_phase: sess.learning_phase || (p.learning_context.topic ? "learning" : "idle"),
        awaiting_registry_confirmation: !!sess.awaiting_registry_confirmation, pending_new_unit: !!sess.pending_new_unit,
        pending_study_strategy: sess.pending_study_strategy || null, pending_start_requests: sess.pending_start_requests || [],
        pending_post_explanation_check: !!(p.web && p.web.pending_post_explanation_check) };
      const r = await api("/api/turn", turnBody("progress", "", state));
      store.learn.state = r.state; store.learn.progress = r.progress; store.learn.units = r.units;
      store.learn.chat = (p.web && p.web.chat) || (state.messages || []).map((m) => ({ id: uid(), role: m.role === "user" ? "user" : "bot", kind: "text", content: m.content, ts: nowIso() }));
      store.learn.chat.push({ id: uid(), role: "system", content: "학습 기록을 불러왔어요. 이어서 입력해 주세요.", ts: nowIso() });
      save(); renderChat(); renderSide(); renderRecords(); switchTab("learn");
    } catch (err) { toast("불러오기 실패: " + err.message, 4000); }
  });
  $("#logCsv").addEventListener("click", () => {
    const logs = (store.learn.state || {}).logs || [];
    if (!logs.length) return toast("아직 로그가 없어요.");
    const keys = ["turn_id", "timestamp", "topic", "user_input", "intent", "next_action", "applied_rules", "target_skill_id", "previous_skill_state", "current_skill_state",
      "concept", "reasoning", "transfer", "concept_source", "reasoning_source", "transfer_source", "core_misconception", "evidence_note", "transition_reason",
      "missing_key_point", "vulnerability", "response"];
    const rows = [keys.concat(["chars_ok", "questions_ok", "state_step_ok", "tone_ok"])];
    for (const l of logs) { const c = l.rule_check || {}; rows.push(keys.map((k) => Array.isArray(l[k]) ? l[k].join("·") : l[k]).concat([c.chars_ok, c.questions_ok, c.state_step_ok, c.tone_ok])); }
    download(`study_logs_${stamp()}.csv`, csv(rows), "text/csv");
  });
  $("#recReset").addEventListener("click", () => {
    if (!confirm("학습 기록, 대화, 로그를 모두 지울까요? (피드백 설문은 유지돼요)")) return;
    store.learn = { state: null, chat: [], progress: null, units: [] }; save(); renderChat(); renderSide(); renderRecords(); toast("초기화했어요.");
  });

  // ------------------------------------------------------------------ boot
  applyResearch(); renderChat(); renderSide(); renderCompare(); renderSurvey(); renderLab(); checkHealth();
})();
