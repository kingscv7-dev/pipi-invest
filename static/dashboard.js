const ASSET_COLORS=['#7e22ce','#e11d48','#0284c7','#16a34a','#f59e0b','#0f766e','#db2777','#4f46e5','#84cc16','#ea580c','#0891b2','#9333ea'];
function krw(v){return '₩'+Math.round(Number(v||0)).toLocaleString()}
function drawAssetPie(){
  const cv=document.getElementById('assetPie'), data=window.ASSET_DATA||[]; if(!cv||!data.length)return;
  const dpr=devicePixelRatio||1, size=Math.min(cv.parentElement.clientWidth||420,420); cv.width=size*dpr;cv.height=size*dpr;cv.style.width=size+'px';cv.style.height=size+'px';
  const c=cv.getContext('2d');c.scale(dpr,dpr);const cx=size/2,cy=size/2,r=size*.41,inner=size*.25,total=data.reduce((s,a)=>s+Number(a.krw_value||0),0);let ang=-Math.PI/2;
  c.clearRect(0,0,size,size);
  data.forEach((a,i)=>{const frac=total?Number(a.krw_value||0)/total:0,end=ang+frac*Math.PI*2;c.beginPath();c.moveTo(cx,cy);c.arc(cx,cy,r,ang,end);c.closePath();c.fillStyle=ASSET_COLORS[i%ASSET_COLORS.length];c.fill();ang=end;});
  c.beginPath();c.arc(cx,cy,inner,0,Math.PI*2);c.fillStyle='#fff';c.fill();
}
addEventListener('load',drawAssetPie);addEventListener('resize',()=>{clearTimeout(window._assetResize);window._assetResize=setTimeout(drawAssetPie,120)});
