import { expect, it, vi } from 'vitest'
import * as echarts from 'echarts/core'
import { CandlestickChart, LineChart } from 'echarts/charts'
import { AriaComponent, DataZoomComponent, GridComponent, MarkAreaComponent, MarkLineComponent, TooltipComponent } from 'echarts/components'
import { SVGRenderer } from 'echarts/renderers'
import { kronosOptions } from '../chart-options'
import type { KronosPrediction } from '../types'

echarts.use([CandlestickChart, LineChart, AriaComponent, DataZoomComponent, GridComponent, MarkAreaComponent, MarkLineComponent, TooltipComponent, SVGRenderer])

it('keeps the forecast accessible name after resize with all future points expired', () => {
  // SVG and ARIA are real; jsdom has no optional canvas text-measurement backend.
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(null)
  const element = document.createElement('div')
  document.body.append(element)
  const chart = echarts.init(element, undefined, { renderer: 'svg', width: 500, height: 300 })
  const prediction = { timeframe: '1H', historical: [], quantiles: [] } as unknown as KronosPrediction
  try {
    chart.setOption(kronosOptions(prediction, Date.parse('2026-10-10T00:00:00Z')))
    // The component used to restore this manually only after setOption.
    element.setAttribute('aria-label', 'Velas reales y forecast Kronos separados')
    chart.resize({ width: 390, height: 300 })
    expect(element.getAttribute('aria-label')).toBe('Velas reales y forecast Kronos separados')
  } finally { chart.dispose(); element.remove() }
})
