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

      // Hide the last problem completely and show the celebration screen
      if(document.getElementById("equation")) document.getElementById("equation").classList.add("hidden");
      formEl.classList.add("hidden");
      const cele = document.getElementById("celebrate"); if(cele) cele.classList.remove("hidden");

      QF.apiStats().then(s=>QF.renderStats(document.getElementById("stats-list"),s));
      QF.apiFeed().then(f=>QF.renderFeed(document.getElementById("feed-list"), f.items));

      const gotStar = !!(pay && (pay.star || (Array.isArray(pay.awards) && pay.awards.join(" ").toLowerCase().includes("star"))));
      if(gotStar) QF.starSound();
      // Populate celebration content
      (function(){
        const celeEmoji=document.getElementById("cele-emoji");
        const celeTitle=document.getElementById("cele-title");
        const celeSub=document.getElementById("cele-sub");
        const celeStats=document.getElementById("cele-stats");
        if(celeStats) celeStats.textContent = `Time ${QF.fmtTime(elapsed)} • Score ${correctFirstTry}/20`;
        if(gotStar){
          if(celeEmoji) celeEmoji.textContent = "⭐";
          if(celeTitle) celeTitle.textContent = "Star earned!";
          if(celeSub) celeSub.textContent = pay?.need_hint || "Great pace — can you do it again?";
        } else {
          if(celeEmoji) celeEmoji.textContent = "🎉";
          if(celeTitle) celeTitle.textContent = "Drill complete!";
          if(celeSub) celeSub.textContent = pay && pay.fail_msg ? pay.fail_msg : "Nice work — let's try for a star next round!";
        }
        // Show next-level option if levelled up
        const nextLvlForm=document.getElementById("nextlvl-form");
        const playAgainBtn=document.getElementById("play-again-btn");
        const homeBtn=document.getElementById("home-btn");
        if(pay && pay.level_up){
          if(celeTitle) celeTitle.textContent = `Level up!`;
          if(celeSub) celeSub.textContent = `Next: ${pay.new_level_label}`;
          QF.levelUpSound();
          if(nextLvlForm) nextLvlForm.classList.remove("hidden");
          if(playAgainBtn) playAgainBtn.classList.add("hidden");
        } else {
          if(nextLvlForm) nextLvlForm.classList.add("hidden");
          if(playAgainBtn) playAgainBtn.classList.remove("hidden");
        }
        if(homeBtn) homeBtn.classList.remove("hidden");
        // Render the 5-star ring for this operation
        QF.apiProg().then(p=>{
          try{
            const op = drill.type; const info = p && p[op];
            const celeStars=document.getElementById("cele-stars");
            if(celeStars && info){ celeStars.textContent = QF.starDots(info.last5); }
          }catch{}
        });
      })();

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
        // Count this attempt and decide whether to finish after the overlay
        done += 1; document.getElementById("q-done").textContent=String(done);
        // Temporarily disable input while showing the overlay
        formEl.classList.add("disabled");
        if(done>=drill.target){
          setTimeout(()=>{ overlay.classList.add("hidden"); formEl.classList.remove("disabled"); finish(); }, 3000);
          return;
        }
        // Re-queue this question a few items ahead so it comes back later
        insertWithin(queue, current, 3, 5);
        await topUpQueue();
        // Ensure the next question is rendered immediately so the UI matches the expected answer
        if(queue.length){ renderEq(queue[0].prompt); }
        // After the overlay, resume with the next question
        setTimeout(()=>{ overlay.classList.add("hidden"); formEl.classList.remove("disabled"); ansEl.value=""; ansEl.focus(); currentStart=new Date(); }, 3000);
      }
    });

    if(playAgainBtn && againForm){
      playAgainBtn.addEventListener("click", (e)=>{ e.preventDefault(); againForm.submit(); });
    }

    renderEq(queue[0].prompt);
    topUpQueue(); ansEl.focus();
  }

  document.addEventListener("DOMContentLoaded", ()=>{ 
    if(window.DRILL){ 
      initDrill(); 
      try{ const ln=document.getElementById('level-num'); if(ln){ QF.setDigits(ln, String(window.DRILL.level||ln.textContent||'')); } }catch(e){}
    }
  });
})();
