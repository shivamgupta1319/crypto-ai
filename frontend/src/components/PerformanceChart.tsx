import { useEffect, useRef } from 'react'
import { createChart, ColorType, LineSeries, AreaSeries, type IChartApi } from 'lightweight-charts'

export interface ChartPoint {
  time: number // ms epoch
  value: number
}

export interface ChartSeries {
  label: string
  color: string
  type?: 'line' | 'area'
  data: ChartPoint[]
}

// A small generic time-series chart (line or area) reusing the same dark theme
// as EquityChart. Used for the live equity / drawdown / exposure analytics.
export default function PerformanceChart({
  series,
  height = 240,
}: {
  series: ChartSeries[]
  height?: number
}) {
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)

  useEffect(() => {
    if (!containerRef.current) return
    const chart = createChart(containerRef.current, {
      height,
      layout: { background: { type: ColorType.Solid, color: 'transparent' }, textColor: '#94a3b8' },
      grid: { vertLines: { color: '#1e293b' }, horzLines: { color: '#1e293b' } },
      timeScale: { timeVisible: true, borderColor: '#334155' },
      rightPriceScale: { borderColor: '#334155' },
      autoSize: true,
    })
    chartRef.current = chart

    for (const s of series) {
      // lightweight-charts expects ascending unix seconds.
      const data = s.data.map((p) => ({ time: Math.floor(p.time / 1000) as never, value: p.value }))
      if (s.type === 'area') {
        const area = chart.addSeries(AreaSeries, {
          lineColor: s.color,
          topColor: `${s.color}55`,
          bottomColor: `${s.color}05`,
          lineWidth: 2,
        })
        area.setData(data)
      } else {
        const line = chart.addSeries(LineSeries, { color: s.color, lineWidth: 2 })
        line.setData(data)
      }
    }
    chart.timeScale().fitContent()

    return () => chart.remove()
  }, [series, height])

  return <div ref={containerRef} className="w-full" />
}
