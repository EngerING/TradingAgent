<script setup lang="ts">
import type { Monitor } from '../../r20-monitor-contract'
defineProps<{snapshot:Monitor|null,error:string}>()
</script>
<template>
 <section class="shadow-monitor" aria-labelledby="shadow-heading">
  <h2 id="shadow-heading">Seguimiento Shadow V2</h2>
  <p class="notice">ENSAYO SINTÉTICO AISLADO · Sin cohorte operativa · Sin órdenes IBKR</p>
  <p v-if="error" role="alert">STALE · No se pudo actualizar. {{error}}</p>
  <p v-if="!snapshot">Sin evidencia del ciclo. No se infieren posiciones ni saldo.</p>
  <template v-else>
   <p><strong>{{snapshot.status}}</strong> · Datos {{snapshot.dataStatus}} · Integridad {{snapshot.integrity}}</p>
   <p>Último evento: {{snapshot.lastObservation??'Sin observación'}} UTC. Es un corte del ledger; no acredita un runner activo.</p>
   <dl>
    <dt>Propósito aplicado</dt><dd>{{snapshot.purpose??'UNKNOWN'}}</dd>
    <dt>PnL neto / apalancamiento agregado</dt><dd>{{snapshot.netPnl??'UNKNOWN'}} USD / {{snapshot.aggregateLeverage??'UNKNOWN'}} ×</dd>
    <dt>Protección intrabar</dt><dd>{{snapshot.intrabarProtection??'UNKNOWN'}}</dd>
    <dt>Último diagnóstico auténtico</dt><dd v-if="snapshot.lastAuthenticRead">{{snapshot.lastAuthenticRead.quoteAt}} UTC · {{snapshot.lastAuthenticRead.bid}} / {{snapshot.lastAuthenticRead.ask}} · {{snapshot.lastAuthenticRead.account}} · Corte histórico de lectura, sin feed continuo.</dd><dd v-else>Sin lectura auténtica disponible. Los datos de este ledger son sintéticos.</dd>
    <dt>Equity neta</dt><dd>{{snapshot.equity??'UNKNOWN'}} USD</dd>
    <dt>PnL bruto realizado / abierto</dt><dd>{{snapshot.realizedGross??'UNKNOWN'}} / {{snapshot.openGross??'UNKNOWN'}} USD</dd>
    <dt>Exposición / margen inicial modelado</dt><dd>{{snapshot.exposure??'UNKNOWN'}} / {{snapshot.margin??'UNKNOWN'}} USD</dd>
    <dt>Riesgo por precio al stop</dt><dd>{{snapshot.priceRisk??'UNKNOWN'}} USD</dd>
    <dt>Pérdida diaria consumida / capacidad restante</dt><dd>{{snapshot.daily?.used_loss??'UNKNOWN'}} / {{snapshot.daily?.remaining??'UNKNOWN'}} USD</dd>
    <dt>Bloqueo diario / Stop persistente</dt><dd>{{snapshot.daily?.loss_blocked?'BLOQUEADO':'NO ACREDITADO COMO BLOQUEADO'}} / {{snapshot.stopRequested?'SOLICITADO':'NO SOLICITADO'}}</dd>
    <dt>Recuperación</dt><dd>{{snapshot.daily?.operational_blocks.join(', ')||'Sin bloqueo registrado'}}</dd>
   </dl>
   <p v-if="snapshot.purpose==='TECHNICAL_VALIDATION'" class="notice">TECHNICAL_VALIDATION · Puede abrir con target neto negativo exclusivamente en Shadow. No acredita viabilidad económica ni permisos Paper.</p>
   <p v-if="snapshot.effectiveProfile" class="hash">Perfil contable {{snapshot.effectiveProfile.configuration_hash}} · Riesgo {{snapshot.effectiveProfile.risk_per_trade_pct}}% · Pérdida diaria {{snapshot.effectiveProfile.daily_loss_limit_pct}}% · Cap agregado {{snapshot.effectiveProfile.max_leverage}}× · Máximo {{snapshot.effectiveProfile.max_open_positions}} posiciones.</p>
   <p v-for="p in snapshot.positions" :key="'economics-'+p.position_id">{{p.position_id}} · {{p.purpose??'NORMAL'}} · Viabilidad al TP: {{p.economically_viable===false?'NO VIABLE':p.economically_viable===true?'TARGET NETO POSITIVO':'UNKNOWN'}} · Neto TP {{p.sizing?.net_target??'UNKNOWN'}} USD · Pérdida neta SL {{p.sizing?.net_stop??'UNKNOWN'}} USD.</p>
   <h3>Posiciones virtuales</h3><p v-if="!snapshot.positions.length">Sin posiciones Shadow abiertas.</p>
   <div v-else class="table-scroll"><table><thead><tr><th>Dirección</th><th>EUR</th><th>Entrada</th><th>Stop Loss</th><th>Take Profit</th><th>Costos USD</th></tr></thead><tbody><tr v-for="p in snapshot.positions" :key="p.position_id"><td>{{p.side}}</td><td>{{p.quantity}}</td><td>{{p.entry_price}}</td><td>{{p.stop}}</td><td>{{p.target}}</td><td>{{p.cost_total}}</td></tr></tbody></table></div>
   <h3>Señales y rechazos</h3><p v-if="!snapshot.signals.length">Sin evaluaciones registradas en este scope.</p>
   <ul v-else><li v-for="(s,i) in snapshot.signals" :key="i">{{s.at}} · {{s.decision?.side??'NO_SIGNAL'}} · {{s.reason}}</li></ul>
   <h3>Costos y reservas</h3><p v-if="!snapshot.costs.length">Sin costos registrados.</p>
   <ul v-else><li v-for="c in snapshot.costs" :key="c.costId">{{c.costId}}: {{c.amount}} USD · {{c.status}} / {{c.provenance}}</li></ul>
   <h3>Historial de operaciones virtuales</h3><p v-if="!snapshot.trades.length">Sin operaciones cerradas.</p>
   <div v-else class="table-scroll"><table><thead><tr><th>Cierre UTC</th><th>Motivo</th><th>Bruto USD</th><th>Costos USD</th><th>Neto USD</th></tr></thead><tbody><tr v-for="t in snapshot.trades" :key="t.position_id"><td>{{t.closed_at}}</td><td>{{t.reason}}</td><td>{{t.gross}}</td><td>{{t.cost}}</td><td>{{t.net}}</td></tr></tbody></table></div>
   <p class="hash">Contabilidad {{snapshot.accountingRevision??'UNKNOWN'}} · {{snapshot.accountingHash??'Sin hash'}} · Ciclo {{snapshot.lifecycleRevision}}</p>
  </template>
 </section>
</template>
<style scoped>
.shadow-monitor{background:#13242e;border:1px solid #2a4350;border-radius:12px;padding:24px;margin:20px 0;min-width:0;color:#dce7ed}.notice{color:#e0d793}h2{font-size:20px}h3{font-size:16px;margin-top:24px}p,li{overflow-wrap:anywhere}dl{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:12px}dd{margin:0;text-align:right;font-variant-numeric:tabular-nums;overflow-wrap:anywhere}dt{color:#a8bdc9}.table-scroll{overflow-x:auto}table{width:100%;border-collapse:collapse;font-size:13px}td,th{padding:10px;text-align:left;border-bottom:1px solid #36505d;white-space:nowrap}.hash{font-size:12px;color:#9ebcc9}.table-scroll:focus-visible{outline:2px solid #65d8c7}@media(max-width:760px){.shadow-monitor{padding:18px}dl{font-size:13px}}
</style>
