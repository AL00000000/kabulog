const assert=require('node:assert/strict');
const group=require('./docs/sox-records.js');
const rows=['2026-01-01','2026-01-02','2026-01-08','2026-01-15','2026-01-23','2026-01-24'].map(date=>({date,value:1}));
const endpoints=group(rows);
assert.deepEqual(endpoints.map(r=>[r.date,r.role,r.run_count]),[
  ['2026-01-01','始点',3],['2026-01-08','終点',3],['2026-01-15','単独',1],['2026-01-23','始点',2],['2026-01-24','終点',2]
]);
assert.deepEqual(group([]),[]);
assert.equal(rows[0].role,undefined);
// A chart boundary must not create a false start or end in the middle of a run.
assert.deepEqual(endpoints.filter(r=>r.date>='2026-01-02'&&r.date<='2026-01-07'),[]);
const analysis=require('./docs/data_sox/analysis.json');
for(const records of Object.values(analysis.records)){
  const points=group(records);
  assert.equal(points[0].date,records[0].date);
  assert.equal(points.at(-1).date,records.at(-1).date);
  assert.equal(points.filter(r=>r.role!=='終点').reduce((sum,r)=>sum+r.run_count,0),records.length);
}
console.log('SOX record grouping: boundary, endpoints, full-history checks passed');
const {firstSoxNews}=require('./docs/sox-records.js');
const news=firstSoxNews(rows,[
  {id:'one',date:'2025-12-31'},
  {id:'hidden',date:'2026-01-01'},
  {id:'later',date:'2026-01-01',market_date:'2026-01-08'},
  {id:'old',date:'2025-01-01'},
  {id:'future',date:'2027-01-01'},
  {id:'derived',date:'2026-01-01',evidence:'価格データから算出'}
]);
assert.deepEqual([...news.values()].flat().map(e=>e.id),['one','hidden','later']);
assert.deepEqual(news.get('2026-01-02').map(e=>e.id),['hidden']);
assert.equal(news.get('2026-01-08')[0].id,'later');
assert.equal(news.get('2026-01-01')[0].days_before,1);
for(const records of Object.values(analysis.records)){
  const links=[...firstSoxNews(records,analysis.events).values()].flat();
  assert.equal(new Set(links.map(e=>e.id)).size,links.length);
}
console.log('SOX news assignment: first record, hidden dates, future leakage, unique notes passed');
