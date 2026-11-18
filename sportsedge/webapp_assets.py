"""HTML / CSS / JS for the StriklyPix page. Kept apart from the Python so each is readable."""

HTML = r"""<!doctype html><html lang=en><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name=robots content="noindex,nofollow"><title>StriklyPix {{SPORT}}</title>
<style>{{CSS}}</style></head><body>
<header><div class=top><a class=logo href="#home">Strikly<span>Pix</span></a>
<div class=sw>{{SWITCH}}</div>
<div class=srch><input id=q type=search autocomplete=off placeholder="Search players or teams"><div id=sres></div></div></div>
<nav class=tabs><a data-r=home href="#home">Home</a><a data-r=trends href="#trends">Trends</a><a data-r=matchups href="#matchups">Matchups</a></nav></header>
<main id=app></main>
<div id=sheet aria-hidden=true><div class=sbg></div><div class=sbody role=dialog aria-modal=true><button class=x aria-label=Close>&times;</button><div id=sc></div></div></div>
<button id=slipbtn hidden>Parlay <b id=slipn>0</b></button>
<div id=slip aria-hidden=true><div class=sbg></div><div class=slipbody><button class=x aria-label=Close>&times;</button><div id=slipc></div></div></div>
<div id=tip></div>
<script>const D={{DATA}};</script><script>{{JS}}</script></body></html>"""

CSS = r"""
:root{--bg:#f4f5f7;--card:#fff;--ink:#0f172a;--ink2:#334155;--mut:#64748b;--line:#e5e7eb;--soft:#f1f5f9;
--hit:#16a34a;--hitbg:#dcfce7;--miss:#e11d48;--missbg:#ffe4e6;--gold:#b45309;--goldbg:#fef3c7;--blue:#1d4ed8;--bluebg:#eff6ff;
--grid:#e2e8f0;--bar-miss:#fda4af;--bar-hit:#22c55e}
*{box-sizing:border-box}html{-webkit-text-size-adjust:100%}
body{margin:0;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;background:var(--bg);color:var(--ink);font-size:14px;line-height:1.4}
a{color:inherit}button{font:inherit;color:inherit;cursor:pointer}
header{background:#0f172a;color:#fff;position:sticky;top:0;z-index:20}
.top{max-width:1240px;margin:0 auto;display:flex;align-items:center;gap:12px;padding:12px 16px 6px;flex-wrap:wrap}
.logo{font-weight:800;font-size:21px;text-decoration:none;letter-spacing:-.3px}.logo span{color:#22c55e}
.sw{display:flex;background:#1e293b;border-radius:10px;padding:3px}.sw a{text-decoration:none;font-weight:700;font-size:13px;color:#94a3b8;padding:6px 14px;border-radius:8px}
.sw a.on{background:#fff;color:#0f172a}
.srch{position:relative;margin-left:auto;flex:1;max-width:340px;min-width:180px}
#q{width:100%;border:0;border-radius:10px;padding:9px 12px;font-size:14px;background:#1e293b;color:#fff;outline:none}#q::placeholder{color:#94a3b8}
#sres{position:absolute;top:42px;left:0;right:0;background:#fff;color:var(--ink);border-radius:10px;box-shadow:0 12px 30px rgba(0,0,0,.25);overflow:hidden;display:none;max-height:60vh;overflow-y:auto}
#sres a{display:flex;justify-content:space-between;padding:10px 12px;text-decoration:none;border-bottom:1px solid var(--line)}#sres a:hover{background:var(--soft)}
#sres small{color:var(--mut)}
.tabs{max-width:1240px;margin:0 auto;display:flex;gap:4px;padding:0 10px}
.tabs a{text-decoration:none;color:#94a3b8;font-weight:650;padding:10px 12px;border-bottom:3px solid transparent}
.tabs a.on{color:#fff;border-color:#22c55e}
main{max-width:1240px;margin:0 auto;padding:16px 16px 90px}
h2{font-size:17px;margin:20px 0 10px;display:flex;align-items:center;gap:8px}h2 small{font-weight:500;color:var(--mut);font-size:12.5px}
.meta{color:var(--mut);font-size:12.5px;margin-bottom:6px}
.note{background:var(--goldbg);color:var(--gold);padding:8px 12px;border-radius:10px;font-size:13px;margin:8px 0}
.seg{display:inline-flex;background:#e2e8f0;border-radius:10px;padding:3px;gap:2px;max-width:100%;overflow-x:auto;scrollbar-width:none}.seg button{white-space:nowrap}
.seg button{border:0;background:transparent;padding:6px 12px;border-radius:8px;font-weight:650;font-size:13px;color:var(--ink2)}
.seg button.on{background:#fff;box-shadow:0 1px 2px rgba(0,0,0,.08);color:var(--ink)}
.hh{display:flex;gap:10px;overflow-x:auto;padding:2px 2px 8px;scroll-snap-type:x mandatory}
.hc{flex:0 0 220px;scroll-snap-align:start;background:var(--card);border:1px solid var(--line);border-radius:14px;padding:12px;cursor:pointer;display:flex;flex-direction:column;gap:6px}
.hc:hover{border-color:#94a3b8}.hc .nm{font-weight:750;font-size:14.5px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.hc .pk{color:var(--ink2);font-size:13px}.hc .big{font-size:26px;font-weight:800;letter-spacing:-.5px}.hc .big small{font-size:12px;color:var(--mut);font-weight:600;margin-left:4px}
.hc .row{display:flex;justify-content:space-between;align-items:center;font-size:12.5px;color:var(--mut)}
.spark{display:flex;gap:2px;height:18px;align-items:flex-end}.spark i{flex:1;border-radius:2px;background:var(--bar-miss)}.spark i.h{background:var(--bar-hit)}
.tag{display:inline-flex;align-items:center;gap:4px;font-size:11.5px;font-weight:750;padding:2px 8px;border-radius:999px;white-space:nowrap}
.tag.strong{background:var(--hitbg);color:#166534}.tag.trap{background:var(--goldbg);color:var(--gold)}
.tag.small{background:var(--soft);color:var(--mut)}.tag.bet{background:var(--bluebg);color:var(--blue)}
.list{background:var(--card);border:1px solid var(--line);border-radius:14px;overflow:hidden}
.it{display:flex;gap:10px;align-items:center;padding:12px 14px;border-bottom:1px solid var(--line);cursor:pointer}
.it:last-child{border-bottom:0}.it:hover{background:#fafbfc}.it.sel{background:var(--bluebg)}
.rk{flex:0 0 24px;height:24px;border-radius:999px;background:var(--ink);color:#fff;font-size:12px;font-weight:700;display:flex;align-items:center;justify-content:center}
.it .mid{flex:1;min-width:0}.it .t1{font-weight:700;display:flex;gap:6px;align-items:center;flex-wrap:wrap}
.it .t2{color:var(--mut);font-size:12.5px;margin-top:2px}.it .t3{color:var(--ink2);font-size:12.5px;margin-top:3px}
.it .rt{text-align:right;flex:0 0 auto}.odds{font-weight:750;font-variant-numeric:tabular-nums}.edge{font-size:12px;font-weight:700}
.pos{color:var(--hit)}.neg{color:var(--miss)}
.hr{font-weight:800;font-variant-numeric:tabular-nums}.hr.g{color:var(--hit)}.hr.m{color:var(--gold)}.hr.b{color:var(--miss)}
.add{border:1px solid var(--line);background:#fff;border-radius:8px;width:30px;height:30px;font-size:18px;line-height:1;flex:0 0 30px;color:var(--ink2)}
.add.on{background:var(--ink);color:#fff;border-color:var(--ink)}
.empty{padding:26px;text-align:center;color:var(--mut)}
.tiles{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:12px}
.tile{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px}.tile b{display:block;font-size:20px}.tile span{color:var(--mut);font-size:12px}
/* trends + game layout */
.split{display:grid;grid-template-columns:360px 1fr;gap:16px;align-items:start}
.side{position:sticky;top:108px;max-height:calc(100vh - 120px);display:flex;flex-direction:column;gap:10px}
.side .list{overflow-y:auto}
.bar{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.fbtn{border:1px solid var(--line);background:#fff;border-radius:10px;padding:7px 12px;font-weight:650;font-size:13px}
.fbtn.on{border-color:var(--ink);background:var(--ink);color:#fff}
.fpanel{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:12px;display:none}.fpanel.open{display:block}
.fpanel h4{margin:6px 0 6px;font-size:12px;text-transform:uppercase;letter-spacing:.5px;color:var(--mut)}
.chips{display:flex;gap:6px;flex-wrap:wrap}.chip{border:1px solid var(--line);background:#fff;border-radius:999px;padding:5px 11px;font-size:12.5px;font-weight:600;color:var(--ink2)}
.chip.on{background:var(--ink);color:#fff;border-color:var(--ink)}
.apply{margin-top:12px;width:100%;border:0;background:#22c55e;color:#04210f;font-weight:800;border-radius:10px;padding:10px}
.pane{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:16px;min-height:300px}
.games{display:grid;grid-template-columns:repeat(auto-fill,minmax(290px,1fr));gap:12px}
.gc{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:14px;cursor:pointer;text-decoration:none;display:block}
.gc:hover{border-color:#94a3b8}.gc .when{color:var(--mut);font-size:12px;display:flex;justify-content:space-between}
.tm{display:flex;align-items:center;gap:10px;margin:8px 0}.dot{width:30px;height:30px;border-radius:9px;display:flex;align-items:center;justify-content:center;color:#fff;font-weight:800;font-size:11px;flex:0 0 30px}
.tm .nm{font-weight:750;font-size:15px}.tm .rec{color:var(--mut);font-size:12.5px;margin-left:auto}
.gc .ln{display:flex;gap:12px;color:var(--ink2);font-size:12.5px;border-top:1px solid var(--line);padding-top:8px;margin-top:4px}
.ghead{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:16px;margin-bottom:12px}
.vs{display:grid;grid-template-columns:1fr auto 1fr;align-items:center;gap:10px;text-align:center}
.vs .big{font-size:20px;font-weight:800}.vs .dot{margin:0 auto 6px;width:44px;height:44px;font-size:13px;border-radius:12px}
.back{display:inline-block;margin-bottom:10px;color:var(--mut);text-decoration:none;font-weight:600}
.recs{width:100%;border-collapse:collapse;margin-top:12px;font-size:13.5px}.recs td,.recs th{padding:8px;border-bottom:1px solid var(--line);text-align:center}
.recs th{color:var(--mut);font-size:11.5px;text-transform:uppercase;letter-spacing:.4px;font-weight:650}.recs td:first-child,.recs th:first-child{text-align:left;color:var(--mut)}
.inj{font-size:12.5px;color:var(--ink2);margin-top:6px}.inj b{color:var(--miss)}
/* sheet */
#sheet,#slip{position:fixed;inset:0;z-index:50;display:none}#sheet.open,#slip.open{display:block}
.sbg{position:absolute;inset:0;background:rgba(15,23,42,.45)}
.sbody,.slipbody{position:absolute;right:0;top:0;bottom:0;width:min(640px,100%);background:var(--bg);overflow-y:auto;padding:18px 16px 40px;box-shadow:-10px 0 30px rgba(0,0,0,.2)}
.slipbody{width:min(440px,100%)}
.x{position:sticky;top:0;float:right;border:0;background:#fff;border-radius:999px;width:36px;height:36px;font-size:22px;box-shadow:0 1px 4px rgba(0,0,0,.15);z-index:2}
.ptitle{font-size:19px;font-weight:800;margin:4px 46px 4px 0}.psub{color:var(--mut);font-size:13px;margin-bottom:10px;display:flex;gap:8px;flex-wrap:wrap;align-items:center}
.verdict{border-radius:12px;padding:10px 12px;font-size:13.5px;margin:10px 0;background:var(--card);border:1px solid var(--line)}
.verdict.strong{background:var(--hitbg);border-color:#bbf7d0}.verdict.trap{background:var(--goldbg);border-color:#fde68a}
.boxes{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin:10px 0}
.bx{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:10px;text-align:center}.bx span{display:block;color:var(--mut);font-size:11.5px;font-weight:650;text-transform:uppercase;letter-spacing:.4px}
.bx b{font-size:18px}.bx small{display:block;color:var(--mut);font-size:11.5px}
.chart{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:10px 8px 4px;margin:10px 0}
.chart svg{display:block;width:100%;height:auto}.chart .ctl{display:flex;gap:6px;flex-wrap:wrap;align-items:center;padding:0 4px 8px}
.chart select{border:1px solid var(--line);border-radius:8px;padding:5px 8px;font-size:12.5px;background:#fff;max-width:220px}
.st{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--line);border-radius:14px;overflow:hidden;font-size:13px}
.st th,.st td{white-space:nowrap;padding:8px 6px;text-align:right;border-bottom:1px solid var(--line);font-variant-numeric:tabular-nums}
.st th{color:var(--mut);font-size:11px;text-transform:uppercase;font-weight:650;background:#fafbfc}.st td:first-child,.st th:first-child{text-align:left;padding-left:12px}
.st tr.hl td{font-weight:750}.scr{overflow-x:auto;border-radius:14px}
.pbtn{border:0;background:var(--ink);color:#fff;font-weight:750;border-radius:10px;padding:8px 14px}.pbtn.on{background:#22c55e;color:#04210f}
#tip{position:fixed;pointer-events:none;background:#0f172a;color:#fff;font-size:12px;padding:6px 8px;border-radius:8px;display:none;z-index:99;white-space:nowrap}
#slipbtn{position:fixed;right:16px;bottom:16px;z-index:30;border:0;background:#22c55e;color:#04210f;font-weight:800;border-radius:999px;padding:12px 18px;box-shadow:0 8px 20px rgba(0,0,0,.25)}
#slipbtn b{background:#04210f;color:#22c55e;border-radius:999px;padding:1px 8px;margin-left:6px}
.leg{display:flex;gap:8px;align-items:center;background:var(--card);border:1px solid var(--line);border-radius:12px;padding:10px;margin:6px 0}
.leg .mid{flex:1;min-width:0}.leg .rm{border:0;background:transparent;color:var(--mut);font-size:20px}
.grade{border-radius:14px;padding:14px;margin:12px 0;font-size:14px}.grade b{font-size:20px;display:block;margin-bottom:4px}
.grade.Strong{background:var(--hitbg)}.grade.Medium{background:var(--goldbg)}.grade.Weak{background:var(--missbg)}
.sum{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}
.foot{color:var(--mut);font-size:12px;margin-top:24px}
@media (max-width:900px){.split{grid-template-columns:1fr}.side{position:static;max-height:none}.pane.desk{display:none}
.tiles{grid-template-columns:repeat(2,1fr)}.srch{order:3;max-width:none;flex-basis:100%;margin:0}}
@media (min-width:901px){.mobonly{display:none}}
"""

JS = r"""
(()=>{
const $=s=>document.querySelector(s), app=$('#app');
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const amer=d=>{if(!d)return'';const a=d>=2?Math.round((d-1)*100):Math.round(-100/(d-1));return a>0?'+'+a:''+a};
const pct=x=>x==null?'':Math.round(x*100)+'%';
const sgn=x=>x==null?'':(x>=0?'+':'')+(x*100).toFixed(1)+'%';
const SI=s=>D.stats.indexOf(s)+5;
const B={};D.bets.forEach(b=>B[b.i]=b);
const G={};D.games.forEach(g=>G[g.id]=g);
const gameOf=t=>D.games.find(g=>g.home===t||g.away===t);
const teamName=(t)=>{const g=gameOf(t);if(!g)return t;const m=g.home===t?g.hm:g.am;return (m&&m.name)||t};
const teamColor=t=>{const g=gameOf(t);const m=g?(g.home===t?g.hm:g.am):null;return (m&&m.color&&m.color!=='#')?m.color:'#334155'};
const fmtTime=s=>{if(!s)return'';const d=new Date(s);return d.toLocaleString('en-US',{weekday:'short',hour:'numeric',minute:'2-digit',timeZone:'America/Toronto'})+' ET'};
const avg=a=>a.length?a.reduce((x,y)=>x+y,0)/a.length:null;
const f1=x=>x==null?'-':(Math.abs(x)<10&&x%1?x.toFixed(1):Math.round(x*10)/10);

/* ---------------- series + hit rates (same rules as the Python side) */
function teamOfBet(b){const g=G[b.g];if(!g)return null;return b.sd==='home'?g.home:b.sd==='away'?g.away:null}
function oppOf(team){const g=gameOf(team);return g?(g.home===team?g.away:g.home):null}
function isHomeToday(team){const g=gameOf(team);return g?g.home===team:null}
function series(b,opt){opt=opt||{};let out=[];
 if(b.k==='prop'){const P=D.players[b.pid];if(!P)return[];const ix=SI(b.st);
  let rows=P.g;
  if(opt.without){const T=D.players[opt.without];if(T&&T.g.length){const first=T.g[0][0];const played=new Set(T.g.filter(r=>r[3]>0).map(r=>r[0]));
   rows=rows.filter(r=>r[0]>=first&&!played.has(r[0]))}}
  out=rows.filter(r=>r[ix]!=null).map(r=>({d:r[0],o:r[1],h:r[2],cur:r[4],v:r[ix],hit:b.sd==='Over'?r[ix]>b.ln:r[ix]<b.ln}));
 }else if(b.k==='total'){const g=G[b.g];if(!g)return[];
  [g.home,g.away].forEach(t=>(D.teams[t]||[]).forEach(r=>out.push({d:r[0],o:r[1],h:r[2],cur:1,t,v:r[3]+r[4],hit:b.sd==='Over'?r[3]+r[4]>b.ln:r[3]+r[4]<b.ln})));
  out.sort((a,c)=>a.d<c.d?-1:1);
 }else{const t=teamOfBet(b);(D.teams[t]||[]).forEach(r=>{const m=r[3]-r[4];out.push({d:r[0],o:r[1],h:r[2],cur:1,t,v:m,
   hit:b.k==='ml'?m>0:m+b.ln>0})})}
 return out}
function hitsOf(s){return{k:s.filter(x=>x.hit).length,n:s.length}}
function summ(b){if(b._s)return b._s;const s=series(b);const cur=s.filter(x=>x.cur);
 let streak=0;for(let i=s.length-1;i>=0&&s[i].hit;i--)streak++;
 b._s={L5:hitsOf(s.slice(-5)),L10:hitsOf(s.slice(-10)),L20:hitsOf(s.slice(-20)),szn:hitsOf(cur),streak,n:s.length};return b._s}
const rate=h=>h&&h.n?h.k/h.n:null;
const hrCls=r=>r==null?'':r>=.7?'g':r>=.5?'m':'b';
const hrTxt=h=>h&&h.n?`${h.k}/${h.n}`:'-';

/* ---------------- wording */
const TAGS={strong:'🎯 Strong',trap:'🪤 Trap'};
function tagHtml(b){return b.tag?`<span class="tag ${b.tag}">${TAGS[b.tag]}</span>`:''}
function proof(b){const s=summ(b),h=s.L10;if(!h.n)return'';
 const t=`${h.k} of last ${h.n}`;
 if(b.k==='prop')return `${b.sd} in ${t}`+(s.streak>=3?` · ${s.streak} straight`:'');
 if(b.k==='ml')return `${teamName(teamOfBet(b))} won ${t}`;
 if(b.k==='spread')return `Would have covered ${b.ln>0?'+':''}${b.ln} in ${t}`;
 return `${b.sd} ${b.ln} in ${t} (both teams' games)`}
function title(b){if(b.k!=='prop')return b.pk;const P=D.players[b.pid];return `${P?P.n:''} ${b.sd} ${b.ln} ${D.short[b.st]||b.st}`}
function sub(b){const g=G[b.g];let x=g?`${g.away} @ ${g.home}`:'';if(b.k==='prop'){const P=D.players[b.pid];if(P&&g)x=`${P.t} vs ${P.t===g.home?g.away:g.home}`}return x}
function verdict(b){const s=summ(b),r10=rate(s.L10),need=1/b.pr;const parts=[];
 if(b.tag==='strong')parts.push(`<b>🎯 Strong.</b> We have an edge (${sgn(b.ev)}) and the trend backs it (${hrTxt(s.L10)} last 10).`);
 else if(b.tag==='trap')parts.push(`<b>🪤 Trap. Don't bet it.</b> It hit ${hrTxt(s.L10)} lately, but at ${amer(b.pr)} the price is too short. Our numbers give it ${pct(b.p)}; it needs ${pct(need)}.`);
 else if(b.fl==='CHECK NEWS')parts.push(`<b>Check the news first.</b> Our number is far from the books; usually that's an injury or lineup change we haven't caught. Not a pick until you've checked.`);
 else if(b.ev>0&&b.fl==='BET')parts.push(`<b>Value.</b> Our chance ${pct(b.p)} vs ${pct(need)} needed at ${amer(b.pr)}.`);
 else if(b.ev>0)parts.push(`<b>Small lean.</b> Slight edge (${sgn(b.ev)}), not much more.`);
 else parts.push(`<b>No edge at this price.</b> Our chance ${pct(b.p)}, it needs ${pct(need)}.`);
 if(s.szn.n&&s.szn.n<10)parts.push(`Small sample: only ${s.szn.n} games this season.`);
 if(r10!=null&&r10>=.8&&b.tag!=='strong'&&b.ev>0&&b.fl!=='CHECK NEWS')parts.push(`Hot streaks usually cool off, so we lean on the price more than the streak.`);
 return `<div class="verdict ${b.tag||''}">${parts.join(' ')}</div>`}

/* ---------------- parlay slip */
let slip=[];try{slip=JSON.parse(localStorage.getItem('sp_slip_'+D.sport+'_'+D.date)||'[]').filter(i=>B[i])}catch(e){}
function saveSlip(){try{localStorage.setItem('sp_slip_'+D.sport+'_'+D.date,JSON.stringify(slip))}catch(e){}
 $('#slipbtn').hidden=!slip.length;$('#slipn').textContent=slip.length;document.querySelectorAll('.add').forEach(a=>{const on=slip.includes(+a.dataset.i);a.classList.toggle('on',on);a.textContent=on?'✓':'+'});
 const pb=document.querySelector('.pbtn[data-i]');if(pb){const on=slip.includes(+pb.dataset.i);pb.classList.toggle('on',on);pb.textContent=on?'✓ In parlay':'+ Add to parlay'}
 if($('#slip').classList.contains('open'))renderSlip()}
function toggleSlip(i){i=+i;slip=slip.includes(i)?slip.filter(x=>x!==i):[...slip,i];saveSlip()}
function grade(legs){const p=legs.reduce((a,b)=>a*(b.p||0),1),dec=legs.reduce((a,b)=>a*b.pr,1),ev=p*dec-1;
 const traps=legs.filter(b=>b.tag==='trap'),neg=legs.filter(b=>b.ev<=0),sameGame=new Set(legs.map(b=>b.g)).size<legs.length;
 const keys=legs.map(b=>b.k==='prop'?b.pid+b.st+b.ln:b.g+b.k+b.ln);const bothSides=new Set(keys).size<keys.length;
 const worst=legs.slice().sort((a,c)=>a.ev-c.ev)[0];let g,msg;
 if(bothSides){g='Weak';msg="You bet both sides of the same line. Bold. Pointless, but bold."}
 else if(legs.length>=6){g='Weak';msg=`${legs.length} legs? That's not a parlay, that's a donation to the sportsbook.`}
 else if(traps.length){g='Weak';msg=`You took the Trap (${esc(title(traps[0]))}). The book thanks you for your business.`}
 else if(ev<-.15){g='Weak';msg=`Are you drunk? Our numbers give this ${(p*100).toFixed(1)}%, and it pays like ${(100/dec).toFixed(1)}%.`}
 else if(!neg.length&&ev>0&&legs.length<=4){g='Strong';msg=`Every leg has an edge. Still hits only ${(p*100).toFixed(0)}% of the time, so keep it small.`}
 else{g='Medium';msg=neg.length?`Not terrible, not great. Weakest leg: ${esc(title(worst))} (${sgn(worst.ev)}). Drop it and this gets better.`:`Decent legs, but ${legs.length} of them stacks the risk. Keep it small.`}
 return{g,msg,p,dec,ev,sameGame}}
function renderSlip(){const legs=slip.map(i=>B[i]).filter(Boolean);let h='<div class=ptitle>Parlay builder</div>';
 if(!legs.length){$('#slipc').innerHTML=h+'<div class=empty>Tap + on any bet to add it here.</div>';return}
 h+=legs.map(b=>`<div class=leg><div class=mid><div style="font-weight:700">${esc(title(b))} ${tagHtml(b)}</div><div class=meta>${esc(sub(b))} · ${amer(b.pr)} ${esc(b.bk)} · edge <span class="${b.ev>0?'pos':'neg'}">${sgn(b.ev)}</span></div></div><button class=rm data-rm="${b.i}" aria-label=Remove>&times;</button></div>`).join('');
 if(legs.length>=2){const r=grade(legs);
  h+=`<div class=sum><div class=bx><span>Odds</span><b>${amer(r.dec)}</b></div><div class=bx><span>Our chance</span><b>${(r.p*100).toFixed(r.p<.1?1:0)}%</b></div><div class=bx><span>Edge</span><b class="${r.ev>0?'pos':'neg'}">${sgn(r.ev)}</b></div></div>`;
  h+=`<div class="grade ${r.g}"><b>${r.g==='Strong'?'🎯 ':r.g==='Weak'?'🥴 ':''}${r.g}</b>${r.msg}</div>`;
  if(r.sameGame)h+=`<div class=note>Some legs are from the same game. Books price same-game parlays differently, so check the real payout on your app.</div>`;
  h+=`<div class=meta>Odds shown assume every leg at the listed price; your book's parlay payout may differ.</div>`}
 else h+='<div class=meta>Add one more leg to grade it.</div>';
 h+=`<p><button class=fbtn id=clr>Clear all</button></p>`;
 $('#slipc').innerHTML=h;$('#slipc').querySelectorAll('[data-rm]').forEach(x=>x.onclick=()=>toggleSlip(x.dataset.rm));$('#clr').onclick=()=>{slip=[];saveSlip()}}
$('#slipbtn').onclick=()=>{renderSlip();$('#slip').classList.add('open')};
document.querySelectorAll('#slip .sbg,#slip .x').forEach(x=>x.onclick=()=>$('#slip').classList.remove('open'));

/* ---------------- rows */
function row(b,rank){const s=summ(b),r10=rate(s.L10);
 return `<div class=it data-b="${b.i}">${rank?`<span class=rk>${rank}</span>`:''}<div class=mid><div class=t1>${esc(title(b))} ${tagHtml(b)}</div>
 <div class=t2>${esc(sub(b))} · ${esc(b.bk)}</div>${s.L10.n?`<div class=t3>${esc(proof(b))}</div>`:''}</div>
 <div class=rt><div class=odds>${amer(b.pr)}</div><div class="edge ${b.ev>0?'pos':'neg'}">${sgn(b.ev)}</div>${s.L10.n?`<div class="hr ${hrCls(r10)}" style="font-size:12px">${hrTxt(s.L10)}</div>`:''}</div>
 <button class=add data-i="${b.i}" aria-label="Add to parlay">+</button></div>`}
function wire(root){root.querySelectorAll('.it[data-b]').forEach(x=>x.onclick=e=>{if(e.target.closest('.add'))return;openBet(+x.dataset.b)});
 root.querySelectorAll('.add').forEach(a=>a.onclick=e=>{e.stopPropagation();toggleSlip(a.dataset.i)});
 root.querySelectorAll('[data-p]').forEach(x=>x.onclick=()=>openPlayer(x.dataset.p));saveSlip()}

/* ---------------- HOME */
let homeTab='best',hhTab='players';
function hotCard(b){const s=summ(b),h=s.L10,last=series(b).slice(-10);
 return `<div class=hc data-b="${b.i}"><div class=nm>${esc(b.k==='prop'?(D.players[b.pid]||{}).n:teamName(teamOfBet(b)||G[b.g]?.home))}</div>
 <div class=pk>${esc(b.k==='prop'?`${b.sd} ${b.ln} ${D.short[b.st]}`:b.pk)}</div>
 <div class=big>${h.k}/${h.n}<small>last ${h.n}${s.streak>=3?` · ${s.streak} straight`:''}</small></div>
 <div class=spark>${last.map(x=>`<i class="${x.hit?'h':''}" style="height:${x.hit?100:45}%"></i>`).join('')}</div>
 <div class=row><span>${amer(b.pr)} ${esc(b.bk)}</span><span class="edge ${b.ev>0?'pos':'neg'}">edge ${sgn(b.ev)}</span></div>
 <div class=row>${tagHtml(b)||'<span></span>'}${s.szn.n<10?'<span class="tag small">small sample</span>':''}</div></div>`}
function home(){const L={best:D.lists.best,props:D.lists.props,long:D.lists.long};
 const d=new Date(D.date+'T12:00:00');let h=`<div class=meta>${d.toLocaleDateString('en-US',{weekday:'long',month:'short',day:'numeric'})} · updated ${esc(D.updated)}${D.demo?' · DEMO DATA':''}</div>`;
 if(D.note)h+=`<div class=note>${esc(D.note)}</div>`;
 const hp=(hhTab==='players'?D.hot:D.teamHot).map(i=>B[i]).filter(Boolean);
 h+=`<h2>🔥 Hot Hands <small>runs against today's line</small></h2><div class=seg id=hhseg><button data-t=players class="${hhTab==='players'?'on':''}">Players</button><button data-t=teams class="${hhTab==='teams'?'on':''}">Teams</button></div>
 <div class=hh style="margin-top:10px">${hp.length?hp.map(hotCard).join(''):'<div class=empty>No real streaks today (we only show 8+ game samples).</div>'}</div>
 <div class=meta>🎯 Strong = edge and trend agree. 🪤 Trap = hot trend, bad price: skip it.</div>`;
 h+=`<h2>Today's picks</h2><div class=seg id=pseg>${[['best','Top 10 Bets'],['props','Top 10 Props'],['long','Long shots'],['tracker','Tracker']].map(([k,t])=>`<button data-t=${k} class="${homeTab===k?'on':''}">${t}</button>`).join('')}</div><div style="margin-top:10px" id=plist></div>`;
 app.innerHTML=h;
 const pl=$('#plist');
 if(homeTab==='tracker')pl.innerHTML=tracker();
 else{const ids=L[homeTab]||[];pl.innerHTML=ids.length?`<div class=list>${ids.map((i,n)=>B[i]?row(B[i],n+1):'').join('')}</div>`:'<div class=list><div class=empty>Nothing with value here today.</div></div>';
  if(homeTab==='long'&&ids.length)pl.innerHTML+='<div class=meta style="margin-top:6px">Long shots lose most of the time even with an edge. Small stakes only.</div>'}
 app.querySelectorAll('#hhseg button').forEach(x=>x.onclick=()=>{hhTab=x.dataset.t;home()});
 app.querySelectorAll('#pseg button').forEach(x=>x.onclick=()=>{homeTab=x.dataset.t;home()});
 app.querySelectorAll('.hc').forEach(x=>x.onclick=()=>openBet(+x.dataset.b));wire(app)}
function tracker(){const t=D.tracker;if(!t)return '<div class=list><div class=empty>Nothing tracked yet. Every Top 10 and Long shot pick is logged and graded after the game, 1 unit each.</div></div>';
 let h=`<div class=tiles><div class=tile><b>${t.w}-${t.l}${t.p?'-'+t.p:''}</b><span>Record</span></div><div class=tile><b class="${t.units>=0?'pos':'neg'}">${t.units>=0?'+':''}${t.units.toFixed(1)}u</b><span>Profit (1u per pick)</span></div><div class=tile><b>${Math.round(t.hit*100)}%</b><span>Hit rate</span></div><div class=tile><b>${t.pending}</b><span>Waiting on result</span></div></div>`;
 h+=`<div class=list>${t.rows.map(r=>`<div class=it style="cursor:default"><div class=mid><div class=t1>${esc(r[1])}</div><div class=t2>${esc(r[0])} · ${esc(r[5])} · ${amer(r[2])}</div></div><div class=rt>${r[3]==='W'?'<span class="tag strong">W</span>':r[3]==='L'?'<span class="tag" style="background:var(--missbg);color:var(--miss)">L</span>':r[3]==='P'?'<span class="tag small">Push</span>':'<span class="tag small">Pending</span>'}<div class="edge ${r[4]>0?'pos':r[4]<0?'neg':''}">${r[4]==null?'':(r[4]>0?'+':'')+r[4]+'u'}</div></div></div>`).join('')}</div>`;
 return h+'<div class=meta style="margin-top:6px">Give it a few weeks before trusting it: 50 picks can swing a lot on luck alone.</div>'}

/* ---------------- filters */
function filterUI(id,mode,state){const types=mode==='player'?[['all','All']].concat(D.stats.filter(s=>D.bets.some(b=>b.st===s)).map(s=>[s,D.short[s]])):[['all','All'],['ml','Moneyline'],['spread','Spread'],['total','Total']];
 return `<div class=fpanel id=${id}><h4>Over / Under</h4><div class=chips data-g=side>${[['all','All'],['Over','Over'],['Under','Under']].map(([k,t])=>`<button class="chip ${state.side===k?'on':''}" data-v=${k}>${t}</button>`).join('')}</div>
 <h4>Bet type</h4><div class=chips data-g=type>${types.map(([k,t])=>`<button class="chip ${state.type===k?'on':''}" data-v=${k}>${esc(t)}</button>`).join('')}</div><button class=apply>Apply</button></div>`}
function wireFilter(root,id,state,done){const p=root.querySelector('#'+id);const tmp={...state};
 p.querySelectorAll('.chips').forEach(c=>c.querySelectorAll('.chip').forEach(x=>x.onclick=()=>{c.querySelectorAll('.chip').forEach(y=>y.classList.toggle('on',y===x));tmp[c.dataset.g]=x.dataset.v}));
 p.querySelector('.apply').onclick=()=>{Object.assign(state,tmp);done()}}
function passes(b,st){if(st.side!=='all'&&b.sd!==st.side)return false;if(st.type!=='all'&&(b.k==='prop'?b.st:b.k)!==st.type)return false;return true}
const nf=st=>(st.side!=='all')+(st.type!=='all');

/* ---------------- TRENDS */
let tMode='player',tSel=null;const tF={side:'all',type:'all'};
function trendList(){let L=D.bets.filter(b=>(tMode==='player')===(b.k==='prop')&&passes(b,tF));
 L=L.map(b=>[b,summ(b)]).filter(([b,s])=>s.L10.n>=5&&rate(s.L10)>=.6);
 L.sort((a,c)=>(rate(c[1].L10)-rate(a[1].L10))||(c[1].streak-a[1].streak)||(c[0].ev-a[0].ev));
 const seen=new Set();return L.filter(([b])=>{const k=b.k==='prop'?b.pid+b.st:b.g+b.k+b.sd;if(seen.has(k))return false;seen.add(k);return true}).slice(0,150).map(x=>x[0])}
function trends(){const L=trendList();if(tSel==null||!L.some(b=>b.i===tSel))tSel=L.length?L[0].i:null;
 app.innerHTML=`<div class=split><div class=side><div class=bar><div class=seg id=tmode><button data-t=player class="${tMode==='player'?'on':''}">Player</button><button data-t=team class="${tMode==='team'?'on':''}">Team</button></div>
 <button class="fbtn ${nf(tF)?'on':''}" id=fb>Filter${nf(tF)?' · '+nf(tF):''}</button></div>${filterUI('tfp',tMode,tF)}
 <div class=meta>${L.length} trends hitting 60%+ of the last 10, best first</div><div class=list id=tl>${L.length?L.map(b=>row(b)).join(''):'<div class=empty>No trends match.</div>'}</div></div>
 <div class="pane desk" id=tpane></div></div>`;
 $('#tmode').querySelectorAll('button').forEach(x=>x.onclick=()=>{tMode=x.dataset.t;tF.type='all';tSel=null;trends()});
 $('#fb').onclick=()=>$('#tfp').classList.toggle('open');wireFilter(app,'tfp',tF,trends);wire(app);
 const sel=()=>{app.querySelectorAll('#tl .it').forEach(x=>x.classList.toggle('sel',+x.dataset.b===tSel))};
 if(innerWidth>900&&tSel!=null){autoWithout(B[tSel]);$('#tpane').innerHTML=betPanel(B[tSel]);wirePanel($('#tpane'),B[tSel]);sel()}
 app.querySelectorAll('#tl .it').forEach(x=>x.onclick=e=>{if(e.target.closest('.add'))return;tSel=+x.dataset.b;
  if(innerWidth>900){autoWithout(B[tSel]);$('#tpane').innerHTML=betPanel(B[tSel]);wirePanel($('#tpane'),B[tSel]);sel()}else openBet(tSel)})}

/* ---------------- MATCHUPS */
function rec(team){const L=D.teams[team]||[];const w=L.filter(r=>r[3]>r[4]).length;return `${w}-${L.length-w}`}
function recL(L){const w=L.filter(r=>r[3]>r[4]).length;return L.length?`${w}-${L.length-w}`:'-'}
function dot(t,cls){return `<span class="dot ${cls||''}" style="background:${esc(teamColor(t))}">${esc(t)}</span>`}
function matchups(){if(!D.games.length){app.innerHTML='<div class=empty>No games on the schedule.</div>';return}
 app.innerHTML=`<h2>Today's matchups</h2><div class=games>${D.games.map(g=>`<a class=gc href="#game/${g.id}"><div class=when><span>${fmtTime(g.start)}</span><span>${esc(g.venue||'')}</span></div>
 ${[['away',g.away,g.am],['home',g.home,g.hm]].map(([s,t,m])=>`<div class=tm>${dot(t)}<span class=nm>${esc((m&&m.name)||t)}</span><span class=rec>${esc((m&&m.rec)||rec(t))}</span>${g.proj.home!=null?`<b style="margin-left:8px;font-variant-numeric:tabular-nums">${f1(g.proj[s])}</b>`:''}</div>`).join('')}
 <div class=ln>${g.line.spread!=null?`<span>${esc(g.home)} ${g.line.spread>0?'+':''}${g.line.spread}</span>`:''}${g.line.total!=null?`<span>O/U ${g.line.total}</span>`:''}<span style="margin-left:auto">${D.bets.filter(b=>b.g===g.id&&b.ev>0&&(b.fl==='BET'||b.fl==='lean')).length} value bets</span></div></a>`).join('')}</div>
 <div class=meta style="margin-top:8px">Bold numbers are our projected score.</div>`}
let gF={side:'all',type:'all'},gMode='all';
function gamePage(id){const g=G[id];if(!g){location.hash='#matchups';return}
 const H=D.teams[g.home]||[],A=D.teams[g.away]||[];const h2h=H.filter(r=>r[1]===g.away);
 const hw=h2h.filter(r=>r[3]>r[4]).length;
 const inj=t=>{const L=(D.inj[t]||[]).filter(x=>x[2]==='out'||x[2]==='questionable');return L.length?`<div class=inj><b>${esc(t)}:</b> ${L.map(x=>`${esc(x[0])} (${esc(x[1])})`).join(', ')}</div>`:''};
 const ats=(t,L)=>{if(g.line.spread==null||!L.length)return'-';const sp=t===g.home?g.line.spread:-g.line.spread;const l=L.slice(-10);return `${l.filter(r=>r[3]-r[4]+sp>0).length}/${l.length}`};
 const ou=L=>{if(g.line.total==null||!L.length)return'-';const l=L.slice(-10);return `${l.filter(r=>r[3]+r[4]>g.line.total).length}/${l.length}`};
 const bets=D.bets.filter(b=>b.g===id&&passes(b,gF)&&(gMode==='all'||(gMode==='value'?b.ev>0&&(b.fl==='BET'||b.fl==='lean'):b.k==='prop'===(gMode==='props'))));
 bets.sort((a,c)=>(c.tag==='strong')-(a.tag==='strong')||c.ev-a.ev);
 const top=bets.filter((b,i,arr)=>arr.findIndex(x=>x.k==='prop'?x.pid===b.pid&&x.st===b.st:x.k===b.k&&x.sd===b.sd)===i).slice(0,80);
 app.innerHTML=`<a class=back href="#matchups">← All matchups</a><div class=split><div><div class=ghead>
 <div class=vs><div>${dot(g.away)}<div class=big>${esc((g.am&&g.am.name)||g.away)}</div><div class=meta>${esc((g.am&&g.am.rec)||rec(g.away))}${g.am&&g.am.road?` · ${esc(g.am.road)} road`:''}</div></div>
 <div class=meta>@</div><div>${dot(g.home)}<div class=big>${esc((g.hm&&g.hm.name)||g.home)}</div><div class=meta>${esc((g.hm&&g.hm.rec)||rec(g.home))}${g.hm&&g.hm.home?` · ${esc(g.hm.home)} home`:''}</div></div></div>
 <div class=meta style="text-align:center;margin-top:8px">${fmtTime(g.start)}${g.venue?' · '+esc(g.venue):''}${g.city?', '+esc(g.city):''}</div>
 <table class=recs><tr><th></th><th>${esc(g.away)}</th><th>${esc(g.home)}</th></tr>
 <tr><td>Season</td><td>${recL(A)}</td><td>${recL(H)}</td></tr><tr><td>Last 5</td><td>${recL(A.slice(-5))}</td><td>${recL(H.slice(-5))}</td></tr>
 <tr><td>Head to head</td><td>${h2h.length?`${h2h.length-hw}-${hw}`:'-'}</td><td>${h2h.length?`${hw}-${h2h.length-hw}`:'-'}</td></tr>
 <tr><td>Covered today's spread (L10)</td><td>${ats(g.away,A)}</td><td>${ats(g.home,H)}</td></tr><tr><td>Over today's total (L10)</td><td>${ou(A)}</td><td>${ou(H)}</td></tr>
 ${g.proj.home!=null?`<tr><td>Our projection</td><td><b>${f1(g.proj.away)}</b></td><td><b>${f1(g.proj.home)}</b></td></tr><tr><td>Win chance</td><td>${pct(1-g.proj.ph)}</td><td>${pct(g.proj.ph)}</td></tr>`:''}
 </table>${inj(g.away)}${inj(g.home)}</div></div>
 <div class=side style="top:108px"><div class=bar><div class=seg id=gm>${[['all','All'],['value','Value'],['props','Props'],['game','Game']].map(([k,t])=>`<button data-t=${k} class="${gMode===k?'on':''}">${t}</button>`).join('')}</div>
 <button class="fbtn ${nf(gF)?'on':''}" id=gfb>Filter${nf(gF)?' · '+nf(gF):''}</button></div>${filterUI('gfp','player',gF).replace('<h4>Bet type</h4>','<h4>Bet type</h4>')}
 <div class=list>${top.length?top.map(b=>row(b)).join(''):'<div class=empty>No bets match.</div>'}</div></div></div>`;
 $('#gm').querySelectorAll('button').forEach(x=>x.onclick=()=>{gMode=x.dataset.t;gamePage(id)});
 $('#gfb').onclick=()=>$('#gfp').classList.toggle('open');wireFilter(app,'gfp',gF,()=>gamePage(id));wire(app)}

/* ---------------- bet panel (trend chart) */
let pRange='L10',pWithout='';
function chart(s,b){const W=innerWidth<640?Math.max(320,Math.min(420,innerWidth-40)):600,Hh=innerWidth<640?240:230,pl=34,pr=8,pt=22,pb=34;if(!s.length)return '<div class=empty>No games to chart.</div>';
 const vals=s.map(x=>x.v);let lo=Math.min(0,...vals),hi=Math.max(...vals,b.k==='spread'?-b.ln:(b.k==='ml'?0:b.ln||0));if(hi===lo)hi=lo+1;hi+= (hi-lo)*.12;
 const y=v=>pt+(hi-v)/(hi-lo)*(Hh-pt-pb),bw=(W-pl-pr)/s.length,gap=Math.min(6,bw*.25);
 const ticks=[];const step=Math.pow(10,Math.floor(Math.log10((hi-lo)/4)));const st=[1,2,5,10].map(m=>m*step).find(m=>(hi-lo)/m<=5)||step*10;
 for(let v=Math.ceil(lo/st)*st;v<=hi;v+=st)ticks.push(v);
 let g=ticks.map(v=>`<line x1=${pl} x2=${W-pr} y1=${y(v)} y2=${y(v)} stroke="var(--grid)" stroke-width=1 /><text x=${pl-6} y=${y(v)+4} font-size=11 fill="var(--mut)" text-anchor=end>${Math.round(v*10)/10}</text>`).join('');
 const showV=s.length<=20&&bw>=22,showD=bw>=30;
 s.forEach((x,i)=>{const x0=pl+i*bw+gap/2,w=Math.max(2,bw-gap),y0=y(Math.max(0,x.v)),y1=y(Math.min(0,x.v)),hgt=Math.max(1.5,y1-y0),r=Math.min(4,w/2);
  const col=x.hit?'var(--bar-hit)':'var(--bar-miss)';const top=x.v>=0;
  const path=top?`M${x0},${y0+hgt}V${y0+r}Q${x0},${y0} ${x0+r},${y0}H${x0+w-r}Q${x0+w},${y0} ${x0+w},${y0+r}V${y0+hgt}Z`:`M${x0},${y0}V${y0+hgt-r}Q${x0},${y0+hgt} ${x0+r},${y0+hgt}H${x0+w-r}Q${x0+w},${y0+hgt} ${x0+w},${y0+hgt-r}V${y0}Z`;
  const dt=x.d.slice(5).replace('-','/');const lab=`${dt} ${x.h?'vs':'@'} ${x.o}${x.t?` (${x.t})`:''}: ${Math.round(x.v*10)/10} · ${x.hit?'Hit':'Miss'}`;
  g+=`<g class=bar data-tip="${esc(lab)}"><rect x=${pl+i*bw} y=${pt} width=${bw} height=${Hh-pt-pb} fill=transparent /><path d="${path}" fill="${col}"/>`+
   (showV?`<text x=${x0+w/2} y=${top?y0-5:y0+hgt+12} font-size=11 font-weight=700 fill="var(--ink2)" text-anchor=middle>${Math.round(x.v*10)/10}</text>`:'')+
   `<text x=${x0+w/2} y=${Hh-pb+14} font-size=10 fill="var(--mut)" text-anchor=middle>${bw>=24||i%2===0?esc(x.o):''}</text>`+
   (showD?`<text x=${x0+w/2} y=${Hh-pb+26} font-size=9 fill="var(--mut)" text-anchor=middle>${dt}</text>`:'')+`</g>`});
 const lv=b.k==='spread'?-b.ln:b.k==='ml'?0:b.ln;
 if(lv!=null){g+=`<line x1=${pl} x2=${W-pr} y1=${y(lv)} y2=${y(lv)} stroke="var(--ink)" stroke-width=2 stroke-dasharray="5 4"/><text x=${pl+4} y=${y(lv)-5} font-size=11 font-weight=700 fill="var(--ink)" paint-order=stroke stroke="#fff" stroke-width=4 stroke-linejoin=round>${b.k==='spread'?'Cover line':b.k==='ml'?'Win':'Line'} ${Math.round(lv*10)/10}</text>`}
 return `<svg viewBox="0 0 ${W} ${Hh}" role=img aria-label="Game by game results vs the line">${g}</svg>`}
function teammates(b){if(b.k!=='prop')return[];const P=D.players[b.pid];if(!P)return[];
 return Object.entries(D.players).filter(([k,p])=>k!==b.pid&&p.t===P.t).map(([k,p])=>[k,p,avg(p.g.filter(r=>r[4]).map(r=>r[3]||0))||0]).sort((a,c)=>c[2]-a[2]).slice(0,10)}
function outToday(name,team){return (D.inj[team]||[]).some(x=>x[0]===name&&x[2]==='out')}
function statTable(b,s){if(b.k==='prop'){const P=D.players[b.pid];const cols=[b.st].concat(D.stats.filter(x=>x!==b.st)).filter(st=>avg(P.g.map(r=>r[SI(st)]).filter(v=>v!=null))>0.05).slice(0,7);
  const cur=P.g.filter(r=>r[4]);const rowOf=(lab,L,cls)=>`<tr class="${cls||''}"><td>${lab}</td>${D.sport==='nba'?`<td>${f1(avg(L.map(r=>r[3])))}</td>`:''}${cols.map(c=>`<td>${f1(avg(L.map(r=>r[SI(c)]).filter(v=>v!=null)))}</td>`).join('')}</tr>`;
  return `<div class=scr><table class=st><tr><th></th>${D.sport==='nba'?'<th>MIN</th>':''}${cols.map(c=>`<th>${esc(D.short[c])}</th>`).join('')}</tr>
  ${rowOf('Last 5',P.g.slice(-5))}${rowOf('Last 10',P.g.slice(-10))}${rowOf('Season',cur.length?cur:P.g)}
  ${Object.keys(P.pj||{}).length?`<tr class=hl><td>Our projection</td>${D.sport==='nba'?'<td></td>':''}${cols.map(c=>`<td>${f1(P.pj[c])}</td>`).join('')}</tr>`:''}</table></div>`}
 const teams=b.k==='total'?[G[b.g].away,G[b.g].home]:[teamOfBet(b)];
 return `<div class=scr><table class=st><tr><th></th><th>Scored</th><th>Allowed</th><th>Total</th><th>Margin</th></tr>${teams.map(t=>{const L=D.teams[t]||[];
  const r=(lab,l)=>`<tr><td>${esc(t)} ${lab}</td><td>${f1(avg(l.map(x=>x[3])))}</td><td>${f1(avg(l.map(x=>x[4])))}</td><td>${f1(avg(l.map(x=>x[3]+x[4])))}</td><td>${f1(avg(l.map(x=>x[3]-x[4])))}</td></tr>`;
  return r('last 5',L.slice(-5))+r('season',L)}).join('')}</table></div>`}
function betPanel(b){const full=series(b,{without:pWithout});const s=summ(b);
 const team=b.k==='prop'?(D.players[b.pid]||{}).t:teamOfBet(b),opp=team?oppOf(team):null,home=team?isHomeToday(team):null;
 const all=series(b);const h2h=opp?hitsOf(all.filter(x=>x.o===opp)):{k:0,n:0};const ha=home==null?{k:0,n:0}:hitsOf(all.filter(x=>!!x.h===home).slice(-10));
 const cut={L5:5,L10:10,L20:20}[pRange];let ss=pRange==='szn'?full.filter(x=>x.cur):full.slice(-(cut||10));
 const mates=teammates(b);const P=b.k==='prop'?D.players[b.pid]:null;
 const bx=(lab,h,note)=>`<div class=bx><span>${lab}</span><b class="hr ${hrCls(rate(h))}">${h.n?Math.round(rate(h)*100)+'%':'-'}</b><small>${h.n?`${h.k} of ${h.n}`:'no games'}${note?' · '+note:''}</small></div>`;
 return `<div class=ptitle>${esc(title(b))}</div><div class=psub>${b.k==='prop'&&P?`<a href="javascript:void 0" data-p="${b.pid}" style="font-weight:650">${esc(P.n)} ›</a> · `:''}${esc(sub(b))} · <b class=odds>${amer(b.pr)}</b> ${esc(b.bk)} · edge <b class="${b.ev>0?'pos':'neg'}">${sgn(b.ev)}</b> ${tagHtml(b)}</div>
 <button class=pbtn data-i="${b.i}">+ Add to parlay</button>${verdict(b)}
 <div class=boxes>${bx('Last 5',s.L5)}${bx('Last 10',s.L10)}${bx('Last 20',s.L20)}${bx('Season',s.szn)}${bx('vs '+(opp||'opp'),h2h)}${bx(home?'Home':'Away',ha,'L10')}</div>
 <div class=chart><div class=ctl><div class=seg id=rng>${[['L5','L5'],['L10','L10'],['L20','L20'],['szn','Season']].map(([k,t])=>`<button data-t=${k} class="${pRange===k?'on':''}">${t}</button>`).join('')}</div>
 ${mates.length?`<select id=wo><option value="">With everyone</option>${mates.map(([k,p])=>`<option value="${k}" ${pWithout===k?'selected':''}>Without ${esc(p.n)}${outToday(p.n,p.t)?' (OUT today)':''}</option>`).join('')}</select>`:''}
 <span class=meta style="margin:0 0 0 auto">${pWithout?`${hrTxt(hitsOf(ss))} without ${esc(D.players[pWithout].n)}`:`${hrTxt(hitsOf(ss))} hit`}</span></div>${chart(ss,b)}</div>
 ${b.why?`<div class=meta>${esc(b.why)}</div>`:''}<h2 style="font-size:15px">Recent vs season</h2>${statTable(b,s)}`}
function wirePanel(root,b){root.querySelectorAll('#rng button').forEach(x=>x.onclick=()=>{pRange=x.dataset.t;rerender(root,b)});
 const wo=root.querySelector('#wo');if(wo)wo.onchange=()=>{pWithout=wo.value;rerender(root,b)};
 const pb=root.querySelector('.pbtn');if(pb)pb.onclick=()=>toggleSlip(pb.dataset.i);
 root.querySelectorAll('[data-p]').forEach(x=>x.onclick=()=>openPlayer(x.dataset.p));
 root.querySelectorAll('.bar[data-tip]').forEach(x=>{x.onmousemove=e=>{const t=$('#tip');t.textContent=x.dataset.tip;t.style.display='block';t.style.left=Math.min(e.clientX+12,innerWidth-200)+'px';t.style.top=(e.clientY-34)+'px'};
  x.onmouseleave=()=>$('#tip').style.display='none';x.onclick=e=>{x.onmousemove(e);setTimeout(()=>$('#tip').style.display='none',1600)}});saveSlip()}
function rerender(root,b){root.innerHTML=(root.id==='sc'?'':'')+betPanel(b);wirePanel(root,b)}
function autoWithout(b){pWithout='';if(b.k!=='prop')return;const m=teammates(b).find(([k,p])=>outToday(p.n,p.t)&&series(b,{without:k}).length>=3);if(m)pWithout=m[0]}
function openSheet(html,wireFn){$('#sc').innerHTML=html;$('#sheet').classList.add('open');$('#sheet .sbody').scrollTop=0;if(wireFn)wireFn($('#sc'))}
function openBet(i){const b=B[i];if(!b)return;autoWithout(b);openSheet(betPanel(b),r=>wirePanel(r,b))}
document.querySelectorAll('#sheet .sbg,#sheet .x').forEach(x=>x.onclick=()=>$('#sheet').classList.remove('open'));
addEventListener('keydown',e=>{if(e.key==='Escape'){$('#sheet').classList.remove('open');$('#slip').classList.remove('open')}});

/* ---------------- player page */
function openPlayer(pid){const P=D.players[pid];if(!P)return;const g=gameOf(P.t);const opp=g?(g.home===P.t?g.away:g.home):'';
 const cols=D.stats.filter(st=>avg(P.g.map(r=>r[SI(st)]).filter(v=>v!=null))>0.05).slice(0,8);const cur=P.g.filter(r=>r[4]);
 const rowOf=(lab,L)=>`<tr><td>${lab}</td>${D.sport==='nba'?`<td>${f1(avg(L.map(r=>r[3])))}</td>`:''}${cols.map(c=>`<td>${f1(avg(L.map(r=>r[SI(c)]).filter(v=>v!=null)))}</td>`).join('')}</tr>`;
 const lines=D.bets.filter(b=>b.pid===pid);const best={};lines.forEach(b=>{const k=b.st+b.ln;const s=summ(b);if(!best[k]||rate(s.L10)>rate(summ(best[k]).L10))best[k]=b});
 const L=Object.values(best).sort((a,c)=>c.ev-a.ev);
 openSheet(`<div class=ptitle>${esc(P.n)}</div><div class=psub>${esc(teamName(P.t))}${P.pos?' · '+esc(P.pos):''}${g?` · today ${P.t===g.home?'vs':'@'} ${esc(opp)} · ${fmtTime(g.start)}`:''}</div>
 <h2 style="font-size:15px">Today's lines</h2>${L.length?`<div class=list>${L.map(b=>row(b)).join('')}</div>`:'<div class="list"><div class=empty>No lines posted for this player yet.</div></div>'}
 <h2 style="font-size:15px">Recent vs season</h2><div class=scr><table class=st><tr><th></th>${D.sport==='nba'?'<th>MIN</th>':''}${cols.map(c=>`<th>${esc(D.short[c])}</th>`).join('')}</tr>
 ${rowOf('Last 5',P.g.slice(-5))}${rowOf('Last 10',P.g.slice(-10))}${rowOf('Season',cur.length?cur:P.g)}
 ${Object.keys(P.pj||{}).length?`<tr class=hl><td>Our projection</td>${D.sport==='nba'?'<td></td>':''}${cols.map(c=>`<td>${f1(P.pj[c])}</td>`).join('')}</tr>`:''}</table></div>
 <h2 style="font-size:15px">Game log</h2><div class=scr><table class=st><tr><th>Date</th><th>Opp</th>${D.sport==='nba'?'<th>MIN</th>':''}${cols.map(c=>`<th>${esc(D.short[c])}</th>`).join('')}</tr>
 ${P.g.slice(-15).reverse().map(r=>`<tr><td>${r[0].slice(5).replace('-','/')}</td><td>${r[2]?'vs':'@'} ${esc(r[1])}</td>${D.sport==='nba'?`<td>${f1(r[3])}</td>`:''}${cols.map(c=>`<td>${f1(r[SI(c)])}</td>`).join('')}</tr>`).join('')}</table></div>`,
 r=>{r.querySelectorAll('.it[data-b]').forEach(x=>x.onclick=e=>{if(e.target.closest('.add'))return;openBet(+x.dataset.b)});r.querySelectorAll('.add').forEach(a=>a.onclick=e=>{e.stopPropagation();toggleSlip(a.dataset.i)});saveSlip()})}

/* ---------------- search */
const q=$('#q'),sr=$('#sres');
q.oninput=()=>{const t=q.value.trim().toLowerCase();if(t.length<2){sr.style.display='none';return}
 const ps=Object.entries(D.players).filter(([k,p])=>p.n.toLowerCase().includes(t)).slice(0,8);
 const ts=D.games.flatMap(g=>[[g.home,g.hm],[g.away,g.am]]).filter(([a,m])=>a.toLowerCase().includes(t)||((m&&m.full)||'').toLowerCase().includes(t)).slice(0,4);
 sr.innerHTML=ts.map(([a,m])=>`<a href="#game/${gameOf(a).id}" data-close=1><span><b>${esc((m&&m.full)||a)}</b></span><small>Team · today's game</small></a>`).join('')+
  ps.map(([k,p])=>`<a href="javascript:void 0" data-pp="${k}"><span><b>${esc(p.n)}</b></span><small>${esc(p.t)}${p.pos?' · '+esc(p.pos):''}</small></a>`).join('')||'<a><small>No match today</small></a>';
 sr.style.display='block';sr.querySelectorAll('[data-pp]').forEach(x=>x.onclick=()=>{sr.style.display='none';q.value='';openPlayer(x.dataset.pp)});
 sr.querySelectorAll('[data-close]').forEach(x=>x.onclick=()=>{sr.style.display='none';q.value=''})};
document.addEventListener('click',e=>{if(!e.target.closest('.srch'))sr.style.display='none'});

/* ---------------- router */
function route(){const h=location.hash.slice(1)||'home';const [r,arg]=h.split('/');
 document.querySelectorAll('.tabs a').forEach(a=>a.classList.toggle('on',a.dataset.r===(r==='game'?'matchups':r)));
 $('#sheet').classList.remove('open');
 if(r==='trends')trends();else if(r==='matchups')matchups();else if(r==='game')gamePage(arg);else home();
 scrollTo({top:0})}
addEventListener('hashchange',route);route();
app.insertAdjacentHTML('afterend','');
document.body.insertAdjacentHTML('beforeend',`<div class=foot style="max-width:1240px;margin:0 auto;padding:0 16px 80px">Lines: DraftKings via ESPN. Edge = how much our chance beats the price. Hit rates use today's line on past games. <a href="archive/index.html">Past days</a> · Bet small, 19+ only. Need help? ConnexOntario 1-866-531-2600.</div>`);
})();
"""
