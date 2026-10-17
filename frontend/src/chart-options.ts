import type { EChartsCoreOption } from 'echarts/core'
import type { KronosPrediction } from './types'

// at identifies the bar OPEN; the predicted value is its CLOSE. Display only.
export function forecastCloseAt(p:KronosPrediction, at:string):number|null {
  const match=/^(\d+)(m|h|d)$/i.exec(p.timeframe ?? '')
  if(!match)return null
  const step=Number(match[1])*({m:60_000,h:3_600_000,d:86_400_000}[match[2]!.toLowerCase()] ?? 0)
  const open=Date.parse(at)
  return step>0&&Number.isFinite(open)?open+step:null
}
export function visibleForecast(p:KronosPrediction,now:number){
  return p.quantiles.flatMap(q=>{const closeAt=forecastCloseAt(p,q.at);return closeAt!==null&&closeAt>now?[{...q,closeAt}]:[]})
}
export function kronosOptions(p: KronosPrediction, now: number, dark=false): EChartsCoreOption {
  const muted=dark?'#9cbab4':'#52657c';const grid=dark?'#24443e':'#dbe5eb'
  const real=p.historical.map(b=>[Date.parse(b.at),b.open,b.close,b.low,b.high])
  const forecast=visibleForecast(p,now);const first=p.quantiles[0]?Date.parse(p.quantiles[0].at):undefined;const last=forecast.at(-1)?.closeAt
  const markers: {name:string;xAxis:number;lineStyle?:{color:string;type:'dashed'|'solid'};label?:{show:boolean}}[]=[]
  if(first!=null)markers.push({name:'FORECAST START · UTC',xAxis:first,label:{show:false},lineStyle:{color:'#0891b2',type:'dashed'}})
  markers.push({name:'NOW · UTC',xAxis:now,lineStyle:{color:muted,type:'solid'}})
  return {
    animation:false,aria:{enabled:true,label:{description:'Velas reales y forecast Kronos separados'}},color:['#0891b2','#059669'],
    grid:{top:42,right:74,left:12,bottom:58},
    tooltip:{trigger:'axis',renderMode:'richText',confine:true,axisPointer:{type:'cross'},formatter:(items:unknown)=>{
      if(!Array.isArray(items))return ''
      const lines:string[]=[]
      for(const item of items as {seriesName?:string;value?:number[]}[]){
        const v=item.value;if(!v||!Number.isFinite(v[0]))continue
        if(!lines.length)lines.push(new Date(v[0]!).toISOString())
        if(item.seriesName==='REAL MARKET')lines.push(`REAL MARKET · apertura UTC\nO ${v[1]?.toFixed(5)} · H ${v[4]?.toFixed(5)}\nL ${v[3]?.toFixed(5)} · C ${v[2]?.toFixed(5)}`)
        else if(item.seriesName==='KRONOS FORECAST'&&v[1]!=null){
          const q=forecast.find(q=>q.closeAt===v[0])
          lines.push(`KRONOS FORECAST · cierre UTC\nMediana ${v[1].toFixed(5)} USD/EUR\nApertura original ${q?.at ?? 'UNKNOWN'}\nP05 ${q?.p05.toFixed(5)} · P95 ${q?.p95.toFixed(5)}\nDispersión del modelo; no confianza calibrada`)
        }
        else if(item.seriesName==='P05'&&v[1]!=null)lines.push(`P05 ${v[1].toFixed(5)}`)
        else if(item.seriesName==='P95'&&v[1]!=null)lines.push(`P95 ${v[1].toFixed(5)}`)
      }return lines.join('\n')
    }},
    xAxis:{type:'time',max:Math.max(last ?? now,now),axisLine:{show:false},axisTick:{show:false},axisLabel:{color:muted,hideOverlap:true,formatter:(v:number)=>new Date(v).toISOString().slice(5,16).replace('T',' ')},splitLine:{show:false}},
    yAxis:{type:'value',position:'right',scale:true,axisLabel:{color:muted,formatter:(v:number)=>v.toFixed(5)},splitLine:{lineStyle:{color:grid}},name:'USD/EUR',nameTextStyle:{color:muted}},
    dataZoom:[{type:'inside',filterMode:'none'},{type:'slider',height:16,bottom:8,borderColor:grid,fillerColor:'rgba(6,182,212,.08)',showDetail:false}],
    series:[
      {name:'REAL MARKET',type:'candlestick',data:real,encode:{x:0,y:[1,2,3,4]},itemStyle:{color:'#059669',color0:dark?'#0b2421':'#ffffff',borderColor:'#059669',borderColor0:'#64748b'},barMaxWidth:9},
      {name:'P05',type:'line',stack:'band',data:forecast.map(b=>[b.closeAt,b.p05]),lineStyle:{opacity:0},symbol:'none',silent:true},
      {name:'Banda 5–95%',type:'line',stack:'band',data:forecast.map(b=>[b.closeAt,b.p95-b.p05]),lineStyle:{opacity:0},areaStyle:{color:'#06b6d4',opacity:.16},symbol:'none',silent:true,tooltip:{show:false}},
      {name:'P95',type:'line',data:forecast.map(b=>[b.closeAt,b.p95]),lineStyle:{opacity:0},symbol:'none',silent:true},
      {id:'forecast',name:'KRONOS FORECAST',type:'line',data:forecast.map(b=>[b.closeAt,b.median]),lineStyle:{type:'dashed',width:2.5,color:dark?'#67e8f9':'#0e7490'},symbol:'none',connectNulls:false,
        markLine:{symbol:'none',silent:true,data:markers,label:{formatter:'{b}',fontSize:9,color:muted,position:'insideEndTop'}},
        markArea:{silent:true,label:{color:muted,fontSize:9,position:'insideTop'},data:[
          ...(real[0]?[[{name:'REAL MARKET',xAxis:real[0][0],itemStyle:{color:'rgba(16,185,129,.025)'}},{xAxis:now}]]:[]),
          ...(last&&last>now?[[{name:'KRONOS FORECAST',xAxis:now,itemStyle:{color:'rgba(6,182,212,.05)'}},{xAxis:last}]]:[])
        ]}},
    ],
  }
}
