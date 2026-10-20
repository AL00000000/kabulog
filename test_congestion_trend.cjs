const assert=require('node:assert/strict');
const {series,connections,definitions}=require('./docs/congestion-trend.js');
const content=value=>({tables:[{title:'電話',headers:['区分','09:00'],rows:[['平日',value]]}]});
const versions={a:content('△'),b:content('◎'),closed:content('-')};
const statuses=['initial','unchanged','error','changed','unchanged','changed'];
const hashes=['a','a','a','b','closed','a'];
const observations=statuses.map((status,i)=>({at:`2026-10-${20+i}T00:00:00+09:00`,companies:{sbi:{at:`2026-10-${20+i}T00:00:00+09:00`,status,fingerprint:hashes[i]}}}));
const points=series(observations,'sbi',versions,'平日','09:00');
assert.deepEqual(points.map(p=>p.level),[2,2,null,0,null,2]);
assert.equal(points[2].reason,'取得失敗');
assert.equal(points[4].reason,'営業時間外');
assert.deepEqual(connections(points,p=>Date.parse(p.at),p=>p.level).map(c=>c.unchanged),[true]);
assert.equal(connections([points[0],points[3]],()=>0,p=>p.level)[0].unchanged,false);
assert.equal(series(observations.slice(0,1),'sbi',versions,'平日','09:00').length,1);
assert.deepEqual(connections(points.slice(0,1),()=>0,()=>0),[]); // single observation is a dot
assert.equal(series(observations,'sbi',{},'平日','09:00')[0].level,null);
assert.equal(series(observations,'sbi',versions,'土日','09:00')[0].reason,'該当する区分なし');
const rakuten=series([{at:'2026-10-20T12:00:00+09:00',companies:{rakuten:{status:'initial',fingerprint:'r'}}}],'rakuten',{r:content('約30分〜')},'平日','09:00');
assert.equal(rakuten[0].level,2);
assert.equal(definitions.rakuten.levels[2],'約30分〜');
assert.notDeepEqual(definitions.sbi.levels,definitions.rakuten.levels);
const sameDay=[{at:'2026-10-20T00:00:00+09:00',companies:{sbi:{status:'initial',fingerprint:'a'}}},{at:'2026-10-20T12:00:00+09:00',companies:{sbi:{status:'changed',fingerprint:'a'}}}];
const sameValueRevision=series(sameDay,'sbi',versions,'平日','09:00');
assert.equal(sameValueRevision.length,2);
assert.equal(sameValueRevision[1].status,'changed');
assert.equal(connections(sameValueRevision,p=>Date.parse(p.at),p=>p.level)[0].unchanged,true); // other cells changed
console.log('PASS: same-content observations, single point, changed level, failure/closed gaps, missing versions/rows, company scales');
