import { useEffect, useRef, useState } from 'react'
import { api, signalsWsUrl, type LiveSignal } from '../api/client'

type Status = 'connecting' | 'live' | 'offline'

// Loads recent signals, then keeps a live WebSocket feed merged on top.
export function useSignalFeed() {
  const [signals, setSignals] = useState<LiveSignal[]>([])
  const [status, setStatus] = useState<Status>('connecting')
  const wsRef = useRef<WebSocket | null>(null)

  useEffect(() => {
    let closed = false

    api.getSignals(100).then((s) => !closed && setSignals(s)).catch(() => {})

    function connect() {
      const ws = new WebSocket(signalsWsUrl())
      wsRef.current = ws
      ws.onopen = () => setStatus('live')
      ws.onmessage = (ev) => {
        try {
          const msg = JSON.parse(ev.data)
          if (msg.type === 'signal') {
            setSignals((prev) => [msg.data as LiveSignal, ...prev].slice(0, 200))
          }
        } catch {
          /* ignore malformed frames */
        }
      }
      ws.onclose = () => {
        setStatus('offline')
        if (!closed) setTimeout(connect, 3000) // auto-reconnect
      }
      ws.onerror = () => ws.close()
    }
    connect()

    return () => {
      closed = true
      wsRef.current?.close()
    }
  }, [])

  return { signals, status, setSignals }
}
