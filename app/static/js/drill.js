(function(){
  function commKey(prompt){ const m=prompt.match(/^\s*(\d+)\s*([+\u00D7])\s*(\d+)\s*$/); if(!m) return null; const a=+m[1], b=+m[3], op=m[2]; const lo=Math.min(a,b), hi=Math.max(a,b); return `${op}:${lo},${hi}`; }
  function parsePrompt(prompt){ const m=prompt.match(/^\s*(\d+)\s*([+\u2212\u00D7\u00F7])\s*(\d+)\s*$/); return m?{a:m[1],op:m[2],b:m[3]}:null; }
  function renderEq(prompt){ const p=parsePrompt(prompt); if(!p) return; QF.setDigits(document.getElementById("num-a"), p.a); QF.setDigits(document.getElementById("num-b"), p.b); const op=document.getElementById("op"); if(op) op.textContent=p.op; }
  function insertWithin(arr,item,minAhead=3,maxAhead=5){ const pos=Math.min(arr.length, Math.floor(Math.random()*(maxAhead-minAhead+1))+minAhead); arr.splice(pos,0,item); }

  function initDrill(){
    const drill=window.DRILL; if(!drill) return;
    const ansEl=document.getElementById("answer"), formEl=document.getElementById("answer-form"), qDoneEl=document.getElementById("q-done"), timerEl=document.getElementById("timer");
    const finishActions=document.getElementById("finish-actions"), playAgainBtn=document.getElementById("play-again-btn"), againForm=document.getElementById("again-form"), nextLvlForm=document.getElementById("nextlvl-form"), homeBtn=document.getElementById("home-btn");
    const helper=document.getElementById("helper");
    const overlay=document.getElementById("overlay"), overlayContent=document.getElementById("overlay-content");

    QF.apiStats().then(s=>QF.renderStats(document.getElementById("stats-list"),s));
    QF.apiFeed().then(f=>QF.renderFeed(document.getElementById("feed-list"), f.items));

    let queue=[{prompt:drill.first.prompt, answer:drill.first.answer, tts:drill.first.tts}];
    let done=0, misses=0, running=true, start=performance.now(); let lastPrompt=null;
    let currentStart=new Date(); const qlog=[]; let lastTimer="";

    if(helper) helper.textContent = "";

    function tick(){ if(!running) return; const now=performance.now(); const t=QF.fmtTime(now-start); if(t!==lastTimer){ lastTimer=t; if(timerEl) timerEl.textContent=t; } requestAnimationFrame(tick); }
    requestAnimationFrame(tick);

    function showCurrent(){ if(!queue.length) return; renderEq(queue[0].prompt); ansEl.value=""; ansEl.focus(); currentStart=new Date(); }
    async function topUpQueue(){
      while(queue.length<6 && done+queue.length<drill.target){
        const avoid = queue.length? queue[queue.length-1].prompt : lastPrompt;
        const avoidPair = (queue.length? queue[queue.length-1].prompt : lastPrompt) ? commKey(queue.length? queue[queue.length-1].prompt : lastPrompt) : null;
        const nxt = await QF.apiNext(drill.type, avoid, avoidPair);
        if((avoid && nxt.prompt===avoid) || (avoidPair && commKey(nxt.prompt)===avoidPair)) continue;
        queue.push({prompt:nxt.prompt, answer:nxt.answer, tts:nxt.tts});
      }
    }

    async function finish(){
      running=false; QF.winSound();
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

      QF.apiStats().then(s=>QF.renderStats(document.getElementById("stats-list"),s));
      QF.apiFeed().then(f=>QF.renderFeed(document.getElementById("feed-list"), f.items));

      const gotStar = !!(pay && (pay.star || (Array.isArray(pay.awards) && pay.awards.join(" ").toLowerCase().includes("star"))));
      if(gotStar) QF.starSound();

      if(pay && pay.level_up){
        if(helper) helper.textContent = `⬆️ Level up! Next: ${pay.new_level_label}`;
        QF.levelUpSound();
        if(nextLvlForm) nextLvlForm.classList.remove("hidden");
        if(playAgainBtn) playAgainBtn.classList.add("hidden");
        if(homeBtn) homeBtn.classList.remove("hidden");
      }else{
        if(helper){
          if(gotStar){
            helper.textContent = `⭐ Star earned — Time ${QF.fmtTime(elapsed)} • Score ${correctFirstTry}/20 • ${pay?.need_hint || "Get 3 of your last 5 stars to level up."}`;
          }else{
            const msg = pay && pay.fail_msg ? pay.fail_msg : "No star this time — keep going!";
            helper.textContent = `No star this time — ${msg} • Time ${QF.fmtTime(elapsed)} • Score ${correctFirstTry}/20.`;
          }
        }
        if(nextLvlForm) nextLvlForm.classList.add("hidden");
        if(playAgainBtn) playAgainBtn.classList.remove("hidden");
        if(homeBtn) homeBtn.classList.remove("hidden");
      }
    }

    formEl.addEventListener("submit", async (e)=>{
      e.preventDefault(); unlockMediaOnce();
      if(!queue.length) return;
      const current=queue.shift();
      const val=parseInt(ansEl.value,10); if(Number.isNaN(val)) return;
      const elapsed=new Date()-currentStart;
      const parsed=parsePrompt(current.prompt) || {a:"0",b:"0",op:"?"};

      if(val===current.answer){
        QF.ding();
        qlog.push({prompt:current.prompt, a:+parsed.a, b:+parsed.b, correct_answer:current.answer, given_answer:val, correct:true, started_at:currentStart.toISOString(), elapsed_ms:elapsed});
        done+=1; document.getElementById("q-done").textContent=String(done);
        lastPrompt=current.prompt;
        if(done>=drill.target){ await finish(); return; }
        await topUpQueue(); showCurrent();
      }else{
        // track miss for first-try score
        misses += 1;

        QF.say(current.tts);
        qlog.push({prompt:current.prompt, a:+parsed.a, b:+parsed.b, correct_answer:current.answer, given_answer:val, correct:false, started_at:currentStart.toISOString(), elapsed_ms:elapsed});
        const html = `${QF.digitsToHTML(parsed.a)} <span class="op">${parsed.op}</span> ${QF.digitsToHTML(parsed.b)} = ${QF.digitsToHTML(String(current.answer))}`;
        overlayContent.innerHTML = html;
        overlay.classList.remove("hidden");
        insertWithin(queue, current, 3, 5);
        await topUpQueue();
        formEl.classList.add("disabled");
        setTimeout(()=>{ overlay.classList.add("hidden"); formEl.classList.remove("disabled"); ansEl.value=""; ansEl.focus(); }, 3000);
      }
    });

    if(playAgainBtn && againForm){
      playAgainBtn.addEventListener("click", (e)=>{ e.preventDefault(); againForm.submit(); });
    }

    renderEq(queue[0].prompt);
    topUpQueue(); ansEl.focus();
  }

  document.addEventListener("DOMContentLoaded", ()=>{ if(window.DRILL) initDrill(); });
})();
