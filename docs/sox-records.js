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
if(typeof module!=='undefined')module.exports=groupSoxRecords;
