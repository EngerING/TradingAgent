import { beforeEach,afterEach,it,expect,vi } from 'vitest'
import { createPinia,setActivePinia } from 'pinia'
import { api } from '../api'
import { applySnapshot,useMarketStore,useSystemStore } from '../stores'
import type { RealtimeEvent } from '../types'
import { mockSnapshot } from './fixtures'
import { realtime } from '../realtime'
const fake=vi.hoisted(()=>({hooks:new Map<string,()=>void>(),event:undefined as ((e:RealtimeEvent)=>void)|undefined}))
vi.mock('@microsoft/signalr',()=>({LogLevel:{None:0},HubConnectionBuilder:class{
 withUrl(){return this}configureLogging(){return this}withAutomaticReconnect(){return this}
 build(){return {on:(name:string,f:(e:RealtimeEvent)=>void)=>{if(name==='event')fake.event=f},onreconnecting:(f:()=>void)=>fake.hooks.set('reconnecting',f),onreconnected:(f:()=>void)=>fake.hooks.set('reconnected',f),onclose:(f:()=>void)=>fake.hooks.set('close',f),start:async()=>{},stop:async()=>{}}}
}}))
beforeEach(()=>{setActivePinia(createPinia());applySnapshot(structuredClone(mockSnapshot));fake.hooks.clear();vi.stubGlobal('requestAnimationFrame',(f:FrameRequestCallback)=>setTimeout(()=>f(0),0));vi.stubGlobal('cancelAnimationFrame',clearTimeout)})
afterEach(()=>vi.useRealTimers())
it('in-flight snapshot cannot mutate stores after logout/stop',async()=>{
 let release:(s:typeof mockSnapshot)=>void=()=>{};const request=vi.spyOn(api,'snapshot').mockImplementation(()=>new Promise(r=>{release=r}))
 const stream=realtime();const started=stream.start();await vi.waitFor(()=>expect(request).toHaveBeenCalledTimes(1));await stream.stop();release({...mockSnapshot,market:{...mockSnapshot.market,bid:1.3}});await started
 expect(useMarketStore().quote?.bid).toBeNull()
})
it('old refresh cannot overwrite a newer reconnect snapshot',async()=>{
 let release:(s:typeof mockSnapshot)=>void=()=>{};const current={...mockSnapshot,market:{...mockSnapshot.market,bid:1.15,source:'MOCK_RECONNECT'}}
 vi.spyOn(api,'snapshot').mockResolvedValueOnce(mockSnapshot).mockImplementationOnce(()=>new Promise(r=>{release=r})).mockResolvedValueOnce(current)
 const stream=realtime();await stream.start();const old=stream.refresh();fake.hooks.get('reconnecting')!();fake.hooks.get('reconnected')!()
 await vi.waitFor(()=>expect(useMarketStore().quote?.source).toBe('MOCK_RECONNECT'));release({...mockSnapshot,market:{...mockSnapshot.market,bid:1.13,source:'MOCK_OLD'}});await old
 expect(useMarketStore().quote?.bid).toBe(1.15);await stream.stop()
})
it('source outage retains STALE until a complete snapshot succeeds with bounded backoff',async()=>{
 vi.useFakeTimers();const current={...mockSnapshot,market:{...mockSnapshot.market,quality:'LIVE',bid:1.15}}
 const request=vi.spyOn(api,'snapshot').mockResolvedValueOnce(mockSnapshot).mockRejectedValueOnce(Error('MOCK_SOURCE_UNAVAILABLE')).mockResolvedValue(current)
 const stream=realtime();await stream.start();fake.event!({sequence:1,type:'source.unavailable',data:{},at:mockSnapshot.at});await vi.advanceTimersByTimeAsync(0)
 expect(useSystemStore().error).toContain('DATA_UNAVAILABLE');expect(useMarketStore().quote?.quality).toBe('STALE')
 await vi.advanceTimersByTimeAsync(1000);expect(request).toHaveBeenCalledTimes(2);expect(useSystemStore().error).toContain('DATA_UNAVAILABLE')
 fake.event!({sequence:2,type:'source.unavailable',data:{},at:mockSnapshot.at});await vi.advanceTimersByTimeAsync(1999);expect(request).toHaveBeenCalledTimes(2)
 await vi.advanceTimersByTimeAsync(1);expect(request).toHaveBeenCalledTimes(3);expect(useSystemStore().error).toBe('');expect(useMarketStore().quote?.bid).toBe(1.15);expect(useSystemStore().status?.ordersSupported).toBe(false);await stream.stop()
})
it('logout cancels scheduled source recovery without an extra request',async()=>{
 vi.useFakeTimers();const request=vi.spyOn(api,'snapshot').mockResolvedValue(mockSnapshot);const stream=realtime();await stream.start()
 fake.event!({sequence:1,type:'source.unavailable',data:{},at:mockSnapshot.at});await vi.advanceTimersByTimeAsync(0);await stream.stop();await vi.advanceTimersByTimeAsync(30_000);expect(request).toHaveBeenCalledTimes(1)
})
it('normal granular events never cause periodic snapshot reloads',async()=>{
 vi.useFakeTimers();const request=vi.spyOn(api,'snapshot').mockResolvedValue(mockSnapshot);const stream=realtime();await stream.start()
 fake.event!({sequence:1,type:'connection.updated',data:mockSnapshot.system,at:mockSnapshot.at});fake.event!({sequence:2,type:'study.updated',data:mockSnapshot.studyStatus,at:mockSnapshot.at});await vi.advanceTimersByTimeAsync(30_000);expect(request).toHaveBeenCalledTimes(1);await stream.stop()
})
