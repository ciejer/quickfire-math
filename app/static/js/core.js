// Core helpers wrapped to avoid redeclaration on double-load
(function(){
  if(window.QF){ return; }

  // -------- time helpers --------
  function fmtTime(ms){ const s=Math.floor(ms/1000), m=Math.floor(s/60), r=s%60; return `${m}:${r.toString().padStart(2,"0")}`; }

  // -------- audio & speech --------
  const audioCtx = typeof window!=="undefined" && "AudioContext" in window ? new AudioContext() : null;
  let mediaUnlocked=false;
  function unlockMediaOnce(){ if(mediaUnlocked) return; try{ if(audioCtx&&audioCtx.state==="suspended") audioCtx.resume(); }catch{} try{ if("speechSynthesis" in window){ speechSynthesis.getVoices(); speechSynthesis.onvoiceschanged=()=>{}; } }catch{} mediaUnlocked=true; }
  ["touchstart","pointerdown","mousedown","keydown","click"].forEach(e=>window.addEventListener(e,unlockMediaOnce,{once:true,passive:true}));
  function tone(f,d=0.12,g=0.04,w=0){ if(!audioCtx) return; const o=audioCtx.createOscillator(), a=audioCtx.createGain(); o.type="sine"; o.frequency.value=f; a.gain.value=g; o.connect(a); a.connect(audioCtx.destination); o.start(audioCtx.currentTime+w); o.stop(audioCtx.currentTime+w+d); }
  function ding(){ tone(880,0.08,0.06); }
  function winSound(){ [523.25,659.25,783.99].forEach((f,i)=>tone(f,0.15,0.05,i*0.1)); }
  function starSound(){ const seq=[659.25,783.99,987.77,1174.66,1318.51,1567.98]; seq.forEach((f,i)=>{ tone(f,0.12,0.07,i*0.07); tone(f*1.5,0.1,0.045,i*0.07+0.03); }); tone(1975.53,0.18,0.06,seq.length*0.07); }
  function levelUpSound(){ [392,523.25,659.25,783.99,1046.5].forEach((f,i)=>tone(f,0.18,0.06,i*0.12)); }
  function say(text){ if(!window.speechSynthesis) return; try{ const u=new SpeechSynthesisUtterance(text); u.rate=1.05; const enNZ=speechSynthesis.getVoices().find(v=>/en[-_]NZ/i.test(v.lang)); if(enNZ) u.voice=enNZ; speechSynthesis.cancel(); speechSynthesis.speak(u);}catch{} }

  // -------- digit colouring (only where we call setDigits) --------
  function digitsToHTML(str){ return String(str).replace(/\d/g,d=>`<span class="digit d${d}">${d}</span>`); }
  function setDigits(el,text){ if(el) el.innerHTML = digitsToHTML(text); }

  // -------- API helpers --------
  async function apiNext(type, avoid, avoidPair){ const fd=new FormData(); fd.set("drill_type",type); if(avoid) fd.set("avoid_prompt", avoid); if(avoidPair) fd.set("avoid_pair", avoidPair); const r=await fetch("/next",{method:"POST",body:fd}); if(!r.ok) throw new Error("next failed"); return r.json(); }
  async function apiFeed(){ const r=await fetch("/feed"); return r.ok? r.json(): {items:[]}; }
  async function apiStats(){ const tz=new Date().getTimezoneOffset(); const r=await fetch(`/stats?tz_offset=${encodeURIComponent(tz)}`); return r.ok? r.json(): null; }
  async function apiProg(){ const r=await fetch("/progress"); return r.ok? r.json(): null; }
  async function apiReportMul(){ const r=await fetch("/report/multiplication"); return r.ok? r.json(): null; }
  async function apiReportAdd(){ const r=await fetch("/report/addition"); return r.ok? r.json(): null; }
  async function apiReportSub(){ const r=await fetch("/report/subtraction"); return r.ok? r.json(): null; }

  // -------- feed + stats renderers --------
  function renderFeed(container,items){
    if(!container) return;
    if(!items||!items.length){ container.innerHTML='<div class="news-empty">No drills yet — hit Start.</div>'; return; }
    const fmt = iso => new Date(iso).toLocaleString(undefined,{weekday:"long",hour:"2-digit",minute:"2-digit"});
    container.innerHTML = items.map(d=>{
      const mins=Math.floor(d.time_ms/60000), secs=Math.floor((d.time_ms/1000)%60);
      const star = d.star ? ' <span title="Star earned">★</span>' : '';
      const typeLabel = d.drill_type[0].toUpperCase()+d.drill_type.slice(1);
      const lvl = d.level? ` • Level ${d.level}` : '';
      const score = d.score ? d.score : '';
      return `<div class="news-item">
        <div class="news-time">${fmt(d.ts)}${star}</div>
        <div class="news-settings"><strong>${typeLabel}</strong>${lvl}</div>
        <div class="news-note">${d.label}</div>
        <div class="news-score">Score ${score}</div>
        <div class="news-result">${mins} min ${secs} secs</div>
      </div>`;
    }).join("");
  }
  function renderStats(listEl,s){ if(!listEl||!s) return; listEl.innerHTML = `
      <li>Total: <strong>${s.total}</strong></li>
      <li>Addition: <strong>${s.addition}</strong></li>
      <li>Subtraction: <strong>${s.subtraction}</strong></li>
      <li>Multiplication: <strong>${s.multiplication}</strong></li>
      <li>Division: <strong>${s.division}</strong></li>`; }

  // -------- choose-card helpers --------
  function starDots(last5){ return (last5||"").padStart(5," ").slice(-5).split("").map(c=>c==="1"?"★":"☆").join(""); }
  function renderProgressOnCards(p){ if(!p) return; [["addition","card-addition","level-addition","stars-addition","badge-addition"], ["subtraction","card-subtraction","level-subtraction","stars-subtraction","badge-subtraction"], ["multiplication","card-multiplication","level-multiplication","stars-multiplication","badge-multiplication"], ["division","card-division","level-division","stars-division","badge-division"]].forEach(([k,cardId,levelId,starsId,badgeId])=>{ const card=document.getElementById(cardId), lvlEl=document.getElementById(levelId), stEl=document.getElementById(starsId), badge=document.getElementById(badgeId); const info=p[k]; if(!card||!lvlEl||!stEl||!info) return; const lvlHTML = `Level ${digitsToHTML(String(info.level))}: ${info.label}`; lvlEl.innerHTML = lvlHTML; stEl.textContent = starDots(info.last5); if(badge) badge.textContent = info.need_msg || "Get 3 of your last 5 stars to level up"; }); }

  // Expose minimal API used by page scripts
  window.QF = { fmtTime, ding, winSound, starSound, levelUpSound, say, digitsToHTML, setDigits, starDots, unlockMediaOnce,
    apiNext, apiFeed, apiStats, apiProg, apiReportMul, apiReportAdd, apiReportSub,
    renderFeed, renderStats, renderProgressOnCards };
})();
