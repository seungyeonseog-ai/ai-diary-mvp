import {node,closeButton} from './ui.js?v=20261104-ui2';
let detail=null;
export function closeDetail(){if(detail){detail.close();detail.remove();detail=null;}}
export function showDetail(day,valid=()=>true){
 if(!valid())return;closeDetail();
 const dialog=node('dialog','weekly-detail');detail=dialog;dialog.setAttribute('aria-labelledby','weekly-detail-title');
 const header=node('header','weekly-detail-header'),title=node('h2','','일일 감정 분석');title.id='weekly-detail-title';
 const close=closeButton(dialog,'일일 감정 분석 닫기');header.append(title,close);
 const body=node('div','weekly-detail-content'),date=new Date(day.date_str+'T12:00:00');
 body.append(node('div','weekly-detail-date',`${date.getFullYear()}년 ${date.getMonth()+1}월 ${date.getDate()}일 (${'일월화수목금토'[date.getDay()]})`));
 const section=label=>{const el=node('section','weekly-detail-section');el.append(node('h3','',label));body.append(el);return el;};
 const emotions=section('감정'),chips=node('div','weekly-detail-emotions');
 for(const [i,name]of (day.emotions||[]).entries()){const score=day.scores[i];chips.append(node('span','weekly-detail-chip',`${name} (${score>=0?'+':''}${score.toFixed(1)})`));}emotions.append(chips);
 const keywords=section('키워드');for(const [i,word]of (day.keywords||[]).entries()){const item=node('div','weekly-detail-keyword');item.append(node('h4','',word),node('p','',day.keyword_descriptions?.[i]||''));keywords.append(item);}
 section('하루').append(node('p','',day.summary||''));dialog.append(header,body);document.body.append(dialog);
 dialog.addEventListener('click',event=>{if(event.target===dialog){const r=dialog.getBoundingClientRect();if(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom)dialog.close();}});
 dialog.addEventListener('close',()=>{dialog.remove();if(detail===dialog)detail=null;},{once:true});dialog.showModal();
}
// Shape-preserving cubic interpolation: flat peaks remain flat and no invented extrema appear.
export function curvePath(points){
 if(!points.length)return '';if(points.length===1)return `M ${points[0].x} ${points[0].y}`;
 const slopes=points.slice(1).map((p,i)=>(p.y-points[i].y)/(p.x-points[i].x));
 const tangents=points.map((p,i)=>i===0?slopes[0]:i===points.length-1?slopes.at(-1):slopes[i-1]*slopes[i]<=0?0:2/(1/slopes[i-1]+1/slopes[i]));
 return points.slice(1).reduce((path,p,i)=>{const prev=points[i],dx=(p.x-prev.x)/3;return path+` C ${prev.x+dx} ${prev.y+tangents[i]*dx}, ${p.x-dx} ${p.y-tangents[i+1]*dx}, ${p.x} ${p.y}`;},`M ${points[0].x} ${points[0].y}`);
}
export function chart(points,days,valid){
 const ns='http://www.w3.org/2000/svg',svg=document.createElementNS(ns,'svg');svg.setAttribute('viewBox','0 0 720 340');svg.setAttribute('role','group');svg.setAttribute('aria-label','분석된 날짜별 감정 흐름');
 const add=(tag,attrs,text)=>{const el=document.createElementNS(ns,tag);for(const [key,value]of Object.entries(attrs))el.setAttribute(key,value);if(text!==undefined)el.textContent=text;svg.append(el);return el;};
 const extent=Math.max(1,...points.map(p=>Math.abs(p.value))),y=value=>155-value/extent*115;
 for(const value of [-extent,-extent/2,0,extent/2,extent]){add('line',{x1:55,y1:y(value),x2:680,y2:y(value),class:'weekly-grid'});add('text',{x:10,y:y(value)+5,class:'weekly-axis'},value.toFixed(1));}
 const positions=points.map((p,i)=>({x:points.length===1?365:65+i*605/(points.length-1),y:y(p.value)})),path=curvePath(positions);
 add('path',{d:path+` L ${positions.at(-1).x} ${y(0)} L ${positions[0].x} ${y(0)} Z`,class:'weekly-area'});add('path',{d:path,class:'weekly-line'});
 positions.forEach((p,i)=>{
  const point=points[i],label=`${point.date} 감정 점수 ${point.value>=0?'+':''}${point.value.toFixed(1)}, 일일 감정 분석 열기`;
  const target=add('g',{role:'button',tabindex:0,'aria-label':label,class:'weekly-point'}),hit=document.createElementNS(ns,'circle');hit.setAttribute('cx',p.x);hit.setAttribute('cy',p.y);hit.setAttribute('r',18);hit.setAttribute('fill','transparent');target.append(hit);
  const circle=document.createElementNS(ns,'circle');for(const [k,v]of Object.entries({cx:p.x,cy:p.y,r:6,class:'weekly-dot'}))circle.setAttribute(k,v);target.append(circle);
  const tooltip=document.createElementNS(ns,'title');tooltip.textContent=label;target.append(tooltip);
  const open=()=>showDetail(days.find(d=>d.date_str===point.date),valid);target.addEventListener('click',open);target.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();open();}});
  add('text',{x:p.x,y:315,'text-anchor':'middle',class:'weekly-axis'},point.date.slice(5).replace('-','/'));
 });return svg;
}
