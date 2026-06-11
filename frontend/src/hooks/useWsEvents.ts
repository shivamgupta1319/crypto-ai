import { useEffect, useRef } from 'react'
import { signalsWsUrl } from '../api/client'

type WsMessage = { type: string; data: unknown }

// Subscribes to the signals WebSocket and invokes `onMessage` for each frame,
// with auto-reconnect. Used by the Portfolio page to refresh on trade events.
export function useWsEvents(onMessage: (msg: WsMessage) => void) {
  const cbRef = useRef(onMessage)
  cbRef.current = onMessage

  useEffect(() => {
    let closed = false
    let ws: WebSocket | null = null

    function connect() {
      ws = new WebSocket(signalsWsUrl())
      ws.onmessage = (ev) => {
        try {
          cbRef.current(JSON.parse(ev.data) as WsMessage)
        } catch {
          /* ignore malformed frames */
        }
      }
      ws.onclose = () => {
        if (!closed) setTimeout(connect, 3000)
      }
      ws.onerror = () => ws?.close()
    }
    connect()

    return () => {
      closed = true
      ws?.close()
    }
  }, [])
}
