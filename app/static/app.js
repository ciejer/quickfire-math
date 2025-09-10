// Minimal client logic: timer, sound, speech and spaced repetition.

function fmtTime(ms) {
  const s = Math.floor(ms / 1000);
  const m = Math.floor(s / 60);
  const r = s % 60;
  return `${m}:${r.toString().padStart(2, '0')}`;
}

// Audio helpers
const audioCtx = typeof window !== 'undefined' && 'AudioContext' in window ? new AudioContext() : null;

function tone(freq, dur = 0.12, gain = 0.04, when = 0) {
  if (!audioCtx) return;
  const o = audioCtx.createOscillator();
  const g = audioCtx.createGain();
  o.type = 'sine';
  o.frequency.value = freq;
  g.gain.value = gain;
  o.connect(g);
  g.connect(audioCtx.destination);
  o.start(audioCtx.currentTime + when);
  o.stop(audioCtx.currentTime + when + dur);
}

function ding() {
  tone(880, 0.08, 0.06);
}

function winSound() {
  [523.25, 659.25, 783.99].forEach((f, i) => tone(f, 0.15, 0.05, i * 0.1));
}

function say(text) {
  if (!window.speechSynthesis) return;
  const u = new SpeechSynthesisUtterance(text);
  u.rate = 1.05;
  speechSynthesis.cancel();
  speechSynthesis.speak(u);
}

async function fetchNext(type) {
  const fd = new FormData();
  fd.set('drill_type', type);
  const res = await fetch('/next', { method: 'POST', body: fd });
  if (!res.ok) throw new Error('next failed');
  return await res.json();
}

function insertWithin(arr, item, minAhead = 3, maxAhead = 5) {
  const pos = Math.min(arr.length, Math.floor(Math.random() * (maxAhead - minAhead + 1)) + minAhead);
  arr.splice(pos, 0, item);
}

document.addEventListener('DOMContentLoaded', () => {
  const drill = window.DRILL;
  if (!drill) return;
  const promptEl = document.getElementById('prompt');
  const ansEl = document.getElementById('answer');
  const formEl = document.getElementById('answer-form');
  const qDoneEl = document.getElementById('q-done');
  const timerEl = document.getElementById('timer');

  let queue = [
    {
      prompt: drill.first.prompt,
      answer: drill.first.answer,
      tts: drill.first.tts,
    },
  ];
  let done = 0;
  let running = true;
  const start = performance.now();

  async function topUpQueue() {
    while (queue.length < 6 && done + queue.length < drill.target) {
      const nxt = await fetchNext(drill.type);
      queue.push({ prompt: nxt.prompt, answer: nxt.answer, tts: nxt.tts });
    }
  }

  function tick() {
    if (!running) return;
    const now = performance.now();
    timerEl.textContent = fmtTime(now - start);
    requestAnimationFrame(tick);
  }
  requestAnimationFrame(tick);

  function showCurrent() {
    promptEl.textContent = queue[0] ? queue[0].prompt : '';
    ansEl.value = '';
    ansEl.focus();
  }

  async function finish() {
    running = false;
    winSound();
    const elapsed = Math.floor(performance.now() - start);
    const fd = new FormData();
    fd.set('drill_type', drill.type);
    fd.set('elapsed_ms', String(elapsed));
    fd.set('settings_human', document.getElementById('settings-human')?.textContent ?? '');
    fd.set('question_count', String(drill.target));
    await fetch('/finish', { method: 'POST', body: fd });
    promptEl.textContent = `Nice one! Time: ${fmtTime(elapsed)}`;
  }

  formEl.addEventListener('submit', async (e) => {
    e.preventDefault();
    if (!queue.length) return;
    const current = queue.shift();
    const val = parseInt(ansEl.value, 10);
    if (Number.isNaN(val)) return;
    if (val === current.answer) {
      ding();
      done += 1;
      qDoneEl.textContent = String(done);
      if (done >= drill.target) {
        await finish();
        return;
      }
      await topUpQueue();
      showCurrent();
    } else {
      say(current.tts);
      insertWithin(queue, current, 3, 5);
      await topUpQueue();
      showCurrent();
    }
  });

  topUpQueue().then(showCurrent);
});