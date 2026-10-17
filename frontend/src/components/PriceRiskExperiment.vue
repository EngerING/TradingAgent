<script setup lang="ts">
import { useSystemStore,useKronosStore } from '../stores'
import { money,date } from '../format'
const system=useSystemStore()
const kronos=useKronosStore()
</script>
<template><section v-if="system.priceRisk" class="card price-risk" data-testid="price-risk-experiment">
  <div class="panel-heading"><div><span class="eyebrow">SIMULATED SHADOW · EXPERIMENTO INDEPENDIENTE</span><h2>R10 Experimental</h2></div><span class="pill">{{ system.priceRisk.status }} · {{ system.priceRisk.evidenceQuality ?? 'UNKNOWN' }}</span></div>
  <p>10% PRICE RISK · presupuesto inicial US$10. Costos adicionales separados. Capital inicial US$100.</p>
  <p>El stop no garantiza una pérdida máxima. Se conserva el stop técnico: el riesgo utilizado puede ser inferior a US$10.</p>
  <p>El último cálculo de tamaño es una evaluación; no acredita una señal vigente, una reserva activa ni una orden.</p>
  <dl class="price-values"><div><dt>Equity virtual</dt><dd>{{ money(Number(system.priceRisk.equity)) }}</dd></div><div><dt>PRICE_RISK alcanzable</dt><dd>{{ money(system.priceRisk.last_assessment?.price_risk==null?null:Number(system.priceRisk.last_assessment.price_risk)) }}</dd></div><div><dt>Comisiones estimadas</dt><dd>{{ money(system.priceRisk.last_assessment?.estimated_fees==null?null:Number(system.priceRisk.last_assessment.estimated_fees)) }}</dd></div><div><dt>ESTIMATED_ALL_IN_LOSS</dt><dd>{{ money(system.priceRisk.last_assessment?.estimated_all_in_loss==null?null:Number(system.priceRisk.last_assessment.estimated_all_in_loss)) }}</dd></div></dl>
  <p v-if="system.priceRisk.last_assessment">{{ system.priceRisk.last_assessment.reason ?? 'Sizing aprobado sólo para Shadow' }} · {{ system.priceRisk.last_assessment.quantity }} EUR · exposición {{ money(Number(system.priceRisk.last_assessment.notional)) }} · stop {{ system.priceRisk.last_assessment.stop }} · target {{ system.priceRisk.last_assessment.target }}</p>
  <p>Fees ESTIMATED; condiciones efectivas IBKR UNKNOWN. Paper {{ system.priceRisk.paper.state }} · autorización nueva de un solo uso pendiente. R10 original conserva su política all-in.</p>
  <p>Posición Shadow: {{ system.priceRisk.active ? 'ABIERTA · protección SIMULATED_ONLY' : 'NINGUNA' }} · {{ system.priceRisk.trades.length }} cierres virtuales · conciliación de journal, sin fills IBKR.</p>
  <p>Kronos observador: {{ kronos.view?.status ?? 'UNKNOWN' }} · {{ kronos.view?.calibrationState ?? 'UNKNOWN' }}. Un forecast antiguo no confirma la señal actual.</p>
  <details><summary>Desglose, operaciones y procedencia</summary><div class="table-scroll"><table><thead><tr><th>Spread</th><th>Slippage</th><th>Gap previsto</th><th>Financiación provisionada</th></tr></thead><tbody><tr><td>{{ money(system.priceRisk.last_assessment?.spread_cost==null?null:Number(system.priceRisk.last_assessment.spread_cost)) }}</td><td>{{ money(system.priceRisk.last_assessment?.slippage_cost==null?null:Number(system.priceRisk.last_assessment.slippage_cost)) }}</td><td>{{ money(system.priceRisk.last_assessment?.gap_reserve==null?null:Number(system.priceRisk.last_assessment.gap_reserve)) }}</td><td>{{ money(system.priceRisk.last_assessment?.financing_reserve==null?null:Number(system.priceRisk.last_assessment.financing_reserve)) }}</td></tr></tbody></table></div>
  <p>Ejemplo: US$10 por precio + US$4 de fees = 14% ESTIMATED ALL-IN LOSS antes de otros costos. No es el riesgo calculado de todas las señales ni un máximo garantizado.</p>
  <div class="table-scroll"><table><thead><tr><th>Cierre</th><th>Bruto</th><th>REALIZED_ALL_IN_PNL simulado</th><th>Motivo</th></tr></thead><tbody><tr v-for="t in system.priceRisk.trades" :key="t.id"><td>{{ date(t.closed_at ?? null) }}</td><td>{{ money(t.gross_pnl==null?null:Number(t.gross_pnl)) }}</td><td>{{ money(t.realized_all_in_pnl==null?null:Number(t.realized_all_in_pnl)) }}</td><td>{{ t.reason }}</td></tr></tbody></table></div>
  <p>Actualizado {{ date(system.priceRisk.updated_at) }} · Kronos observador; probabilidad calibrada no disponible. Sol LOCAL_EVIDENCE, US$0.</p></details>
</section></template>
<style scoped>.price-risk{margin-block:24px;overflow-wrap:anywhere}.price-values{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:16px}.price-values dd{margin:6px 0;font-weight:700}@media(max-width:600px){.price-values{grid-template-columns:repeat(2,minmax(0,1fr))}}</style>
