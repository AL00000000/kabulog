/* Company-specific ordinal guidance levels; these are not measured minutes. */
(function(root) {
  'use strict';
  const definitions = {
    sbi: {name:'SBI証券', levels:['約5分（◎）','約10分（〇）','約20分（△）','約30分（▲）'], values:{'◎':0,'〇':1,'○':1,'△':2,'▲':3}},
    rakuten: {name:'楽天証券', levels:['約5分','約15分','約30分〜'], values:{'約5分':0,'約15分':1,'約30分〜':2}}
  };
  const closed = new Set(['-', '−', '－']);
  function series(observations, company, versions, day, hour) {
    return observations.map(o => {
      const event=o.companies[company];
      const point={at:event?.at || o.at, level:null, value:null, reason:'取得記録なし',status:event?.status};
      // Do not use an old fingerprint carried by an error event as a new value.
      if(!event || event.status==='error') return {...point,reason:event?'取得失敗':'取得記録なし'};
      const content=versions[event.fingerprint];
      if(!content) return {...point,reason:'保存内容の読込失敗'};
      const table=content.tables?.find(t=>t.title==='電話');
      const column=table?.headers.indexOf(hour) ?? -1;
      const row=table?.rows.find(r=>r[0]===day);
      if(column<0 || !row) return {...point,reason:'該当する区分なし'};
      const value=row[column];
      if(closed.has(value)) return {...point,value,reason:'営業時間外'};
      const level=definitions[company].values[value];
      if(level===undefined) return {...point,value,reason:'未対応の混雑区分'};
      return {...point,level,value,reason:null};
    }).sort((a,b)=>Date.parse(a.at)-Date.parse(b.at));
  }
  function connections(points,x,y) {
    const lines=[];
    for(let i=1;i<points.length;i++) {
      const a=points[i-1],b=points[i];
      if(a.level===null || b.level===null)continue;
      lines.push({d:`M${x(a)},${y(a)} L${x(b)},${y(b)}`,unchanged:a.level===b.level});
    }
    return lines;
  }
  const api={definitions,series,connections};
  if(typeof module!=='undefined' && module.exports)module.exports=api;
  else root.CongestionTrend=api;
})(typeof window!=='undefined'?window:globalThis);
