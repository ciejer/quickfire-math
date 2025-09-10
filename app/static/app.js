// Utilities
function fmtTime(ms) {
  const s = Math.floor(ms / 1000);
  const m = Math.floor(s / 60);
  const r = s % 60;
  return `${m}:${r.toString().padStart(2, "0")}`;
}

const audioCtx =
  typeof window !== "undefined" && "AudioContext" in window ? new AudioContext() : null;

function tone(freq, dur = 0.12, gain = 0.04, when = 0) {
  if (!audioCtx) return;
  const o = audioCtx.createOscillator();
  const g = audioCtx.createGain();
  o.type = "sine";
  o.frequency.value = freq;
  g.gain.value = gain;
  o.connect(g);
  g.connect(audioCtx.destination);
  o.start(audioCtx.currentTime + when);
  o.stop(audioCtx.currentTime + when + dur);
}

function ding() { tone(880, 0.08, 0.06); }
function winSound() { [523.25, 659.25, 783.99].forEach((f, i) => tone(f, 0.15, 0.05, i * 0.1)); }

function say(text) {
  if (!window.speechSynthesis) return;
  const u = new SpeechSynthesisUtterance(text);
  u.rate = 1.05;
  speechSynthesis.cancel();
  speechSynthesis.speak(u);
}

// API
async function fetchNext(type) {
  const fd = new FormData(); fd.set("drill_type", type);
  const res = await fetch("/next", { method: "POST", body: fd });
  if (!res.ok) throw new Error("next failed");
  return await res.json();
}
async function fetchFeed() { const r = await fetch("/feed"); return r.ok ? r.json() : { items: [] }; }
async function fetchStats() { const tz = new Date().getTimezoneOffset(); const r = await fetch(`/stats?tz_offset=${encodeURIComponent(tz)}`); return r.ok ? r.json() : null; }
async function fetchReportMul() { const r = await fetch("/report/multiplication"); return r.ok ? r.json() : null; }

// Rendering
function renderFeed(container, items) {
  if (!container) return;
  if (!items || !items.length) {
    container.innerHTML = `<div class="news-empty">No drills yet — hit Start.</div>`;
    return;
  }
  const fmt = (iso) => new Date(iso).toLocaleString(undefined, { weekday: "long", hour: "2-digit", minute: "2-digit" });
  container.innerHTML = items.map(d => {
    const mins = Math.floor(d.elapsed_ms / 60000);
    const secs = Math.floor((d.elapsed_ms / 1000) % 60);
    return `<div class="news-item"><div class="news-time">${fmt(d.ts)}</div><div class="news-settings">${d.settings}</div><div class="news-result">${mins} min ${secs} secs</div></div>`;
  }).join("");
}
function renderStats(listEl, stats) {
  if (!listEl || !stats) return;
  listEl.innerHTML = `
    <li>Total: <strong>${stats.total}</strong></li>
    <li>Addition: <strong>${stats.addition}</strong></li>
    <li>Subtraction: <strong>${stats.subtraction}</strong></li>
    <li>Multiplication: <strong>${stats.multiplication}</strong></li>
    <li>Division: <strong>${stats.division}</strong></li>`;
}

function renderMulHeatmap(el, data) {
  if (!el || !data || !data.grid) return;
  const g = data.grid;
  let html = `<div class="hm"><div class="hm-row hm-head"><span></span>${Array.from({length:12},(_,i)=>`<span>${i+1}</span>`).join("")}</div>`;
  for (let a=1;a<=12;a++) {
    html += `<div class="hm-row"><span class="hm-headcell">${a}</span>`;
    for (let b=1;b<=12;b++) {
      const v = g[a][b];
      // darker red = worse (higher score). null = no data (dim)
      let bg = "rgba(255,255,255,0.06)";
      if (v !== null) {
        const clamped = Math.max(0, Math.min(1, v));
        const alpha = 0.15 + clamped*0.65;
        bg = `rgba(255, 80, 80, ${alpha})`;
      }
      html += `<span class="hm-cell" title="${a}×${b}" style="background:${bg}"></span>`;
    }
    html += `</div>`;
  }
  html += `</div>`;
  el.innerHTML = html;
}

// --- Chooser page
function initHome() {
  const opCards = Array.from(document.querySelectorAll(".op-card input[type=radio]"));
  if (opCards.length) {
    const idx = Math.floor(Math.random() * opCards.length);
    opCards[idx].checked = true;
    updateCardStyles();
  }
  function updateCardStyles() {
    document.querySelectorAll(".op-card").forEach((lbl) => {
      const input = lbl.querySelector("input");
      lbl.classList.toggle("selected", input && input.checked);
    });
  }
  document.querySelectorAll(".op-card").forEach((lbl) => {
    lbl.addEventListener("click", () => {
      const input = lbl.querySelector("input");
      if (input) { input.checked = true; updateCardStyles(); }
    });
  });

  const statsList = document.getElementById("stats-list");
  fetchStats().then((s) => renderStats(statsList, s));
  const feedList = document.getElementById("feed-list");
  fetchFeed().then((f) => renderFeed(feedList, f.items));

  const rep = document.getElementById("report-mul");
  fetchReportMul().then((d) => renderMulHeatmap(rep, d));
}

// --- Drill page
function parsePrompt(prompt) {
  const m = prompt.match(/^\s*(\d+)\s*([+\u2212\u00D7\u00F7])\s*(\d+)\s*$/);
  if (!m) return null;
  return { a: m[1], op: m[2], b: m[3] };
}
function renderEquationFromPrompt(prompt) {
  const parts = parsePrompt(prompt);
  const a = document.getElementById("num-a");
  const b = document.getElementById("num-b");
  const op = document.getElementById("op");
  if (parts && a && b && op) {
    a.textContent = parts.a;
    b.textContent = parts.b;
    op.textContent = parts.op;
  }
}

function insertWithin(arr, item, minAhead = 3, maxAhead = 5) {
  const pos = Math.min(arr.length, Math.floor(Math.random() * (maxAhead - minAhead + 1)) + minAhead);
  arr.splice(pos, 0, item);
}

function initDrill() {
  const drill = window.DRILL;
  if (!drill) return;

  const ansEl = document.getElementById("answer");
  const formEl = document.getElementById("answer-form");
  const qDoneEl = document.getElementById("q-done");
  const qTotalEl = document.getElementById("q-total");
  const timerEl = document.getElementById("timer");
  const finishActions = document.getElementById("finish-actions");
  const overlay = document.getElementById("overlay");
  const overlayContent = document.getElementById("overlay-content");

  let queue = [{ prompt: drill.first.prompt, answer: drill.first.answer, tts: drill.first.tts }];
  let done = 0;
  let misses = 0;
  let running = true;
  let start = performance.now();

  // Per-question logging
  let currentStart = new Date();
  const qlog = [];

  function tick() {
    if (!running) return;
    const now = performance.now();
    timerEl.textContent = fmtTime(now - start);
    requestAnimationFrame(tick);
  }
  requestAnimationFrame(tick);

  function showCurrent() {
    if (!queue.length) return;
    renderEquationFromPrompt(queue[0].prompt);
    ansEl.value = "";
    ansEl.focus();
    currentStart = new Date();
  }

  async function topUpQueue() {
    while (queue.length < 6 && done + queue.length < drill.target) {
      const nxt = await fetchNext(drill.type);
      queue.push({ prompt: nxt.prompt, answer: nxt.answer, tts: nxt.tts });
    }
  }

  async function finish() {
    running = false;
    winSound();
    const elapsed = Math.floor(performance.now() - start);
    const correctFirstTry = drill.target - misses;

    const fd = new FormData();
    fd.set("drill_type", drill.type);
    fd.set("elapsed_ms", String(elapsed));
    fd.set("settings_human", document.getElementById("settings-human")?.textContent ?? "");
    fd.set("question_count", String(drill.target));
    fd.set("score", String(correctFirstTry));
    fd.set("qlog", JSON.stringify(qlog));
    await fetch("/finish", { method: "POST", body: fd });

    // UI
    document.getElementById("equation").classList.add("finished");
    formEl.classList.add("hidden");
    finishActions.classList.remove("hidden");

    // Sidebar refresh
    fetchStats().then((s) => renderStats(document.getElementById("stats-list"), s));
    fetchFeed().then((f) => renderFeed(document.getElementById("feed-list"), f.items));

    // Helper banner
    const helper = document.getElementById("helper");
    helper.textContent = `Nice one! Time: ${fmtTime(elapsed)} • Score ${correctFirstTry}/${drill.target}`;
  }

  formEl.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (!queue.length) return;
    const current = queue.shift();
    const val = parseInt(ansEl.value, 10);
    if (Number.isNaN(val)) return;

    const elapsed = new Date() - currentStart;
    const parsed = parsePrompt(current.prompt) || {a: "0", b: "0", op: "?"};

    if (val === current.answer) {
      ding();
      // log
      qlog.push({
        prompt: current.prompt,
        a: parseInt(parsed.a,10), b: parseInt(parsed.b,10),
        correct_answer: current.answer,
        given_answer: val,
        correct: true,
        started_at: currentStart.toISOString(),
        elapsed_ms: elapsed
      });

      done += 1;
      qDoneEl.textContent = String(done);
      if (done >= drill.target) { await finish(); return; }
      await topUpQueue();
      showCurrent();
    } else {
      misses += 1;
      say(current.tts);

      // log
      qlog.push({
        prompt: current.prompt,
        a: parseInt(parsed.a,10), b: parseInt(parsed.b,10),
        correct_answer: current.answer,
        given_answer: val,
        correct: false,
        started_at: currentStart.toISOString(),
        elapsed_ms: elapsed
      });

      // Visual overlay for 3s
      if (parsed) {
        overlayContent.textContent = `${parsed.a} ${parsed.op} ${parsed.b} = ${current.answer}`;
        overlay.classList.remove("hidden");
      }
      insertWithin(queue, current, 3, 5);
      await topUpQueue();

      formEl.classList.add("disabled");
      setTimeout(() => {
        overlay.classList.add("hidden");
        formEl.classList.remove("disabled");
        showCurrent();
      }, 3000);
    }
  });

  // Initial render & focus
  renderEquationFromPrompt(queue[0].prompt);
  topUpQueue();
  ansEl.focus();
}

// Boot
document.addEventListener("DOMContentLoaded", () => {
  if (document.getElementById("choose-form")) initHome();
  if (window.DRILL) initDrill();
});
