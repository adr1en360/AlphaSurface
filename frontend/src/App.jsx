import { useEffect, useState } from "react"
import { Tldraw, useEditor, toRichText, getSnapshot, loadSnapshot, AssetRecordType } from "tldraw"
import "tldraw/tldraw.css"

// Handler for incoming WebSocket messages - extracted outside component to avoid stale closures
function handleCanvasMessage(editor, message) {
  if (!editor) return  // Guard against null editor
  const p = message.payload

  switch (message.type) {

    // ── Plain text label ──────────────────────────────────────
    case "add_text":
      editor.createShape({
        type: "text",
        x: p.x ?? 200, y: p.y ?? 200,
        props: {
          richText: toRichText(p.text),
          size: p.size ?? "m",
          color: p.color ?? "black",
        }
      })
      break

    // ── Sticky note ───────────────────────────────────────────
    case "add_note":
      editor.createShape({
        type: "note",
        x: p.x ?? 300, y: p.y ?? 300,
        props: {
          richText: toRichText(p.text),
          color: p.color ?? "violet",
          size: p.size ?? "m",
        }
      })
      break

    // ── Geo shapes (rect, ellipse, triangle, diamond, etc.) ───
    case "add_geo":
      editor.createShape({
        type: "geo",
        x: p.x ?? 200, y: p.y ?? 200,
        props: {
          geo: p.geo ?? "rectangle",   // rectangle | ellipse | triangle | diamond | hexagon | star | oval | rhombus | pentagon | cloud | arrow-right | arrow-left | check-box | x-box | cross
          w: p.w ?? 200,
          h: p.h ?? 120,
          richText: toRichText(p.text ?? ""),
          color: p.color ?? "blue",
          fill: p.fill ?? "semi",      // none | semi | solid | pattern
          dash: p.dash ?? "draw",      // draw | dashed | dotted | solid
          size: p.size ?? "m",
        }
      })
      break

    // ── Arrow ─────────────────────────────────────────────────
    case "add_arrow":
      editor.createShape({
        type: "arrow",
        x: p.x1 ?? 100, y: p.y1 ?? 100,
        props: {
          start: { x: 0, y: 0 },
          end: { x: (p.x2 ?? 300) - (p.x1 ?? 100), y: (p.y2 ?? 200) - (p.y1 ?? 100) },
          richText: toRichText(p.label ?? ""),
          color: p.color ?? "black",
          size: p.size ?? "m",
          arrowheadEnd: p.arrowhead ?? "arrow",  // arrow | triangle | square | dot | none
          arrowheadStart: "none",
        }
      })
      break

    // ── Bind Arrow (shape-to-shape connection) ────────────────
    case "bind_arrow":
      if (p.fromShapeId && p.toShapeId) {
        const fromShape = editor.getShape(p.fromShapeId)
        const toShape = editor.getShape(p.toShapeId)
        if (fromShape && toShape) {
          // Calculate midpoint between shapes for arrow base position
          const midX = (fromShape.x + toShape.x) / 2
          const midY = (fromShape.y + toShape.y) / 2
          editor.createShape({
            type: "arrow",
            x: midX,
            y: midY,
            props: {
              start: { type: "binding", boundShapeId: p.fromShapeId },
              end: { type: "binding", boundShapeId: p.toShapeId },
              richText: toRichText(p.label ?? ""),
              color: p.color ?? "black",
              size: p.size ?? "m",
            }
          })
        }
      }
      break

    // ── Image from URL ────────────────────────────────────────
    case "add_image": {
      const assetId = AssetRecordType.createId()
      editor.createAssets([{
        id: assetId,
        type: "image",
        typeName: "asset",
        props: {
          name: p.name ?? "image",
          src: p.url,
          w: p.w ?? 400,
          h: p.h ?? 300,
          mimeType: p.mimeType ?? "image/jpeg",
          isAnimated: false,
        },
        meta: {}
      }])
      editor.createShape({
        type: "image",
        x: p.x ?? 200, y: p.y ?? 200,
        props: {
          assetId,
          w: p.w ?? 400,
          h: p.h ?? 300,
        }
      })
      break
    }

    // ── Frame (named section / container) ────────────────────
    case "add_frame":
      editor.createShape({
        type: "frame",
        x: p.x ?? 100, y: p.y ?? 100,
        props: {
          name: p.name ?? "Frame",
          w: p.w ?? 400,
          h: p.h ?? 300,
        }
      })
      break

    // ── Clear entire canvas ───────────────────────────────────
    case "clear_canvas": {
      const allIds = [...editor.getCurrentPageShapeIds()]
      if (allIds.length > 0) editor.deleteShapes(allIds)
      break
    }

    // ── Delete specific shapes ────────────────────────────────
    case "delete_shapes":
      if (p.shapeIds && p.shapeIds.length > 0) {
        editor.deleteShapes(p.shapeIds)
      }
      break

    // ── Zoom / pan camera ─────────────────────────────────────
    case "set_camera":
      editor.setCamera({ x: p.x ?? 0, y: p.y ?? 0, z: p.zoom ?? 1 })
      break

    // ── Zoom to fit all content ───────────────────────────────
    case "zoom_to_fit":
      editor.zoomToFit()
      break

    // ── Focus on specific shape ───────────────────────────────
    case "focus_shape":
      if (p.shapeId) {
        const shape = editor.getShape(p.shapeId)
        if (shape) {
          editor.zoomToSelection([p.shapeId])
          editor.select(p.shapeId)
        }
      }
      break

    // ── Canvas snapshots (monitoring, ignore on frontend) ─────
    case "canvas_snapshot":
      // Sent by frontend every 3s, echoed back by backend - safe to ignore
      break

    default:
      console.warn("Unknown message type:", message.type)
  }
}

function AlphaSurfaceInner() {
  const editor = useEditor()
  const [ws, setWs] = useState(null)
  const [indicator, setIndicator] = useState(false)

  useEffect(() => {
    if (!editor) return  // Wait for editor to be ready
    
    let socket
    let retryDelay = 1000
    let retryTimeout

    function connect() {
      socket = new WebSocket("/ws")

      socket.onopen = () => {
        console.log("Connected to AlphaSurface backend")
        retryDelay = 1000  // reset backoff on success
        setWs(socket)
      }

      socket.onmessage = (event) => {
        const message = JSON.parse(event.data)
        console.log("Incoming:", message.type, message.payload)
        setIndicator(true)
        setTimeout(() => setIndicator(false), 1500)
        handleCanvasMessage(editor, message)
      }

      socket.onerror = () => {}  // onclose handles it

      socket.onclose = () => {
        console.log(`Disconnected. Retrying in ${retryDelay / 1000}s...`)
        setWs(null)
        retryTimeout = setTimeout(() => {
          retryDelay = Math.min(retryDelay * 2, 30000)
          connect()
        }, retryDelay)
      }
    }

    connect()

    return () => {
      clearTimeout(retryTimeout)
      socket?.close()
    }
  }, [editor])

  useEffect(() => {
    if (!ws || !editor) return
    const interval = setInterval(() => {
      const shapeIds = [...editor.getCurrentPageShapeIds()]
      if (shapeIds.length === 0) return
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({
          type: "canvas_snapshot",
          payload: { 
            shapeIds: shapeIds.map(id => id.toString()),
            shape_count: shapeIds.length 
          }
        }))
      }
    }, 3000)
    return () => clearInterval(interval)
  }, [ws, editor])

  const handleSave = () => {
    const snapshot = getSnapshot(editor.store)
    const blob = new Blob([JSON.stringify(snapshot)], { type: "application/json" })
    const url = URL.createObjectURL(blob)
    const a = document.createElement("a")
    a.href = url
    a.download = "alphasurface-session.tldr"
    a.click()
    URL.revokeObjectURL(url)
  }

  const handleLoad = () => {
    const input = document.createElement("input")
    input.type = "file"
    input.accept = ".tldr"
    input.onchange = (e) => {
      const file = e.target.files[0]
      if (!file) return
      const reader = new FileReader()
      reader.onload = (ev) => {
        loadSnapshot(editor.store, JSON.parse(ev.target.result))
      }
      reader.readAsText(file)
    }
    input.click()
  }

  return (
    <>
      {indicator && (
        <div style={{
          position: "fixed", top: 0, left: 0, right: 0,
          height: "4px", backgroundColor: "#06b6d4", zIndex: 9999
        }} />
      )}
      {/* Backend connection status indicator */}
      <div style={{
        position: "fixed", top: 16, left: "50%", transform: "translateX(-50%)", zIndex: 9999,
        display: "flex", alignItems: "center", gap: 6,
        padding: "4px 8px", borderRadius: 6,
        backgroundColor: "rgba(0, 0, 0, 0.5)", color: "#d1d5db",
        fontSize: 11, fontWeight: 400
      }}>
        <div style={{
          width: 6, height: 6, borderRadius: "50%",
          backgroundColor: ws ? "#10b981" : "#d1d5db"
        }} />
        {ws ? "Online" : "Reconnecting"}
      </div>
      {/* Save/Load buttons - minimal style */}
      <div style={{
        position: "fixed", top: "50%", transform: "translateY(-50%)", left: 20,
        zIndex: 9999, display: "flex", flexDirection: "column", gap: 6
      }}>
        <button onClick={handleSave} style={{
          padding: "6px 10px", borderRadius: 6,
          background: "rgba(0, 0, 0, 0.65)", color: "#d1d5db",
          border: "1px solid rgba(255, 255, 255, 0.1)", cursor: "pointer", fontWeight: 400,
          fontSize: 11, whiteSpace: "nowrap"
        }}>Save</button>
        <button onClick={handleLoad} style={{
          padding: "6px 10px", borderRadius: 6,
          background: "rgba(0, 0, 0, 0.65)", color: "#d1d5db",
          border: "1px solid rgba(255, 255, 255, 0.1)", cursor: "pointer", fontWeight: 400,
          fontSize: 11, whiteSpace: "nowrap"
        }}>Load</button>
      </div>
    </>
  )
}

export default function App() {
  return (
    <div style={{ position: "fixed", inset: 0 }}>
      <Tldraw persistenceKey="alphasurface">
        <AlphaSurfaceInner />
      </Tldraw>
    </div>
  )
}
