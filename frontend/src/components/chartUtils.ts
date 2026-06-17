// lightweight-charts indexes intraday data by UNIX *seconds* and requires the
// series to be strictly ascending with unique timestamps. Our data is in
// milliseconds and can have two points within the same second (e.g. two trades
// closing a few ms apart) — flooring to seconds then collides, which renders as
// a criss-crossed/folded line. Collapse to unique seconds (last value wins) and
// sort ascending so the chart always gets valid input.
export function normalizeSeconds(points: { time: number; value: number }[]): { time: number; value: number }[] {
  const bySecond = new Map<number, number>()
  for (const p of points) bySecond.set(Math.floor(p.time / 1000), p.value)
  return [...bySecond.entries()]
    .sort((a, b) => a[0] - b[0])
    .map(([time, value]) => ({ time, value }))
}
