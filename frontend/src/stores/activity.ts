import { defineStore } from 'pinia'
import { shallowRef } from 'vue'
import type { DashboardSnapshot, RealtimeEvent, Trade, Signal, KronosView, MarketQuote, Experiment, SystemStatus, Research, SolResponse, Notification, PaperRotation, PriceRiskView } from '../types'
import { money, number, percent } from '../format'
import { aggressiveGrowthSchema, decimalValue } from '../modules/aggressive-growth/contracts'

export type ActivityKind = 'MARKET' | 'SIGNAL' | 'KRONOS' | 'TRADE_OPEN' | 'TRADE_UPDATE' | 'TRADE_CLOSE' | 'NO_TRADE' | 'RISK' | 'COST_REJECTION' | 'SOL' | 'SYSTEM' | 'ERROR' | 'PAPER'
export interface ActivityItem { id: string; kind: ActivityKind; at: string; title: string; detail: string; origin: string; tradeId?: string; snapshot?: boolean }
export const useActivityStore = defineStore('activity', () => {
  const items = shallowRef<ActivityItem[]>([])
  const limit = 300
  const tradeStates = new Map<string, string>()
  let study: string | null = null
  function add(item: ActivityItem) { items.value = [item, ...items.value.filter(i => i.id !== item.id)].slice(0, limit) }
  function ingest(e: RealtimeEvent, snapshot = false) {
    const base = { at: e.at, snapshot }
    const id = `event:${e.sequence}:${e.type}`
    switch (e.type) {
      case 'aggressiveGrowth.updated': {
        const parsed = aggressiveGrowthSchema.safeParse(e.data)
        if (!parsed.success) break
        const r20 = parsed.data
        for (const signal of r20.recentSignals) add({ ...base, id: `r20:${r20.experiment}:signal:${signal.id}`, at: signal.at,
          kind: signal.status === 'NO_TRADE' || signal.reason ? 'NO_TRADE' : 'SIGNAL', title: `R20 · ${signal.status} · ${signal.side ?? '—'}`,
          detail: `${r20.runKind} · ${signal.timeframe} min · ${signal.reason ?? 'Señal registrada'}`, origin: r20.classification })
        for (const trade of r20.trades) {
          const key = `r20:${r20.experiment}:trade:${trade.id}`
          const signature = JSON.stringify(trade)
          if (tradeStates.get(key) === signature) continue
          const previous = tradeStates.has(key)
          tradeStates.set(key, signature)
          if (tradeStates.size > 1000) tradeStates.delete(tradeStates.keys().next().value!)
          add({ ...base, id: `${key}:${trade.closedAt ? 'closed' : 'open'}`, at: trade.closedAt ?? trade.at,
            kind: trade.closedAt ? 'TRADE_CLOSE' : previous ? 'TRADE_UPDATE' : 'TRADE_OPEN', title: `R20 · ${trade.side} · ${trade.closedAt ? 'CERRADA' : 'ABIERTA'}`,
            detail: `${trade.runKind} · ${trade.quantity ?? 'UNKNOWN'} EUR · neto ${money(decimalValue(trade.netPnl))} · ${trade.reason ?? 'Protección virtual'}`, origin: trade.classification })
        }
        break
      }
      case 'priceRisk.updated': {
        const p=e.data as PriceRiskView
        for(const row of p.events ?? []) add({...base,id:row.id,at:row.at,kind:row.kind==='SIMULATED_SHADOW_FILL'?'TRADE_OPEN':row.kind==='SHADOW_CLOSE_RECONCILED'?'TRADE_CLOSE':row.kind==='NO_TRADE'?'NO_TRADE':'SYSTEM',title:`R10 Experimental ${row.kind}`,detail:JSON.stringify(row.detail),origin:'SIMULATED_SHADOW'})
        break
      }
      case 'rotation.updated': {
        const rotation=e.data as PaperRotation
        for(const row of rotation.events ?? [])add({...base,id:row.id,at:row.at,kind:'PAPER',title:row.kind,detail:`${row.profile ?? ''} · ${row.detail}`,origin:row.origin})
        break
      }
      case 'market.quote.updated': {
        const q = e.data as MarketQuote
        // Coalesced market ticks replace one visible market row; fills are never coalesced.
        add({ ...base, id: 'latest-market', kind: 'MARKET', title: q.symbol, origin: q.source, detail: `${q.quality} · BID ${number(q.bid, 5)} / ASK ${number(q.ask, 5)} · spread ${number(q.spread, 5)}` }); break
      }
      case 'prediction.updated': {
        const s = e.data as Signal
        const decisions = Object.entries(s.decisions)
        if (!decisions.length) add({ ...base, id, kind: s.decision === 'TRADE' ? 'SIGNAL' : 'NO_TRADE', title: s.decision, detail: `${s.probabilityStatus} · ${s.regime}`, origin: 'DETERMINISTIC_SIGNAL' })
        for (const [profile, value] of decisions) {
          const d = value && typeof value === 'object' && !Array.isArray(value) ? value : {}
          add({ ...base, id: `${id}:${profile}`, kind: d.decision === 'TRADE' ? 'SIGNAL' : /COST|COMMISSION|SPREAD|SLIPPAGE/.test(String(d.reason ?? d.reasons ?? '')) ? 'COST_REJECTION' : 'NO_TRADE', title: `${profile} · ${String(d.decision ?? s.decision)}`, detail: String(d.reason ?? d.reasons ?? s.status), origin: 'SIGNAL_GATE' })
        } break
      }
      case 'kronos.updated': {
        const k = e.data as KronosView; const p = k.latest
        add({ ...base, id: p ? `kronos:${p.prediction_id}` : id, kind: 'KRONOS', title: `${k.status} · ${p?.consensus.kronos_direction ?? 'UNKNOWN'}`, detail: `RAW TP ${percent(p?.raw_tp_frequency)} · SL ${percent(p?.raw_sl_frequency)} · NEITHER ${percent(p?.neither_frequency)} · ${k.calibrationState}`, origin: 'KRONOS_FORECAST' }); break
      }
      case 'position.updated':
      case 'trade.completed': {
        for (const t of e.data as Trade[]) {
          const key = `${t.classification}:${t.id}`
          const signature = JSON.stringify(t)
          if (tradeStates.get(key) === signature) continue
          tradeStates.set(key, signature)
          if (tradeStates.size > 1000) tradeStates.delete(tradeStates.keys().next().value!)
          const previous = items.value.some(i => i.tradeId === t.id && i.kind !== 'TRADE_CLOSE')
          const kind = e.type === 'trade.completed' ? 'TRADE_CLOSE' : previous ? 'TRADE_UPDATE' : 'TRADE_OPEN'
          add({ ...base, at: t.closedAt ?? e.at, id: `${t.id}:${kind}:${e.sequence}`, tradeId: t.id, kind, title: `${t.profile} · ${t.symbol} · ${t.direction}`, detail: `${t.status} · ${number(t.quantity)} · net ${money(t.netPnl)} · comisión ${t.commissionStatus}`, origin: t.classification })
        } break
      }
      case 'experiment.updated': {
        for (const p of e.data as Experiment[]) add({ ...base, id: `${id}:${p.id}`, kind: 'RISK', title: `${p.id} · ${p.status}`, detail: `${p.stoppedForDay ? 'DAY STOP · ' : ''}${p.dailyStopReason ?? p.reason ?? 'Sin motivo expuesto'} · próximo presupuesto ${money(p.risk?.nextBudget)}`, origin: p.classification ?? 'EXPERIMENT_READ_MODEL' }); break
      }
      case 'connection.updated': { const s = e.data as SystemStatus; add({ ...base, id: 'latest-system', kind: 'SYSTEM', title: `IBKR ${s.ibkr}`, detail: `EmergencyStop ${s.emergency} · Live ${s.liveState}`, origin: 'SYSTEM_READ_MODEL' }); break }
      case 'source.unavailable': add({ ...base, id, kind: 'ERROR', title: 'DATA_UNAVAILABLE', detail: 'Journal no disponible. Datos conservados STALE.', origin: 'SOURCE_ERROR' }); break
      case 'journal.updated': { const r = e.data as Research; add({ ...base, id, kind: 'SYSTEM', title: 'Research actualizado', detail: `${r.status} · ${r.candidates.length} candidatos · sin promoción automática`, origin: 'RESEARCH_JOURNAL' }); break }
      case 'notification.updated': for (const n of e.data as Notification[]) add({ ...base, id: `notification:${n.id}`, kind: /ERROR|FAILURE/.test(n.kind)?'ERROR':'SYSTEM', title: n.kind, detail: n.text, origin: 'BACKEND_NOTIFICATION' }); break
    }
  }
  function hydrate(s: DashboardSnapshot) {
    if (study !== s.studyId) { clear(); study = s.studyId }
    // Snapshot rows are labelled, not presented as a recovered complete event history.
    for (const [type, data] of [['aggressiveGrowth.updated',s.aggressiveGrowth],['priceRisk.updated',s.priceRisk],['rotation.updated',s.rotation],['connection.updated', s.system], ['market.quote.updated', s.market], ['prediction.updated', s.prediction], ['kronos.updated', s.kronos], ['experiment.updated', s.experiments], ['position.updated', s.openPositions], ['trade.completed', s.trades]] as const) {
      if (data) ingest({ sequence: s.revision, type, data, at: s.at }, true)
    }
  }
  function sol(response: SolResponse) { add({ id: `sol:${response.requestId}`, kind: 'SOL', at: new Date().toISOString(), title: response.status, detail: response.text, origin: response.provider }) }
  function clear() { items.value = []; tradeStates.clear(); study = null }
  return { items, limit, add, ingest, hydrate, sol, clear }
})
