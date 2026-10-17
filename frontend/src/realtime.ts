import { HubConnectionBuilder, LogLevel } from '@microsoft/signalr'
import { api } from './api'
import { applyEvent, applySnapshot, useSystemStore, useNotificationStore } from './stores'
import type { RealtimeEvent } from './types'
export const retryDelay = (count: number) => Math.min(30_000, 1000 * 2 ** Math.min(count, 5))
export class SequencedEvents {
  private sequence: number | null = null
  private chain = Promise.resolve()
  private generation = 0
  constructor(private refresh: () => Promise<void>, private apply: (e: RealtimeEvent) => void) { }
  reset() { this.sequence = null; this.generation++ }
  receive(event: RealtimeEvent): Promise<void> {
    const generation=this.generation
    const task=this.chain.then(async()=>{
      if(generation!==this.generation || this.sequence!==null && event.sequence<=this.sequence)return
      const gap=this.sequence!==null && event.sequence!==this.sequence+1
      if(gap)await this.refresh()
      if(generation!==this.generation)return
      if(!gap)this.apply(event)
      this.sequence=event.sequence
    })
    this.chain=task.catch(()=>{})
    return task
  }
}
export class QuoteBatcher {
  private latest:RealtimeEvent|undefined
  private frame:number|undefined
  constructor(private apply:(e:RealtimeEvent)=>void,private schedule:(f:FrameRequestCallback)=>number=f=>window.requestAnimationFrame(f),private cancel:(id:number)=>void=id=>window.cancelAnimationFrame(id)){}
  receive(e:RealtimeEvent){
    if(e.type!=='market.quote.updated'){if(e.type==='source.unavailable')this.clear();this.apply(e);return}
    this.latest=e
    if(this.frame===undefined)this.frame=this.schedule(()=>{this.frame=undefined;const value=this.latest;this.latest=undefined;if(value)this.apply(value)})
  }
  clear(){if(this.frame!==undefined)this.cancel(this.frame);this.frame=undefined;this.latest=undefined}
}
export function realtime() {
  const system = useSystemStore(); let stopped = false; let online = navigator.onLine; let pending: Promise<void> | null = null; let refreshEpoch=0;let retryTimer: ReturnType<typeof setTimeout> | undefined; let closing: Promise<void> | undefined
  const batched=new QuoteBatcher(applyEvent)
  let recoveryTimer:ReturnType<typeof setTimeout>|undefined;let recoveringSource=false
  const invalidate=()=>{refreshEpoch++;pending=null;batched.clear();clearTimeout(recoveryTimer);recoveryTimer=undefined;recoveringSource=false}
  const refresh = () => {
    if(pending)return pending
    const epoch=refreshEpoch
    const task=api.snapshot().then(snapshot=>{if(epoch===refreshEpoch&&!stopped){batched.clear();applySnapshot(snapshot)}}).finally(()=>{if(pending===task)pending=null})
    pending=task;return task
  }
  // A source outage needs a complete read snapshot to recover. Ordinary deltas
  // cannot clear uncertainty, and normal market events never request snapshots.
  function recoverSource(attempt=0){
    if(stopped||!online||recoveringSource)return
    recoveringSource=true;const epoch=refreshEpoch
    recoveryTimer=setTimeout(()=>{
      recoveryTimer=undefined
      void refresh().then(()=>{if(epoch===refreshEpoch)recoveringSource=false}).catch(()=>{
        if(epoch!==refreshEpoch||stopped||!online)return
        recoveringSource=false;system.error='DATA_UNAVAILABLE: esperando confirmar la fuente.';recoverSource(attempt+1)
      })
    },retryDelay(attempt))
  }
  const connection = new HubConnectionBuilder().withUrl('/hubs/dashboard').configureLogging(LogLevel.None)
    .withAutomaticReconnect({ nextRetryDelayInMilliseconds: c => retryDelay(c.previousRetryCount) }).build()
  const sequenced = new SequencedEvents(refresh, e=>batched.receive(e))
  connection.on('event', (event: RealtimeEvent) => {
    if(stopped)return
    // Invalidate an older in-flight read when a newly observed outage begins.
    if(event.type==='source.unavailable'&&!recoveringSource)invalidate()
    const epoch=refreshEpoch
    void sequenced.receive(event).then(()=>{if(epoch===refreshEpoch&&event.type==='source.unavailable')recoverSource()}).catch(()=>{if(stopped||epoch!==refreshEpoch)return;system.error='DATA_UNAVAILABLE';recoverSource()})
  })
  connection.onreconnecting(() => { invalidate();sequenced.reset();system.connection = 'RECONNECTING'; system.error = 'Conexión interrumpida; los valores conservados no son datos LIVE.' })
  connection.onreconnected(() => { invalidate();sequenced.reset(); void refresh().then(() => { system.connection = 'CONNECTED' }).catch(() => { system.error = 'DATA_UNAVAILABLE' }) })
  connection.onclose(() => { invalidate();sequenced.reset();system.connection = 'DISCONNECTED'; if (!stopped && online) void start(0) })
  connection.on('analysisCompleted', (e: { requestId: string }) => useNotificationStore().add({ id: e.requestId, kind: 'info', text: 'Sol terminó la consulta.' }))
  async function start(attempt: number) {
    if (stopped || !online) return
    try { await connection.start() }
    catch { system.connection = 'DISCONNECTED'; system.error = 'Backend o sesión no disponibles.'; if (!stopped && online) retryTimer = setTimeout(() => void start(attempt + 1), retryDelay(attempt)); return }
    sequenced.reset(); system.connection = 'CONNECTED'
    try { await refresh() } catch { system.error = 'DATA_UNAVAILABLE: conexión disponible, fuente sin confirmar.' }
  }
  const offline = () => { online = false; invalidate();sequenced.reset();clearTimeout(retryTimer); system.connection = 'DISCONNECTED'; system.error = 'Sin red; los datos conservados no son LIVE.'; closing = connection.stop() }
  const reconnect = () => { online = true; void (closing ?? Promise.resolve()).then(() => start(0)) }
  window.addEventListener('offline', offline); window.addEventListener('online', reconnect)
  return { start: () => start(0), stop: async () => { stopped = true; invalidate();sequenced.reset();window.removeEventListener('offline', offline); window.removeEventListener('online', reconnect); clearTimeout(retryTimer); await connection.stop() }, refresh }
}
