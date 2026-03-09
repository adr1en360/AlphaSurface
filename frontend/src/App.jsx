import { useEffect, useState } from "react"
import { Tldraw, useEditor, toRichText } from "tldraw"
import "tldraw/tldraw.css"

function AlphaSurfaceInner() {
  const editor = useEditor()
  const [ws, setWs] = useState(null)
  const [indicator, setIndicator] = useState(false)

  useEffect(() => {
    const socket = new WebSocket("/ws")

    socket.onopen = () => {
      console.log("Connected to AlphaSurface backend")
      setWs(socket)
    }

    socket.onmessage = (event) => {
      const message = JSON.parse(event.data)
      console.log("Message from backend:", message)

      setIndicator(true)
      setTimeout(() => setIndicator(false), 1500)

      if (message.type === "add_text") {
        editor.createShape({
          type: "text",
          x: message.payload.x ?? 200,
          y: message.payload.y ?? 200,
          props: {
            richText: toRichText(message.payload.text),
            size: "m"
          }
        })
      }
    }

    socket.onerror = (e) => console.error("WebSocket error:", e)
    socket.onclose = () => console.log("WebSocket closed")

    return () => socket.close()
  }, [])

  useEffect(() => {
    if (!ws || !editor) return
    const interval = setInterval(() => {
      const shapeIds = [...editor.getCurrentPageShapeIds()]
      if (shapeIds.length === 0) return
      ws.send(JSON.stringify({
        type: "canvas_snapshot",
        payload: { shape_count: shapeIds.length }
      }))
    }, 3000)
    return () => clearInterval(interval)
  }, [ws, editor])

  return (
    <>
      {indicator && (
        <div style={{
          position: "fixed", top: 0, left: 0, right: 0,
          height: "4px", backgroundColor: "#8b5cf6",
          zIndex: 9999
        }} />
      )}
    </>
  )
}

export default function App() {
  return (
    <div style={{ position: "fixed", inset: 0 }}>
      <Tldraw>
        <AlphaSurfaceInner />
      </Tldraw>
    </div>
  )
}
