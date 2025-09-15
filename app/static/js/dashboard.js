(function(){
  function initDashboard(){
    const radios=[...document.querySelectorAll(".op-card input[type=radio]")];
    const cards=[...document.querySelectorAll(".op-card")];
    const update=()=>cards.forEach(lbl=>{ const input=lbl.querySelector("input"); lbl.classList.toggle("selected", !!(input&&input.checked)); });
    if(radios.length){ radios.forEach(r=>r.checked=false); radios[Math.floor(Math.random()*radios.length)].checked=true; update(); }
    cards.forEach(lbl=>lbl.addEventListener("click",()=>{ const input=lbl.querySelector("input"); if(!input) return; radios.forEach(r=>r.checked=false); input.checked=true; update(); }));

    QF.apiStats().then(s=>QF.renderStats(document.getElementById("stats-list"),s));
    QF.apiFeed().then(f=>QF.renderFeed(document.getElementById("feed-list"), f.items));
    QF.apiProg().then(p=>QF.renderProgressOnCards(p));

    // Lazy-load reports on open
    const repMul=document.getElementById("report-mul"), repAdd=document.getElementById("report-add"), repSub=document.getElementById("report-sub");
    document.querySelectorAll("details.expander").forEach(d=>{
      d.addEventListener("toggle", async ()=>{
        if(d.open && !d.dataset.loaded){
          d.dataset.loaded="1";
          QF.apiReportMul().then(data=>renderHeatmap(repMul,data,1,12,true));
          QF.apiReportAdd().then(data=>renderHeatmap(repAdd,data,data?.labels_from??0,data?.labels_to??20,true));
          QF.apiReportSub().then(data=>renderHeatmap(repSub,data,data?.labels_from??0,data?.labels_to??20,true));
        }
      });
    });
  }

  // Heatmap (brighter red = needs work)
  function renderHeatmap(el,data,labelStart=1,labelEnd=12,withLegend=false){
    if(!el||!data||!data.grid) return;
    const g=data.grid, from=data.labels_from??labelStart, to=data.labels_to??labelEnd;
    let header=`<div class="hm-row hm-head"><span></span>`; for(let x=from;x<=to;x++) header+=`<span>${x}</span>`; header+=`</div>`;
    let html=`<div class="hm">${header}`;
    for(let a=from;a<=to;a++){
      html+=`<div class="hm-row"><span class="hm-headcell">${a}</span>`;
      for(let b=from;b<=to;b++){
        const v=(g[a]&&g[a][b]!==undefined)?g[a][b]:null;
        let bg="rgba(255,255,255,0.06)";
        if(v!==null){ const clamped=Math.max(0,Math.min(1,v)); const alpha=0.05+clamped*0.9; bg=`rgba(255,60,60,${alpha})`; }
        html+=`<span class="hm-cell" title="${a},${b}" style="background:${bg}"></span>`;
      }
      html+=`</div>`;
    }
    html+=`</div>`;
    if(withLegend){
      html+=`<div class="news-info" style="margin-top:6px;">Legend: brighter red means that square needs more work (last 5 attempts).</div>`;
    }
    el.innerHTML=html;
  }

  document.addEventListener("DOMContentLoaded", ()=>initDashboard());
})();
