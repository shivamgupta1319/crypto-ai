import { useEffect, useRef } from 'react'
import { createChart, ColorType, LineSeries, type IChartApi } from 'lightweight-charts'
import type { EquityPoint } from '../api/client'

// Renders one or more equity curves on a single chart.
export default function EquityChart({
  series,
}: {
  series: { label: string; color: string; data: EquityPoint[] }[]
}) {
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)

  useEffect(() => {
    if (!containerRef.current) return
    const chart = createChart(containerRef.current, {
      height: 300,
      layout: { background: { type: ColorType.Solid, color: 'transparent' }, textColor: '#94a3b8' },
      grid: { vertLines: { color: '#1e293b' }, horzLines: { color: '#1e293b' } },
      timeScale: { timeVisible: true, borderColor: '#334155' },
      rightPriceScale: { borderColor: '#334155' },
      autoSize: true,
    })
    chartRef.current = chart

    for (const s of series) {
      const line = chart.addSeries(LineSeries, { color: s.color, lineWidth: 2 })
      line.setData(
        // lightweight-charts expects ascending unix seconds.
        s.data.map((p) => ({ time: Math.floor(p.time / 1000) as never, value: p.equity })),
      )
    }
    chart.timeScale().fitContent()

    return () => chart.remove()
  }, [series])

  return <div ref={containerRef} className="w-full" />
}
