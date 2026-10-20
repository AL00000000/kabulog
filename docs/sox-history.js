'use strict';
const $=id=>document.getElementById(id);
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const timestamp=d=>Date.parse(d+'T00:00:00Z');
const ymd=t=>new Date(t).toISOString().slice(0,10);
const dayMs=86400000;
const number=n=>n==null?'未取得':n.toLocaleString('ja-JP',{maximumFractionDigits:2});
const pct=n=>n==null?'未確定・未取得':`${n>0?'+':''}${n.toFixed(2)}%`;
let prices,analysis,registry,research,focus=null,selectedEvent=null;
const column=()=>$('metric').value==='high'?2:1;
const category=e=>e.requested?'指定':({industry:'企業・技術',macro:'政策・マクロ',market:'市場の節目'}[e.kind]||'事象');
const color=e=>e.requested?'#ffd184':({industry:'#68d7ec',macro:'#bdabff',market:'#a6b9d0'}[e.kind]||'#a6b9d0');
function eventsVisible(){return analysis.events.filter(e=>$('eventFilter').value==='all'||($('eventFilter').value==='requested'?e.requested:e.kind===$('eventFilter').value));}
function preceding(day){return analysis.events.filter(e=>{const diff=(timestamp(day)-timestamp(e.date))/dayMs;return diff>=1 && diff<=Number($('lookback').value) && e.evidence!=='価格データから算出';});}
function displayedRecords(){const records=analysis.records[$('metric').value];return $('recordScope').value==='all'?records:$('recordScope').value==='breakouts'?analysis.breakouts[$('metric').value]:groupSoxRecords(records);}
function fillChunks(){
  const years=Number($('chunkYears').value),start=Number(prices.start.slice(0,4)),end=Number(prices.end.slice(0,4));
  $('chunk').replaceChildren();
  for(let y=start;y<=end;y+=years)$('chunk').add(new Option(`${y}〜${Math.min(y+years-1,end)}年`,String(y)));
  $('chunk').selectedIndex=$('chunk').options.length-1;
  $('chunk').add(new Option('全期間を分割表示','all'));
}
function makeChart(start,end,{overview=false}={}){
  const col=column(),rows=prices.rows.filter(r=>r[0]>=start && r[0]<=end && r[col]!=null);
  if(!rows.length)return '<p class="muted">この期間の日足はありません。</p>';
  const W=1200,left=84,right=24,baseHeight=overview?210:360;
  const log=overview||$('scale').value==='log',transform=v=>log?Math.log(v):v;
  const values=rows.map(r=>transform(r[col])),min=Math.min(...values),max=Math.max(...values),pad=(max-min||max*.05)*.08;
  const yMin=log?min-pad:Math.max(0,min-pad),yMax=max+pad;
  const from=timestamp(start),to=Math.max(timestamp(end),from+dayMs);
  const x=d=>left+(timestamp(d)-from)/(to-from)*(W-left-right);
  const ev=overview?[]:eventsVisible().filter(e=>e.plot_date>=rows[0][0] && e.plot_date<=rows.at(-1)[0]);
  const laneEnds=[],positioned=[];
  for(const e of ev.filter(e=>$('eventLabels').value==='all'||($('eventLabels').value==='requested'&&e.requested)||e.id===selectedEvent||e.id===focus)){
    const bw=Math.max(144,Math.min(340,[...e.short].reduce((n,c)=>n+(c.charCodeAt(0)>255?12:7),0)+22)),bx=Math.max(left,Math.min(W-right-bw,x(e.plot_date)-bw/2));
    let lane=laneEnds.findIndex(v=>v+10<=bx);if(lane<0)lane=laneEnds.length;
    laneEnds[lane]=bx+bw;positioned.push({e,bw,bx,lane});
  }
  const top=overview?20:34+laneEnds.length*34;
  const bottom=top+baseHeight,H=bottom+(overview?44:70);
  const y=v=>bottom-(transform(v)-yMin)/(yMax-yMin)*baseHeight;
  const path=rows.map((r,i)=>`${i?'L':'M'}${x(r[0]).toFixed(2)},${y(r[col]).toFixed(2)}`).join(' ');
  const records=displayedRecords().filter(r=>r.date>=start && r.date<=end);
  const endpoints=groupSoxRecords(analysis.records[$('metric').value]).filter(r=>r.date>=start&&r.date<=end);
  const drops=analysis.drops.filter(r=>r.date>=start&&r.date<=end);
  const dates=[...new Set([rows[0][0],...Array.from({length:5},(_,i)=>ymd(from+(to-from)*(i+1)/6)),rows.at(-1)[0]])];
  return `<svg class="${overview?'overview':'chart'}" viewBox="0 0 ${W} ${H}" role="img" aria-label="SOX ${start}から${end}、${$('metric').value==='close'?'終値':'日中高値'}。赤点は選択した表示条件に合う最高値更新。">
    ${Array.from({length:5},(_,i)=>{const value=log?Math.exp(yMin+(yMax-yMin)*i/4):yMin+(yMax-yMin)*i/4;return `<line class="tick" x1="${left}" x2="${W-right}" y1="${y(value)}" y2="${y(value)}"/><text x="${left-10}" y="${y(value)+5}" text-anchor="end">${number(value)}</text>`;}).join('')}
    ${dates.map((d,i)=>`<line class="tick" x1="${x(d)}" x2="${x(d)}" y1="${top}" y2="${bottom}"/><text x="${x(d)}" y="${bottom+28}" text-anchor="${i===0?'start':i===dates.length-1?'end':'middle'}">${overview?d.slice(0,7):d}</text>`).join('')}
    ${$('showRecords').checked?endpoints.map(r=>`<a href="#pointDetail" data-record="${r.date}">${r.role!=='終点'?`<line class="start-line" x1="${x(r.date)}" x2="${x(r.date)}" y1="${top}" y2="${bottom}"><title>${r.date} ${r.role==='単独'?'単独（始点＝終点）':'始点'}</title></line>`:''}${r.role!=='始点'?`<line class="end-line" x1="${x(r.date)+(r.role==='単独'?1:0)}" x2="${x(r.date)+(r.role==='単独'?1:0)}" y1="${top}" y2="${bottom}"><title>${r.date} 終点</title></line>`:''}</a>`).join(''):''}
    ${$('showDrops').checked?drops.map(r=>`<a href="#drop-${r.date}" data-drop="${r.date}" aria-label="${r.date} 終値前日比 ${pct(r.change_pct)}"><line class="drop-line" x1="${x(r.date)}" x2="${x(r.date)}" y1="${top}" y2="${bottom}"><title>${r.date} 終値前日比 ${pct(r.change_pct)}</title></line><rect x="${x(r.date)-4}" y="${top}" width="8" height="${baseHeight}" fill="transparent"/></a>`).join(''):''}
    <path d="${path}" fill="none" stroke="#68d7ec" stroke-width="${overview?1.4:1.8}"/>
    ${$('showRecords').checked?records.map(r=>`<a href="#pointDetail" data-record="${r.date}" aria-label="${r.date}最高値${number(r.value)}"><circle class="record ${r.role==='始点'?'record-start':''}" cx="${x(r.date)}" cy="${y(r.value)}" r="${overview?2:3.5}"><title>${r.date} / ${r.role||'更新'} / ${number(r.value)} / 前回更新から${r.gap_days}日</title></circle></a>`).join(''):''}
    ${positioned.map(({e,bw,bx,lane})=>{
      const row=rows.find(r=>r[0]===e.plot_date),py=y(row[col]),boxY=15+lane*34,mid=bx+bw/2;
      return `<a href="#evt-${e.id}" data-event="${e.id}" aria-label="${esc(e.title)}"><path d="M${mid},${boxY+25} L${x(e.plot_date)},${top-9} L${x(e.plot_date)},${py}" fill="none" stroke="${color(e)}" stroke-width=".8" opacity=".55"/><rect class="eventbox" x="${bx}" y="${boxY}" width="${bw}" height="25" rx="4"/><text class="eventtext" x="${mid}" y="${boxY+17}" text-anchor="middle">${esc(e.short)}</text><path d="M${x(e.plot_date)},${py-5} l5,5 l-5,5 l-5,-5Z" fill="${color(e)}"><title>${esc(e.date+' '+e.title+' / 対応日 '+e.plot_date)}</title></path></a>`;
    }).join('')}
    ${ev.filter(e=>!positioned.some(p=>p.e.id===e.id)).map(e=>{const row=rows.find(r=>r[0]===e.plot_date),px=x(e.plot_date),py=y(row[col]);return `<a href="#evt-${e.id}" data-event="${e.id}" aria-label="${esc(e.title)}"><path d="M${px},${py-5} l5,5 l-5,5 l-5,-5Z" fill="${color(e)}"><title>${esc(e.date+' '+e.title)}</title></path><circle cx="${px}" cy="${py}" r="9" fill="transparent"/></a>`;}).join('')}
    <text x="${W-right}" y="${H-10}" text-anchor="end">米国市場の取引日 / ${log?'対数':'通常'}軸</text></svg>`;
}
function renderCharts(){
  const years=Number($('chunkYears').value),selected=$('chunk').value;
  let ranges=[];
  if(focus){const e=analysis.events.find(e=>e.id===focus),mid=timestamp(e.plot_date||e.date);ranges=[[ymd(mid-45*dayMs),ymd(mid+45*dayMs),e.title+'：前後45日']];}
  else if(selected==='all'){
    for(let year=Number(prices.start.slice(0,4));year<=Number(prices.end.slice(0,4));year+=years)ranges.push([`${year}-01-01`,`${year+years-1}-12-31`,`${year}〜${Math.min(year+years-1,Number(prices.end.slice(0,4)))}年`]);
    ranges.reverse();
  }else{const year=Number(selected);ranges=[[`${year}-01-01`,`${year+years-1}-12-31`,`${year}〜${Math.min(year+years-1,Number(prices.end.slice(0,4)))}年`]];}
  $('charts').innerHTML=ranges.map(([a,b,title])=>{const start=a<prices.start?prices.start:a,end=b>prices.end?prices.end:b;return `<section class="chartsection"><h2>${esc(title)}</h2><p class="caption">${start}〜${end} / ${$('metric').value==='close'?'終値':'日中高値'}基準。◆を押すと名前と出典を表示、赤点を押すと直前の事象へ移動します。</p><div class="scroll">${makeChart(start,end)}</div></section>`;}).join('');
  $('overview').innerHTML=makeChart(prices.start,prices.end,{overview:true});
  $('stats').innerHTML=`<span>日足 <b>${number(prices.rows.length)}</b> 日</span><span>最高値更新 <b>${analysis.records[$('metric').value].length}</b> 回</span><span>表示対象の赤点 <b>${displayedRecords().length}</b> 個</span><span>1日5％以上下落 <b>${analysis.drops.length}</b> 日</span><span>登録事象 <b>${analysis.events.length}</b> 件</span><span>前回更新から30日以上 <b>${analysis.breakouts[$('metric').value].length}</b> 回</span>`;
  renderRecords();renderEvents();renderResearch();renderDrops();
}
function hypothesisHTML(day){
  return research.hypotheses.filter(h=>h.record_date===day).map(h=>`<div class="hypothesis"><b>${esc(h.author)}・${esc(h.status)}</b><p>${esc(h.text)}</p><details><summary>別の説明候補・検証方法</summary><p>${esc(h.counterpoint)}</p><p>${esc(h.test)}</p>${h.sources.map(s=>`<a href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.label)}</a>`).join('<br>')}</details></div>`).join('');
}
function recordRow(r,ev=[],withId=false){
  const roleClass=r.role==='始点'?'start':r.role==='終点'?'end':'';
  return `<tr ${withId?`id="record-${r.date}"`:''}><td class="date ${roleClass?'role-'+roleClass:''}"><a href="#pointDetail" data-record="${r.date}">${r.date}</a>${r.role?`<br><span class="badge ${roleClass?'badge-'+roleClass:''}">${r.role}</span>${r.run_count?`<br><span class="caption">${r.run_count}回の更新<br>${r.run_start}〜${r.run_end}</span>`:''}`:''}</td><td>${number(r.value)}</td><td>${r.gap_days}暦日</td><td class="eventlinks">${ev.length?ev.map(e=>`<a href="#evt-${e.id}" data-news-id="${e.id}">${esc(e.title)}（${e.days_before}日前）</a><span class="caption">時期の近い候補・因果未判定</span>`).join(''):'<span class="caption">新たなニュース注記なし</span>'}${hypothesisHTML(r.date)}</td></tr>`;
}
function renderRecords(){
  const news=firstSoxNews(analysis.records[$('metric').value],analysis.events,Number($('lookback').value));
  const rows=new Map(displayedRecords().map(r=>[r.date,r]));
  if($('recordScope').value==='endpoints')for(const day of news.keys())if(!rows.has(day))rows.set(day,{...analysis.records[$('metric').value].find(r=>r.date===day),role:'ニュース後初回（途中）'});
  $('breakouts').innerHTML=[...rows.values()].sort((a,b)=>b.date.localeCompare(a.date)).map(r=>recordRow(r,news.get(r.date)||[],true)).join('');
}
function renderDrops(){
  $('dropRows').innerHTML=analysis.drops.slice().reverse().map(r=>`<tr id="drop-${r.date}"><td class="drop-cell"><a href="#pointDetail" data-drop="${r.date}">${r.date}</a></td><td class="down">${pct(r.change_pct)}</td><td>${r.event_ids.length?r.event_ids.map(id=>{const e=analysis.events.find(e=>e.id===id);return `<a href="#evt-${id}">${esc(e.title)}</a><br><span class="caption">時期の近い候補。原因は未判定。</span>`;}).join('<br>'):'<span class="caption">候補未確認。出来事なしを意味しません。</span>'}</td></tr>`).join('');
}
function renderResearch(){
  const starts=groupSoxRecords(analysis.records[$('metric').value]).filter(r=>r.role!=='終点');
  const windows=starts.map(r=>{const from=ymd(timestamp(r.date)-14*dayMs),to=ymd(timestamp(r.date)-dayMs);const events=analysis.events.filter(e=>e.evidence!=='価格データから算出'&&e.date>=from&&e.date<=to);return {r,from,to,events,searched:research.searches.some(s=>s.month===r.date.slice(0,7))};});
  $('researchSummary').textContent=`${$('metric').value==='close'?'終値':'日中高値'}基準の始点 ${starts.length}日。直前14暦日に登録候補がある始点 ${windows.filter(w=>w.events.length).length}日。今回検索した対象月 ${research.searches.length}か月。`;
  $('researchRows').innerHTML=windows.slice().reverse().map(w=>`<tr><td><a href="#pointDetail" data-record="${w.r.date}">${w.r.date}</a></td><td>${w.from}〜${w.to}</td><td>${w.searched?'月単位検索・資料照合':'追加調査前'} / ${w.events.length?w.events.map((e,i)=>`<a href="#evt-${e.id}">候補${i+1}</a>`).join('・'):'今回の登録候補は未確認'}</td></tr>`).join('');
}
function renderEvents(){
  $('eventCards').innerHTML=eventsVisible().slice().reverse().map(e=>`<article class="eventcard" id="evt-${e.id}"><span class="badge" style="color:${color(e)}">${category(e)}</span><span class="caption">${e.evidence}</span><h3>${esc(e.title)}</h3><p>発表・発生日：${e.date}<br><span class="caption">チャート対応日：${e.plot_date||'収録期間外'}</span></p><p>${esc(e.note)}</p><p>対応日のSOX：<b class="${e.sox_change_pct>=0?'up':'down'}">${pct(e.sox_change_pct)}</b><br><span class="caption">直前営業日終値→対応日終値。5営業日：${pct(e.sox_5session_pct)}</span></p>${e.related_reaction?`<p>${esc(e.related_reaction.symbol)}同日：<b>${pct(e.related_reaction.change_pct)}</b><br><span class="caption">${e.related_reaction.date} / <a href="${esc(e.related_reaction.source_url)}" target="_blank" rel="noopener">個別株の日足</a></span></p>`:''}<p class="caption">${e.sources.map(s=>`<a href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.label)} ↗</a>`).join('<br>')}</p><button type="button" data-focus="${e.id}">前後45日のチャート</button></article>`).join('');
}
function showRecord(day){
  const record=analysis.records[$('metric').value].find(r=>r.date===day);if(!record)return;
  $('pointDetail').hidden=false;
  const endpoint=groupSoxRecords(analysis.records[$('metric').value]).find(r=>r.date===day)||record;
  const news=firstSoxNews(analysis.records[$('metric').value],analysis.events,Number($('lookback').value)).get(day)||[];
  $('pointDetail').innerHTML=`<h2>${day}の最高値更新</h2><p>${$('metric').value==='close'?'終値':'日中高値'} ${number(record.value)}。それ以前の最高値は${record.previous_record_date}の${number(record.previous_record)}。</p><p class="caption">直前${$('lookback').value}暦日のニュースのうち、発表後初めての高値更新に対応するものだけ表示。因果関係は未判定です。</p><div class="scroll"><table><tbody>${recordRow(endpoint,news)}</tbody></table></div>`;
  $('pointDetail').scrollIntoView({behavior:'smooth',block:'start'});
}
function focusEvent(id){focus=id;selectedEvent=id;$('jump').value=id;renderCharts();$('charts').scrollIntoView({behavior:'smooth',block:'start'});}
document.addEventListener('click',e=>{
  const drop=e.target.closest('[data-drop]');if(drop){e.preventDefault();const day=drop.dataset.drop,item=analysis.drops.find(r=>r.date===day);$('pointDetail').hidden=false;$('pointDetail').innerHTML=`<h2>${day}：SOXが1日で${pct(item.change_pct)}</h2><p>前営業日終値 ${number(item.previous_close)} → ${number(item.close)}。</p><p>${item.event_ids.length?item.event_ids.map(id=>{const e=analysis.events.find(e=>e.id===id);return `<a href="#evt-${id}">${esc(e.title)}</a>（時期の近い候補・因果未判定）`;}).join('<br>'):'関連するニュース候補は未確認。出来事なしを意味しません。'}</p>`;$('pointDetail').scrollIntoView({behavior:'smooth',block:'start'});}
  const record=e.target.closest('[data-record]');if(record){e.preventDefault();showRecord(record.dataset.record);}
  const event=e.target.closest('[data-event]');if(event){e.preventDefault();selectedEvent=event.dataset.event;renderCharts();const item=analysis.events.find(item=>item.id===selectedEvent);$('eventSelection').hidden=false;$('eventSelection').innerHTML=`<strong>${esc(item.title)}</strong>（${item.date}）<br>${esc(item.note)} <a href="#evt-${item.id}">出典と騰落を見る</a>`;}
  const target=e.target.closest('[data-focus]');if(target)focusEvent(target.dataset.focus);
});
for(const id of ['metric','scale','showRecords','showDrops','eventFilter','eventLabels','recordScope'])$(id).onchange=renderCharts;
$('chunkYears').onchange=()=>{focus=null;fillChunks();$('jump').value='';renderCharts();};
$('chunk').onchange=()=>{focus=null;$('jump').value='';renderCharts();};
$('jump').onchange=()=>{if($('jump').value)focusEvent($('jump').value);};
$('reset').onclick=()=>{focus=null;$('jump').value='';renderCharts();};
$('lookback').onchange=renderRecords;
Promise.all(['prices','analysis','events','research'].map(async name=>{const response=await fetch(`./data_sox/${name}.json`,{cache:'no-cache'});if(!response.ok)throw Error(`${name}を読み込めません`);return response.json();})).then(([p,a,r,re])=>{
  prices=p;analysis=a;registry=r;research=re;
  $('asof').textContent=`収録：${prices.start}〜${prices.end}（米国取引日） / 年表の調査日：${registry.researched_at}`;
  $('pendingItems').innerHTML=registry.pending.map(e=>`<h3>${esc(e.title)}</h3><p>${esc(e.note)}</p>`).join('');
  for(const e of analysis.events)$('jump').add(new Option(`${e.date} ${e.title}`,e.id));
  fillChunks();renderCharts();
}).catch(e=>{$('asof').textContent='データの読込に失敗しました。';$('message').textContent=e.message;});
