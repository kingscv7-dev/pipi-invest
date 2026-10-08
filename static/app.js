function money(v){return '$'+Number(v||0).toLocaleString(undefined,{maximumFractionDigits:2})}
async function fetchQuoteByDate(){
  const price=document.getElementById('priceInput'), dateEl=document.getElementById('closeDateInput'), status=document.getElementById('priceStatus');
  if(!price||!dateEl||!dateEl.value)return;
  try{
    if(status)status.textContent='종가 조회중…';
    const r=await fetch('/api/quote?date='+encodeURIComponent(dateEl.value)),j=await r.json();
    if(!j.ok)throw new Error(j.error);
    price.value=j.price;
    price.readOnly=true;
    if(status)status.textContent=(j.actual_date===dateEl.value?'자동조회 완료':'휴장일 → '+j.actual_date+' 종가 사용');
  }catch(e){
    price.readOnly=false;
    if(status)status.textContent='자동조회 실패 · 수동입력';
    alert(e.message);
  }
}
function toggleManualPrice(){
  const price=document.getElementById('priceInput'), status=document.getElementById('priceStatus');
  if(!price)return;
  price.readOnly=!price.readOnly;
  if(!price.readOnly){price.focus(); if(status)status.textContent='수동입력 모드';}
  else if(status)status.textContent='자동조회 모드';
}
async function fetchQuote(){return fetchQuoteByDate()}

function validNum(v){return v!==null&&v!==undefined&&v!==''&&Number.isFinite(Number(v))}
function draw(id,labels,series){const cv=document.getElementById(id);if(!cv||!labels||!labels.length)return;const dpr=devicePixelRatio||1,W=cv.clientWidth||900,H=parseInt(cv.getAttribute('height')||300),p={l:62,r:20,t:32,b:46};cv.width=W*dpr;cv.height=H*dpr;cv.style.height=H+'px';const x=cv.getContext('2d');x.scale(dpr,dpr);let vals=[];series.forEach(s=>s.data.forEach(v=>{if(validNum(v))vals.push(Number(v))}));if(!vals.length)return;let mn=Math.min(...vals),mx=Math.max(...vals);if(mn===mx){mn-=1;mx+=1}let pad=(mx-mn)*.08;mn-=pad;mx+=pad;const X=i=>p.l+(labels.length===1?.5:i/(labels.length-1))*(W-p.l-p.r),Y=v=>p.t+(mx-v)/(mx-mn)*(H-p.t-p.b);x.clearRect(0,0,W,H);x.font='11px Arial';for(let k=0;k<=4;k++){let yy=p.t+k*(H-p.t-p.b)/4,val=mx-k*(mx-mn)/4;x.strokeStyle='#e5e7eb';x.beginPath();x.moveTo(p.l,yy);x.lineTo(W-p.r,yy);x.stroke();x.fillStyle='#667085';x.fillText(money(val),4,yy+4)}let step=Math.max(1,Math.ceil(labels.length/9));labels.forEach((l,i)=>{if(i%step===0||i===labels.length-1){x.fillStyle='#667085';x.fillText(l,X(i)-12,H-16)}});series.forEach(s=>{x.save();x.strokeStyle=s.color;x.lineWidth=s.width||2;if(s.dash)x.setLineDash(s.dash);x.beginPath();let open=false;s.data.forEach((v,i)=>{if(!validNum(v)){open=false;return}const xx=X(i),yy=Y(Number(v));if(!open){x.moveTo(xx,yy);open=true}else{x.lineTo(xx,yy)}});x.stroke();if(s.points){s.data.forEach((v,i)=>{if(!validNum(v))return;x.beginPath();x.fillStyle=s.color;x.arc(X(i),Y(Number(v)),3.2,0,Math.PI*2);x.fill()})}x.restore()});let lx=p.l;series.forEach(s=>{x.save();x.strokeStyle=s.color;x.lineWidth=s.width||2;if(s.dash)x.setLineDash(s.dash);x.beginPath();x.moveTo(lx,16);x.lineTo(lx+24,16);x.stroke();x.restore();x.fillStyle='#475467';x.fillText(s.label,lx+30,20);lx+=86});}
function render(){const c=window.VR_CHART||{};draw('valueChart',c.labels||[],[{label:'평가금',data:c.valuation||[],color:'#e11d48',width:3,points:true},{label:'최소',data:c.vmin||[],color:'#7e22ce',width:2,dash:[7,6]},{label:'최대',data:c.vmax||[],color:'#7e22ce',width:2,dash:[7,6]}]);draw('accountChart',c.actual_labels||[],[{label:'계좌총액',data:c.account||[],color:'#e11d48',width:3},{label:'투자원금',data:c.invested||[],color:'#111827',width:2,dash:[6,5]}]);}
addEventListener('load',()=>{render(); if(document.getElementById('closeDateInput')&&document.getElementById('priceInput')&&!document.getElementById('priceInput').value)fetchQuoteByDate();});addEventListener('resize',()=>{clearTimeout(window._r);window._r=setTimeout(render,120)});

function fillPlanned(weekNo, plannedDate){
  const w=document.getElementById('weekNoInput');
  const d=document.getElementById('closeDateInput');
  if(w)w.value=weekNo;
  if(d)d.value=plannedDate;
  const form=w?w.closest('form'):null;
  if(form){
    form.scrollIntoView({behavior:'smooth',block:'start'});
    setTimeout(()=>{ if(d) fetchQuoteByDate(); },250);
  }
}
