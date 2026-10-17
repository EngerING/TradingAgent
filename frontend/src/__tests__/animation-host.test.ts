import { afterEach, expect, it, vi } from 'vitest'
import { QuoteBatcher } from '../realtime'
import type { RealtimeEvent } from '../types'

afterEach(() => vi.unstubAllGlobals())

it('uses animation host functions without binding the QuoteBatcher as their receiver', () => {
  let pending: FrameRequestCallback | undefined
  // Browser animation methods reject foreign receivers. jsdom does not enforce
  // this Web IDL boundary; retain it here to reproduce Chromium Illegal invocation.
  vi.stubGlobal('requestAnimationFrame', function (this: unknown, callback: FrameRequestCallback) {
    if (this !== undefined && this !== window) throw new TypeError('Illegal invocation')
    pending = callback
    return 7
  })
  const cancelled: number[] = []
  vi.stubGlobal('cancelAnimationFrame', function (this: unknown, id: number) {
    if (this !== undefined && this !== window) throw new TypeError('Illegal invocation')
    cancelled.push(id)
  })
  const apply = vi.fn()
  const batcher = new QuoteBatcher(apply)
  const quote = { sequence: 1, type: 'market.quote.updated', at: '2026-10-12T00:39:00Z', data: {} } as RealtimeEvent
  batcher.receive(quote)
  pending!(0)
  expect(apply).toHaveBeenCalledWith(quote)
  batcher.receive({ ...quote, sequence: 2 })
  batcher.clear()
  pending!(0)
  expect(cancelled).toEqual([7])
  expect(apply).toHaveBeenCalledTimes(1)
})
