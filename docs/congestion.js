'use strict';
const $ = id => document.getElementById(id);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt = s => s ? new Date(s).toLocaleString('ja-JP', {timeZone:'Asia/Tokyo',hour12:false}) : '未確認';
const labels = {initial:'初回（基準点）',unchanged:'内容同一',changed:'内容変更',error:'取得失敗'};
let db;
function tableHTML(content, other) {
  if (!content) return '<p class="muted">取得済みデータなし</p>';
  return content.tables.map((t,i) => `<h3>${esc(t.title)}</h3><div class="scroll"><table><thead><tr>${t.headers.map(v=>`<th>${esc(v)}</th>`).join('')}</tr></thead><tbody>${t.rows.map((r,j)=>`<tr>${r.map((v,k)=>`<td${other && v !== other.tables?.[i]?.rows?.[j]?.[k] ? ' class="changed"' : ''}>${esc(v)}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`).join('') + `<p class="caption">${esc(content.legend)}</p><p class="caption">集計基準: ${esc(content.basis)}<br>${esc(content.note)}</p>`;
}
function companyEvents(key) {return db.observations.map(o=>o.companies[key]).filter(Boolean);}
function render() {
  $('updated').textContent = `最終観測: ${fmt(db.updated)}（日本時間） · 記録開始: ${fmt(db.observations[0]?.at)}`;
  const entries = Object.entries(db.companies);
  const ok = entries.filter(([,c])=>c.status==='ok').length;
  const changes = db.observations.reduce((n,o)=>n+Object.values(o.companies).filter(e=>e.status==='changed').length,0);
  $('stats').innerHTML = `<div class="stat">最新の取得成功<b>${ok} / ${entries.length} 社</b></div><div class="stat">観測回数<b>${db.observations.length} 回</b></div><div class="stat">内容の変更検出<b>${changes} 件</b></div>`;
  $('summary').innerHTML = entries.map(([key,c])=>{
    const times = companyEvents(key).filter(e=>e.status==='changed').map(e=>Date.parse(e.at));
    const interval = times.length>=2 ? ` / 平均${((times.at(-1)-times[0])/(times.length-1)/86400000).toFixed(1)}日間隔` : ' / 頻度未判定';
    const lm = c.resources?.map(r=>r.last_modified ? fmt(r.last_modified) : '提供なし').join(' / ') || '未取得';
    return `<tr><td><a href="${esc(c.source_url)}" target="_blank" rel="noopener">${esc(c.name)} ↗</a></td><td class="${c.status==='ok'?'ok':'error'}">${c.status==='ok'?'取得成功':'取得失敗'}</td><td>${fmt(c.last_success_at)}</td><td class="wrap">${times.length}件${interval}<br>${c.last_change_detected_at?fmt(c.last_change_detected_at):'変更の検出なし'}</td><td class="wrap">${esc(c.content?.basis || '未取得')}</td><td>${lm}</td></tr>`;
  }).join('') + [['野村證券','https://www.nomura.co.jp/support/inquiry/'],['松井証券','https://www.matsui.co.jp/support/contact/']].map(([name,url])=>`<tr><td><a href="${url}" target="_blank" rel="noopener">${name} ↗</a></td><td colspan="5" class="wrap muted">未対応: 時間帯別の詳細表の取得先を未確認。自動観測の対象外です。</td></tr>`).join('');
  $('companies').innerHTML = entries.map(([key,c])=>`<section><h2>${esc(c.name)} <span class="pill ${c.status==='ok'?'ok':'error'}">${c.status==='ok'?'最新観測で取得成功':'最新観測で取得失敗'}</span></h2><p class="caption">確認: ${fmt(c.checked_at)} / 最終成功: ${fmt(c.last_success_at)} / 現在の内容を最初に観測: ${fmt(c.content_observed_since)}</p>${c.error?`<p class="error">${esc(c.error)}${c.content?' — 以下は直近の成功データです。':' — 混雑状況は未取得です。'}</p>`:''}${tableHTML(c.content)}<p><a href="${esc(c.source_url)}" target="_blank" rel="noopener">公式案内で確認 ↗</a></p><details><summary>取得元・HTTPメタデータ</summary><div class="details caption">${(c.resources||[]).map(r=>`対象: <a href="${esc(r.url)}" target="_blank" rel="noopener">${esc(r.url)}</a><br>Last-Modified: ${esc(r.last_modified||'提供なし')}<br>ETag: ${esc(r.etag||'提供なし')}<br>Cache-Control: ${esc(r.cache_control||'提供なし')}`).join('<hr>')}</div></details></section>`).join('');
  for (const [key,c] of entries) {
    $('historyCompany').add(new Option(c.name,key));
    if (c.content) $('compareCompany').add(new Option(c.name,key));
  }
  renderHistory(); selectCompany(); initTrends();
}
const trendVersions=new Map();
function loadTrendVersion(company, fingerprint) {
  const key=company+'/'+fingerprint;
  if(!trendVersions.has(key))trendVersions.set(key,fetch(`./data_congestion/versions/${key}.json`).then(r=>{
    if(!r.ok)throw Error('HTTP '+r.status);return r.json();
  }).catch(()=>{trendVersions.delete(key);return null;}));
  return trendVersions.get(key);
}
function initTrends() {
  $('trendCharts').innerHTML=Object.entries(CongestionTrend.definitions).map(([key,def])=>{
    const table=db.companies[key]?.content?.tables.find(t=>t.title==='電話');
    const days=[...new Set(table?.rows.map(r=>r[0]) || [])];
    const hours=table?.headers.filter(h=>/^\d{2}:\d{2}/.test(h)) || [];
    return `<div class="trend-controls" id="trend-${key}"><h3>${def.name}</h3><label>曜日区分 <select id="trendDay-${key}" aria-label="${def.name}の曜日区分">${days.map(d=>`<option>${esc(d)}</option>`).join('')}</select></label><label>時間帯 <select id="trendHour-${key}" aria-label="${def.name}の時間帯">${hours.map(h=>`<option${h==='09:00'?' selected':''}>${esc(h)}</option>`).join('')}</select></label><div id="trendPlot-${key}"></div></div>`;
  }).join('<hr style="border:0;border-top:1px solid var(--line);margin:24px 0">');
  for(const key of Object.keys(CongestionTrend.definitions)) {
    $('trendDay-'+key).onchange=$('trendHour-'+key).onchange=renderTrends;
  }
  $('trendRange').onchange=renderTrends;
  renderTrends();
}
let trendGeneration=0;
async function renderTrends() {
  const generation=++trendGeneration;
  const all=db.observations.slice().sort((a,b)=>Date.parse(a.at)-Date.parse(b.at));
  const range=$('trendRange').value;
  const cutoff=range==='all'?-Infinity:Date.now()-Number(range)*86400000;
  const observations=all.filter(o=>Date.parse(o.at)>=cutoff);
  const times=observations.map(o=>Date.parse(o.at));
  const min=times.length?Math.min(...times):0,max=times.length?Math.max(...times):0;
  const pad=Math.max((max-min)*.035,1000);
  const domain=min===max?[min-60000,max+60000]:[min-pad,max+pad];
  await Promise.all(Object.keys(CongestionTrend.definitions).map(async key=>{
    const hashes=[...new Set(observations.map(o=>o.companies[key]).filter(e=>e && e.status!=='error' && e.fingerprint).map(e=>e.fingerprint))];
    const versions=Object.fromEntries(await Promise.all(hashes.map(async h=>[h,await loadTrendVersion(key,h)])));
    if(generation!==trendGeneration)return;
    const day=$('trendDay-'+key).value,hour=$('trendHour-'+key).value;
    const points=CongestionTrend.series(observations,key,versions,day,hour);
    drawTrend(key,points,domain,day,hour);
  }));
}
function drawTrend(key,points,domain,day,hour) {
  const def=CongestionTrend.definitions[key],width=1000,height=310,left=150,right=26,top=32,bottom=192,gapY=233;
  if(!points.length){$('trendPlot-'+key).innerHTML='<p class="muted">選択期間の記録がありません。</p>';return;}
  const x=p=>left+((typeof p.at==='number'?p.at:Date.parse(p.at))-domain[0])/(domain[1]-domain[0])*(width-left-right);
  const y=p=>bottom-p.level/(def.levels.length-1)*(bottom-top);
  const valid=points.filter(p=>p.level!==null),missing=points.filter(p=>p.level===null && p.reason!=='営業時間外');
  const days=new Set(points.map(p=>new Date(p.at).toLocaleDateString('ja-JP',{timeZone:'Asia/Tokyo'})));
  const early=valid.length<2 || days.size<2;
  const status=`${early?'履歴蓄積中 · ':''}${valid.length}観測点 / 欠測${missing.length}件 / 営業時間外${points.length-valid.length-missing.length}件`;
  const tickTimes=points.length<=4?points.map(p=>Date.parse(p.at)):[0,1,2,3].map(i=>domain[0]+(domain[1]-domain[0])*i/3);
  const dateLabel=t=>new Date(t).toLocaleString('ja-JP',{timeZone:'Asia/Tokyo',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:days.size===1?'2-digit':undefined,hour12:false});
  const svg=`<svg class="trend-chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="${def.name} ${esc(day)} ${esc(hour)}の公表混雑区分の推移。${status}">
    ${def.levels.map((label,i)=>`<line class="guideline" x1="${left}" x2="${width-right}" y1="${y({level:i})}" y2="${y({level:i})}"/><text x="${left-12}" y="${y({level:i})+5}" text-anchor="end">${label}</text>`).join('')}
    <text x="${left-12}" y="${gapY+5}" text-anchor="end">欠測・時間外</text>
    ${tickTimes.map(t=>`<line class="guideline" x1="${x({at:t})}" x2="${x({at:t})}" y1="${top}" y2="${gapY+8}"/><text x="${x({at:t})}" y="270" text-anchor="middle">${dateLabel(t)}</text>`).join('')}
    ${CongestionTrend.connections(points,x,y).map(line=>`<path d="${line.d}" fill="none" stroke="#6bd3ef" stroke-width="2"${line.unchanged?' stroke-dasharray="6 5"':''}/>`).join('')}
    ${points.map(p=>{
      const title=esc(`${fmt(p.at)} · ${p.reason || p.value} · ${labels[p.status] || '記録なし'}`);
      if(p.level===null) return `<text x="${x(p)}" y="${gapY+5}" text-anchor="middle" tabindex="0" class="axis-label"><title>${title}</title>${p.reason==='営業時間外'?'□':'×'}</text>`;
      if(p.status==='changed')return `<path class="revision" d="M${x(p)},${y(p)-7} l7,7 l-7,7 l-7,-7 Z" tabindex="0"><title>${title}（混雑表全体・注記の変更。選択区分の変化とは限りません）</title></path>`;
      return `<circle class="point" cx="${x(p)}" cy="${y(p)}" r="4.5" tabindex="0"><title>${title}</title></circle>`;
    }).join('')}
    <text class="axis-label" x="${left}" y="18">公表する待ち時間の目安（区分）</text><text x="${width-right}" y="300" text-anchor="end">観測日時（日本時間）</text></svg>`;
  $('trendPlot-'+key).innerHTML=`<p class="caption">${esc(day)} / ${esc(hour)} · ${status}${early?'。日付をまたぐ推移は今後の観測で表示されます。':''}</p><div class="scroll">${svg}</div><details><summary>グラフの観測値を表で確認</summary><div class="scroll"><table><thead><tr><th>観測日時（日本時間）</th><th>選択区分の掲載内容</th><th>混雑表全体の判定</th></tr></thead><tbody>${points.map(p=>`<tr><td>${fmt(p.at)}</td><td>${esc(p.reason || p.value)}</td><td>${esc(labels[p.status] || '記録なし')}</td></tr>`).join('')}</tbody></table></div></details>`;
}
function renderHistory() {
  const rows=[];
  for (const o of [...db.observations].reverse()) for (const [key,e] of Object.entries(o.companies)) {
    if ($('historyCompany').value!=='all' && $('historyCompany').value!==key) continue;
    if ($('historyType').value!=='all' && $('historyType').value!==e.status) continue;
    rows.push(`<tr><td>${fmt(e.at)}</td><td>${esc(db.companies[key].name)}</td><td class="${e.status==='error'?'error':''}">${labels[e.status]||esc(e.status)}</td><td class="wrap">${esc(e.error || (e.status==='initial'?'比較の基準点を保存':e.status==='changed'?'前回成功時から対象内容が変化': '前回成功時と対象内容が同一'))}</td></tr>`);
  }
  $('history').innerHTML=rows.join('')||'<tr><td colspan="4">該当する記録はありません</td></tr>';
  $('historyCount').textContent=`${rows.length}件。取得失敗は変更回数に含みません。`;
}
function selectCompany() {
  const events=companyEvents($('compareCompany').value).filter(e=>e.fingerprint);
  for(const id of ['before','after']) {$(id).replaceChildren();events.forEach((e,i)=>$(id).add(new Option(`${fmt(e.at)} · ${labels[e.status]}`,String(i))));}
  $('before').selectedIndex=Math.max(0,events.length-2);$('after').selectedIndex=events.length-1;
  renderComparison();
}
let compareGeneration=0;
async function renderComparison() {
  const generation=++compareGeneration;
  const key=$('compareCompany').value;
  const events=companyEvents(key).filter(e=>e.fingerprint);
  const a=events[Number($('before').value)],b=events[Number($('after').value)];
  if(!a||!b)return;
  try {
    const contents=await Promise.all([a,b].map(async e=>{
      const r=await fetch(`./data_congestion/versions/${key}/${e.fingerprint}.json`);
      if(!r.ok)throw Error('保存内容を読み込めません');return r.json();
    }));
    if(generation!==compareGeneration)return;
    $('comparisonNote').textContent=a.fingerprint===b.fingerprint?'選択した2時点の内容は同一です。初回のみの場合は同じ基準点を表示します。':'選択した2時点の内容が異なります。集計基準・注記だけの変化では、表のセルに差が出ない場合があります。';
    $('beforeContent').innerHTML=tableHTML(contents[0],contents[1]);$('afterContent').innerHTML=tableHTML(contents[1],contents[0]);
  }catch(e){$('comparisonNote').textContent=e.message;}
}
$('compareCompany').onchange=selectCompany;
$('before').onchange=$('after').onchange=renderComparison;
$('historyCompany').onchange=$('historyType').onchange=renderHistory;
fetch('./data_congestion/data.json',{cache:'no-cache'}).then(r=>{if(!r.ok)throw Error(`HTTP ${r.status}`);return r.json();}).then(d=>{db=d;render();}).catch(e=>{$('updated').textContent=`データを読み込めません: ${e.message}`;});
