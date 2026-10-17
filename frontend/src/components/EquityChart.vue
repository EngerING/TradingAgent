<script setup lang="ts">
import { computed, onMounted, onBeforeUnmount, ref, watch } from 'vue'
import * as echarts from 'echarts/core'
import { LineChart, BarChart, ScatterChart } from 'echarts/charts'
import { TooltipComponent, GridComponent, LegendComponent, DataZoomComponent, AriaComponent, MarkLineComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import type { ECharts, EChartsCoreOption } from 'echarts/core'
import { useInterfaceStore } from '../stores/interface'
import type { ChartResponse } from '../types'
echarts.use([LineChart, BarChart, ScatterChart, TooltipComponent, GridComponent, LegendComponent, DataZoomComponent, AriaComponent, MarkLineComponent, CanvasRenderer])
const ui=useInterfaceStore()
const props = withDefaults(defineProps<{ chart: ChartResponse; height?: number; compact?: boolean; kind?: 'line' | 'bar' | 'scatter'; probabilityAxis?: boolean }>(), { height: 280, compact: false, kind: 'line', probabilityAxis: false })
const element = ref<HTMLElement>(); let instance: ECharts | undefined; let resize: ResizeObserver | undefined
const available = computed(() => props.chart.series.some(s => s.points.length > 0))
function render() {
  if (!instance) return
  const options: EChartsCoreOption = { animationDurationUpdate: 250, color: ['#059669', '#06b6d4', '#7c83db'], aria: { enabled: true },
    tooltip: { trigger: 'axis', renderMode: 'richText', formatter: (items: unknown) => {
      if (!Array.isArray(items)) return ''
      return items.map((item: { seriesName?: string; data?: { value?: [string | number, number]; note?: string } }) => `${item.seriesName ?? ''}: ${item.data?.value?.[1]?.toFixed(4) ?? ''}\n${item.data?.note ?? ''}`).join('\n')
    } },
    legend: { show: !props.compact, bottom: 0, icon: 'roundRect', textStyle: { color: ui.theme==='dark'?'#9cbab4':'#52657c' } },
    grid: { top: props.compact ? 4 : 16, bottom: props.compact ? 4 : 45, left: props.compact ? 0 : 56, right: 12 },
    xAxis: { type: props.probabilityAxis ? 'value' : 'time', min: props.probabilityAxis ? 0 : undefined, max: props.probabilityAxis ? 1 : undefined, show: !props.compact, axisLine: { show: false }, axisTick: { show: false }, axisLabel: { color: ui.theme==='dark'?'#9cbab4':'#52657c', formatter: props.probabilityAxis ? (v:number) => `${Math.round(v*100)}%` : undefined }, splitLine: { show: false } },
    yAxis: { type: 'value', show: !props.compact, scale: !props.probabilityAxis, min: props.probabilityAxis ? 0 : undefined, max: props.probabilityAxis ? 1 : undefined, splitLine: { lineStyle: { color: ui.theme==='dark'?'#24443e':'#dbe5eb' } }, axisLabel: { color: ui.theme==='dark'?'#9cbab4':'#52657c', formatter: props.probabilityAxis ? (v:number) => `${Math.round(v*100)}%` : undefined }, name: props.chart.unit },
    series: props.chart.series.map((s, index) => ({ name: s.name, type: props.kind, markLine: props.probabilityAxis && index===0 ? { silent:true, symbol:'none', label:{show:false}, lineStyle:{color:'#94a3b8',type:'dashed'}, data:[[{coord:[0,0]},{coord:[1,1]}]] } : undefined, data: s.points.map(p => ({ value: [props.probabilityAxis ? Number(p.at) : new Date(p.at).getTime(), p.value], note: `${props.probabilityAxis ? 'Probabilidad prevista ' + p.at : new Date(p.at).toISOString()}${p.netPnl == null ? '' : '\nP&L acumulado: ' + p.netPnl.toFixed(4)}${p.drawdown == null ? '' : '\nDrawdown: ' + p.drawdown.toFixed(4)}${p.tradeNumber == null ? '' : '\nOperación: ' + p.tradeNumber}` })), smooth: false, connectNulls: false, showSymbol: true, symbolSize: props.compact ? 4 : 5, lineStyle: { width: 2.5 }, areaStyle: props.compact ? { opacity: .08 } : undefined })),
  }; instance.setOption(options, { notMerge: true }); element.value?.setAttribute('aria-label',props.chart.title)
}
onMounted(() => { if (element.value) { instance = echarts.init(element.value); resize = new ResizeObserver(() => instance?.resize()); resize.observe(element.value); render() } })
watch(() => props.chart, render, { deep: false }); watch(() => props.kind, render); watch(()=>ui.theme,render)
onBeforeUnmount(() => { resize?.disconnect(); instance?.dispose() })
</script>
<template><p v-if="!compact" class="chart-title">{{ chart.title }} <span>· {{ chart.unit }}</span></p><div class="chart-wrap" :style="{ height: `${height}px` }"><div ref="element" role="img" :aria-label="chart.title" class="chart-canvas"></div><div v-if="!available" class="chart-empty"><span>DATA_UNAVAILABLE</span><small>El journal todavía no contiene observaciones para esta gráfica.</small></div></div></template>
