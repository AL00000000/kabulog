'use strict';
// Group the complete record history before filtering it to a chart's date range.
function groupSoxRecords(records) {
  const groups=[];
  for(const record of records){
    const last=groups.at(-1);
    if(last && (Date.parse(record.date)-Date.parse(last.at(-1).date))/86400000<7)last.push(record);
    else groups.push([record]);
  }
  return groups.flatMap(group=>{
    const decorate=(record,role)=>({...record,role,run_count:group.length,run_start:group[0].date,run_end:group.at(-1).date});
    return group.length===1?[decorate(group[0],'単独')]:[decorate(group[0],'始点'),decorate(group.at(-1),'終点')];
  });
}
function firstSoxNews(records,events,days=14){
  const byDate=new Map();
  for(const event of events){
    if(event.evidence==='価格データから算出')continue;
    // Determine the first subsequent record from the unabridged history.
    // Never reassign an event to a later endpoint when the first date is hidden.
    const record=records.find(r=>r.date>event.date&&r.date>=(event.market_date||event.date));
    if(!record)continue;
    const age=(Date.parse(record.date)-Date.parse(event.date))/86400000;
    if(age<1||age>days)continue;
    if(!byDate.has(record.date))byDate.set(record.date,[]);
    byDate.get(record.date).push({...event,days_before:age});
  }
  return byDate;
}
if(typeof module!=='undefined'){module.exports=groupSoxRecords;module.exports.firstSoxNews=firstSoxNews;}
