<script setup lang="ts">
import { computed, ref, onMounted, onBeforeUnmount, watch } from 'vue'
import * as echarts from 'echarts/core'
import { CandlestickChart, LineChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, DataZoomComponent, MarkAreaComponent, MarkLineComponent, AriaComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import type { ECharts } from 'echarts/core'
import type { KronosPrediction } from '../types'
import { useInterfaceStore } from '../stores/interface'
import { kronosOptions, forecastCloseAt, visibleForecast } from '../chart-options'
echarts.use([CandlestickChart,LineChart,GridComponent,TooltipComponent,DataZoomComponent,MarkAreaComponent,MarkLineComponent,AriaComponent,CanvasRenderer])
const ui=useInterfaceStore()
const props=defineProps<{ prediction:KronosPrediction }>();const element=ref<HTMLElement>();let chart:ECharts|undefined;let resize:ResizeObserver|undefined;let timer:ReturnType<typeof setInterval>|undefined
const now=ref(Date.now());const hidden=computed(()=>props.prediction.quantiles.length-visibleForecast(props.prediction,now.value).length)
function render(){now.value=Date.now();chart?.setOption(kronosOptions(props.prediction,now.value,ui.theme==='dark'),{notMerge:true})}
function clock(){render()}
onMounted(()=>{if(element.value){chart=echarts.init(element.value);resize=new ResizeObserver(()=>chart?.resize());resize.observe(element.value);render();timer=setInterval(clock,30_000)}})
watch(()=>props.prediction,render)
watch(()=>ui.theme,render)
onBeforeUnmount(()=>{clearInterval(timer);resize?.disconnect();chart?.dispose()})
</script>
<template><div ref="element" class="kronos-chart" role="img" aria-label="Velas reales y forecast Kronos separados"></div><p class="chart-time-note">UTC · cierres pronosticados después de NOW. {{ hidden }} puntos sin cierre futuro verificable omitidos del gráfico; conservados en la tabla.</p><details class="chart-data-table"><summary>Ver datos originales del forecast · UTC</summary><div class="table-scroll" tabindex="0" aria-label="Datos accesibles del forecast"><table><caption class="sr-only">Cierre pronosticado de cada vela futura, identificada por su apertura UTC. USD/EUR, dispersión no calibrada.</caption><thead><tr><th>Apertura original UTC</th><th>Cierre de vela UTC</th><th>Cierre previsto · mediana</th><th>P05</th><th>P95</th></tr></thead><tbody><tr v-for="q in prediction.quantiles" :key="q.at"><td>{{ q.at }}</td><td>{{ forecastCloseAt(prediction,q.at)===null?'UNKNOWN':new Date(forecastCloseAt(prediction,q.at)!).toISOString() }}</td><td>{{ q.median.toFixed(5) }}</td><td>{{ q.p05.toFixed(5) }}</td><td>{{ q.p95.toFixed(5) }}</td></tr></tbody></table></div></details></template>
