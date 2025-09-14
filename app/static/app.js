// time utils
function fmtTime(ms){ const s=Math.floor(ms/1000), m=Math.floor(s/60), r=s%60; return `${m}:${r.toString().padStart(2,"0")}`; }

// audio + speech
const audioCtx = typeof window!=="undefined" && "AudioContext" in window ? new AudioContext() : null;
let mediaUnlocked=false;
function unlockMediaOnce(){ if(mediaUnlocked) return; try{ if(audioCtx&&audioCtx.state==="suspended") audioCtx.resume(); }catch{} try{ if("speechSynthesis" in window){ speechSynthesis.getVoices(); speechSynthesis.onvoiceschanged=()=>{}; } }catch{} mediaUnlocked=true; }
["touchstart","pointerdown","mousedown","keydown","click"].forEach(e=>window.addEventListener(e,unlockMediaOnce,{once:true,passive:true}));
function tone(freq,dur=0.12,gain=0.04,when=0){ if(!audioCtx) return; const o=audioCtx.createOscillator(), g=audioCtx.createGain(); o.type="sine"; o.frequency.value=freq; g.gain.value=gain; o.connect(g); g.connect(audioCtx.destination); o.start(audioCtx.currentTime+when); o.stop(audioCtx.currentTime+when+dur); }
function ding(){ tone(880,0.08,0.06); }
function winSound(){ [523.25,659.25,783.99].forEach((f,i)=>tone(f,0.15,0.05,i*0.1)); }
function say(text){ if(!window.speechSynthesis) return; try{ const u=new SpeechSynthesisUtterance(text); u.rate=1.05; u.pitch=1.0; const enNZ=speechSynthesis.getVoices().find(v=>/en[-_]NZ/i.test(v.lang)); if(enNZ) u.voice=enNZ; speechSynthesis.cancel(); speechSynthesis.speak(u);}catch{} }

// digit colouring — ONLY for operands & wrong-answer overlay
function digitsToHTML(str){ return String(str).replace(/\d/g,d=>`<span class="digit d${d}">${d}</span>`); }
function setDigits(el,text){ if(el) el.innerHTML = digitsToHTML(text); }

// API
async function apiNext(type, avoid){ const fd=new FormData(); fd.set("drill_type",type); if(avoid) fd.set("avoid_prompt", avoid); const r=await fetch("/next",{method:"POST",body:fd}); if(!r.ok) throw new Error("next failed"); return r.json(); }
async function apiFeed(){ const r=await fetch("/feed"); return r.ok? r.json(): {items:[]}; }
async function apiStats(){ const tz=new Date().getTimezoneOffset(); const r=await fetch(`/stats?tz_offset=${encodeURIComponent(tz)}`); return r.ok? r.json(): null; }
async function apiProg(){ const r=await fetch("/progress"); return r.ok? r.json(): null; }
async function apiReportMul(){ const r=await fetch("/report/multiplication"); return r.ok? r.json(): null; }
async function apiReportAdd(){ const r=await fetch("/report/addition"); return r.ok? r.json(): null; }
async function apiReportSub(){ const r=await fetch("/report/subtraction"); return r.ok? r.json(): null; }

// feed + stats (NO digit colouring here)
function renderFeed(container,items){
  if(!container) return;
  if(!items||!items.length){ container.innerHTML='<div class="news-empty">No drills yet — hit Start.</div>'; return; }
  const fmt = iso => new Date(iso).toLocaleString(undefined,{weekday:"long",hour:"2-digit",minute:"2-digit"});
  container.innerHTML = items.map(d=>{
    const mins=Math.floor(d.elapsed_ms/60000), secs=Math.floor((d.elapsed_ms/1000)%60);
    return `<div class="news-item"><div class="news-time">${fmt(d.ts)}</div><div class="news-settings">${d.settings}</div><div class="news-result">${mins} min ${secs} secs</div></div>`;
  }).join("");
}
function renderStats(listEl,s){
  if(!listEl||!s) return;
  listEl.innerHTML = `
    <li>Total: <strong>${s.total}</strong></li>
    <li>Addition: <strong>${s.addition}</strong></li>
    <li>Subtraction: <strong>${s.subtraction}</strong></li>
    <li>Multiplication: <strong>${s.multiplication}</strong></li>
    <li>Division: <strong>${s.division}</strong></li>`;
}

// drill selection tiles
function starDots(last5){ return (last5||"").padStart(5," ").slice(-5).split("").map(c=>c==="1"?"★":"☆").join(""); }
function levelNumber(label,fallback){ const m=(label||"").match(/(\d+)/); return m? m[1]: (fallback??"—"); }
function renderProgressOnCards(p){
  if(!p) return;
  [["addition","card-addition","level-addition","stars-addition","badge-addition"],
   ["subtraction","card-subtraction","level-subtraction","stars-subtraction","badge-subtraction"],
   ["multiplication","card-multiplication","level-multiplication","stars-multiplication","badge-multiplication"],
   ["division","card-division","level-division","stars-division","badge-division"]]
  .forEach(([k,cardId,levelId,starsId,badgeId])=>{
    const card=document.getElementById(cardId), lvlEl=document.getElementById(levelId), stEl=document.getElementById(starsId), badge=document.getElementById(badgeId);
    const info=p[k]; if(!card||!lvlEl||!stEl||!info) return;
    lvlEl.textContent = `Level ${levelNumber(info.label, info.level)}`;
    stEl.textContent = starDots(info.last5);
    if(badge) badge.textContent = info.ready_if_star? "One more star → level up" : "3 of last 5 stars → level up";
  });
}
function initHome(){
  const radios=[...document.querySelectorAll(".op-card input[type=radio]")];
  const cards=[...document.querySelectorAll(".op-card")];
  const update=()=>cards.forEach(lbl=>{ const input=lbl.querySelector("input"); lbl.classList.toggle("selected", !!(input&&input.checked)); });
  if(radios.length){ radios.forEach(r=>r.checked=false); radios[Math.floor(Math.random()*radios.length)].checked=true; update(); }
  cards.forEach(lbl=>lbl.addEventListener("click",()=>{ const input=lbl.querySelector("input"); if(!input) return; radios.forEach(r=>r.checked=false); input.checked=true; update(); }));

  apiStats().then(s=>renderStats(document.getElementById("stats-list"),s));
  apiFeed().then(f=>renderFeed(document.getElementById("feed-list"), f.items));
  apiProg().then(p=>renderProgressOnCards(p));

  // lazy reports
  const repMul=document.getElementById("report-mul"), repAdd=document.getElementById("report-add"), repSub=document.getElementById("report-sub");
  document.querySelectorAll("details.expander").forEach(d=>{
    d.addEventListener("toggle", async ()=>{
      if(d.open && !d.dataset.loaded){
        d.dataset.loaded="1";
        apiReportMul().then(data=>renderHeatmap(repMul,data,1,12));
        apiReportAdd().then(data=>renderHeatmap(repAdd,data,data?.labels_from??0,data?.labels_to??20));
        apiReportSub().then(data=>renderHeatmap(repSub,data,data?.labels_from??0,data?.labels_to??20));
      }
    });
  });
}

// heatmap (error rate: 0 good … 1 bad)
function renderHeatmap(el,data,labelStart=1,labelEnd=12){
  if(!el||!data||!data.grid) return;
  const g=data.grid, from=data.labels_from??labelStart, to=data.labels_to??labelEnd;
  let header=`<div class="hm-row hm-head"><span></span>`; for(let x=from;x<=to;x++) header+=`<span>${x}</span>`; header+=`</div>`;
  let html=`<div class="hm">${header}`;
  for(let a=from;a<=to;a++){
    html+=`<div class="hm-row"><span class="hm-headcell">${a}</span>`;
    for(let b=from;b<=to;b++){
      const v=(g[a]&&g[a][b]!==undefined)?g[a][b]:null;
      let bg="rgba(255,255,255,0.06)";
      if(v!==null){ const clamped=Math.max(0,Math.min(1,v)); const alpha=0.1+clamped*0.7; bg=`rgba(255,80,80,${alpha})`; }
      html+=`<span class="hm-cell" title="${a},${b}" style="background:${bg}"></span>`;
    }
    html+=`</div>`;
  }
  html+=`</div>`;
  el.innerHTML=html;
}

// drill
function parsePrompt(prompt){ const m=prompt.match(/^\s*(\d+)\s*([+\u2212\u00D7\u00F7])\s*(\d+)\s*$/); return m?{a:m[1],op:m[2],b:m[3]}:null; }
function renderEq(prompt){ const p=parsePrompt(prompt); if(!p) return; setDigits(document.getElementById("num-a"), p.a); setDigits(document.getElementById("num-b"), p.b); const op=document.getElementById("op"); if(op) op.textContent=p.op; }
function insertWithin(arr,item,minAhead=3,maxAhead=5){ const pos=Math.min(arr.length, Math.floor(Math.random()*(maxAhead-minAhead+1))+minAhead); arr.splice(pos,0,item); }

function initDrill(){
  const drill=window.DRILL; if(!drill) return;
  const ansEl=document.getElementById("answer"), formEl=document.getElementById("answer-form"), qDoneEl=document.getElementById("q-done"), timerEl=document.getElementById("timer");
  const finishActions=document.getElementById("finish-actions"), nextLvlForm=document.getElementById("nextlvl-form");
  const overlay=document.getElementById("overlay"), overlayContent=document.getElementById("overlay-content");

  // hydrate sidebar on entry
  apiStats().then(s=>renderStats(document.getElementById("stats-list"),s));
  apiFeed().then(f=>renderFeed(document.getElementById("feed-list"), f.items));

  let queue=[{prompt:drill.first.prompt, answer:drill.first.answer, tts:drill.first.tts}];
  let done=0, misses=0, running=true, start=performance.now(); let lastPrompt=null;
  let currentStart=new Date(); const qlog=[]; let lastTimer="";

  function tick(){ if(!running) return; const now=performance.now(); const t=fmtTime(now-start); if(t!==lastTimer){ lastTimer=t; if(timerEl) timerEl.textContent=t; } requestAnimationFrame(tick); }
  requestAnimationFrame(tick);

  function showCurrent(){ if(!queue.length) return; renderEq(queue[0].prompt); ansEl.value=""; ansEl.focus(); currentStart=new Date(); }
  async function topUpQueue(){
    while(queue.length<6 && done+queue.length<drill.target){
      const avoid = queue.length? queue[queue.length-1].prompt : lastPrompt;
      const nxt = await apiNext(drill.type, avoid);
      // additional client-side guard
      if(avoid && nxt.prompt===avoid) continue;
      queue.push({prompt:nxt.prompt, answer:nxt.answer, tts:nxt.tts});
    }
  }

  async function finish(){
    running=false; winSound();
    const elapsed=Math.floor(performance.now()-start);
    const correctFirstTry=drill.target - misses;
    const fd=new FormData();
    fd.set("drill_type",drill.type);
    fd.set("elapsed_ms", String(elapsed));
    fd.set("settings_human", document.getElementById("settings-human")?.textContent ?? "");
    fd.set("question_count", String(drill.target));
    fd.set("score", String(correctFirstTry));
    fd.set("qlog", JSON.stringify(qlog));
    const res=await fetch("/finish",{method:"POST", body:fd});
    let pay={}; try{ pay=await res.json(); }catch{}

    document.getElementById("equation").classList.add("finished");
    formEl.classList.add("hidden"); finishActions.classList.remove("hidden");

    apiStats().then(s=>renderStats(document.getElementById("stats-list"),s));
    apiFeed().then(f=>renderFeed(document.getElementById("feed-list"), f.items));

    const helper=document.getElementById("helper");
    const awards=(pay.awards||[]).join(" • ");
    const starTxt = pay.star ? "⭐ Star earned" : "No star this time";
    if(helper) helper.textContent = `${starTxt} — Time ${fmtTime(elapsed)} • Score ${correctFirstTry}/20` + (awards? ` • ${awards}` : "") + " • Get 3 of your last 5 stars to level up.";
    if(pay.level_up && nextLvlForm) nextLvlForm.classList.remove("hidden");
  }

  formEl.addEventListener("submit", async (e)=>{
    e.preventDefault(); unlockMediaOnce();
    if(!queue.length) return;
    const current=queue.shift();
    const val=parseInt(ansEl.value,10); if(Number.isNaN(val)) return;
    const elapsed=new Date()-currentStart;
    const parsed=parsePrompt(current.prompt) || {a:"0",b:"0",op:"?"};

    if(val===current.answer){
      ding();
      qlog.push({prompt:current.prompt, a:+parsed.a, b:+parsed.b, correct_answer:current.answer, given_answer:val, correct:true, started_at:currentStart.toISOString(), elapsed_ms:elapsed});
      done+=1; if(qDoneEl) qDoneEl.textContent=String(done);
      lastPrompt=current.prompt;
      if(done>=drill.target){ await finish(); return; }
      await topUpQueue(); showCurrent();
    }else{
      say(current.tts);
      qlog.push({prompt:current.prompt, a:+parsed.a, b:+parsed.b, correct_answer:current.answer, given_answer:val, correct:false, started_at:currentStart.toISOString(), elapsed_ms:elapsed});
      overlayContent.innerHTML = `${digitsToHTML(parsed.a)} <span class="op">${parsed.op}</span> ${digitsToHTML(parsed.b)} = ${digitsToHTML(String(current.answer))}`;
      overlay.classList.remove("hidden");
      insertWithin(queue, current, 3, 5);
      await topUpQueue();
      formEl.classList.add("disabled");
      setTimeout(()=>{ overlay.classList.add("hidden"); formEl.classList.remove("disabled"); showCurrent(); }, 3000);
    }
  });

  renderEq(queue[0].prompt);
  topUpQueue(); ansEl.focus();
}

// heatmap styles come from CSS

document.addEventListener("DOMContentLoaded", ()=>{
  if(document.getElementById("choose-form")) initHome();
  if(window.DRILL) initDrill();
});
