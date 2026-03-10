import { useEffect, useState } from "react"
import { Tldraw, useEditor, toRichText, getSnapshot, loadSnapshot, AssetRecordType, createShapeId } from "tldraw"
import "tldraw/tldraw.css"

// ── Singleton audio playback context ─────────────────────────────────────────
// Shared across all audio_response messages so chunks are scheduled back-to-back.
const _playback = {
  _ctx: null,
  get ctx() {
    if (!this._ctx) this._ctx = new AudioContext({ sampleRate: 24000 })
    return this._ctx
  },
  nextTime: 0,   // cursor: when the last scheduled chunk ends
  enabled: true, // controlled by 🔊/🔇 button
}

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
    // tldraw v4: arrow props.start/end are always {x,y} numbers.
    // Shape bindings are separate records created via editor.createBinding().
    case "bind_arrow": {
      if (p.fromShapeId && p.toShapeId) {
        const fromShape = editor.getShape(p.fromShapeId)
        const toShape = editor.getShape(p.toShapeId)
        if (fromShape && toShape) {
          const arrowId = createShapeId()
          // Place arrow at centroid of the two shapes
          const cx = (fromShape.x + toShape.x) / 2
          const cy = (fromShape.y + toShape.y) / 2
          editor.createShape({
            id: arrowId,
            type: "arrow",
            x: cx, y: cy,
            props: {
              start: { x: 0, y: 0 },
              end: { x: toShape.x - fromShape.x, y: toShape.y - fromShape.y },
              richText: toRichText(p.label ?? ""),
              color: p.color ?? "black",
              size: p.size ?? "m",
              arrowheadEnd: "arrow",
              arrowheadStart: "none",
            }
          })
          // Bind start terminal to fromShape
          editor.createBinding({
            type: "arrow",
            fromId: arrowId,
            toId: p.fromShapeId,
            props: {
              terminal: "start",
              normalizedAnchor: { x: 0.5, y: 0.5 },
              isExact: false,
              isPrecise: false,
            }
          })
          // Bind end terminal to toShape
          editor.createBinding({
            type: "arrow",
            fromId: arrowId,
            toId: p.toShapeId,
            props: {
              terminal: "end",
              normalizedAnchor: { x: 0.5, y: 0.5 },
              isExact: false,
              isPrecise: false,
            }
          })
        }
      }
      break
    }

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

    // ── Move shape to new position ────────────────────────────
    case "move_shape":
      if (p.shapeId) {
        const shape = editor.getShape(p.shapeId)
        if (shape) editor.updateShape({ id: p.shapeId, type: shape.type, x: p.x, y: p.y })
      }
      break

    // ── Update shape properties ───────────────────────────────
    case "update_shape":
      if (p.shapeId) {
        const shape = editor.getShape(p.shapeId)
        if (shape) {
          const updatedProps = { ...shape.props }
          if (p.text !== undefined) updatedProps.richText = toRichText(p.text)
          if (p.color !== undefined) updatedProps.color = p.color
          editor.updateShape({ id: p.shapeId, type: shape.type, props: updatedProps })
        }
      }
      break

    // ── Select shapes ─────────────────────────────────────────
    case "select_shapes":
      if (p.shapeIds && p.shapeIds.length > 0) editor.select(...p.shapeIds)
      break

    // ── Add freehand drawing ──────────────────────────────────
    case "add_draw":
      if (p.points && p.points.length > 0) {
        editor.createShape({
          type: "draw",
          x: p.x ?? 0, y: p.y ?? 0,
          props: {
            segments: [{ type: "free", points: p.points }],
            color: p.color ?? "black",
            size: p.size ?? "m",
            isComplete: true,
          }
        })
      }
      break

    // ── Audio response from Gemini ────────────────────────────
    case "audio_response": {
      if (!p.data || !_playback.enabled) break
      const raw = atob(p.data)
      const buf = new ArrayBuffer(raw.length)
      const view = new Uint8Array(buf)
      for (let i = 0; i < raw.length; i++) view[i] = raw.charCodeAt(i)

      // Resume context if browser suspended it (requires prior user gesture)
      if (_playback.ctx.state === "suspended") _playback.ctx.resume()

      const audioBuffer = _playback.ctx.createBuffer(1, buf.byteLength / 2, 24000)
      const channel = audioBuffer.getChannelData(0)
      const pcm = new Int16Array(buf)
      for (let i = 0; i < pcm.length; i++) channel[i] = pcm[i] / 32768

      const source = _playback.ctx.createBufferSource()
      source.buffer = audioBuffer
      source.connect(_playback.ctx.destination)

      // Schedule chunk immediately after the previous one ends.
      // If we've fallen behind (gap between Gemini turns), snap to now.
      const now = _playback.ctx.currentTime
      if (_playback.nextTime < now) _playback.nextTime = now
      source.start(_playback.nextTime)
      _playback.nextTime += audioBuffer.duration
      break
    }

    // ── AI status updates (thinking, listening, etc.) ─────────
    case "ai_status":
      // Backend sends status updates - just log for debugging
      // Could be used to show "AI thinking..." indicators in UI
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
  const [audioEnabled, setAudioEnabled] = useState(false)

  useEffect(() => {
    if (!editor) return  // Wait for editor to be ready
    
    let socket
    let retryDelay = 1000
    let retryTimeout
    let disposed = false  // Prevents zombie reconnects from StrictMode double-mount

    function connect() {
      if (disposed) return  // Don't connect if effect was cleaned up
      socket = new WebSocket("/ws")

      socket.onopen = () => {
        console.log("Connected to AlphaSurface backend")
        retryDelay = 1000  // reset backoff on success
        setWs(socket)
      }

      socket.onmessage = (event) => {
        if (disposed) return
        const message = JSON.parse(event.data)
        console.log("Incoming:", message.type, message.payload)
        setIndicator(true)
        setTimeout(() => setIndicator(false), 1500)
        handleCanvasMessage(editor, message)
      }

      socket.onerror = () => {}  // onclose handles it

      socket.onclose = () => {
        if (disposed) return  // Don't retry if cleanup already ran
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
      disposed = true
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

  useEffect(() => {
    if (!ws) return
    let audioContext, processor, source, stream

    async function startMic() {
      try {
        stream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false })
        audioContext = new AudioContext({ sampleRate: 16000 })
        source = audioContext.createMediaStreamSource(stream)
        processor = audioContext.createScriptProcessor(4096, 1, 1)
        processor.onaudioprocess = (e) => {
          if (ws.readyState !== WebSocket.OPEN) return
          const input = e.inputBuffer.getChannelData(0)
          // Send ALL frames (including silence) — Gemini's built-in auto-VAD needs
          // a continuous stream to reliably detect speech onset and offset.
          // Dropping silent frames confuses turn detection.
          const pcm16 = new Int16Array(input.length)
          for (let i = 0; i < input.length; i++) {
            pcm16[i] = Math.max(-32768, Math.min(32767, input[i] * 32768))
          }
          const base64 = btoa(String.fromCharCode(...new Uint8Array(pcm16.buffer)))
          ws.send(JSON.stringify({ type: "audio_chunk", payload: { data: base64 } }))
        }
        source.connect(processor)
        // Silent sink: keeps the audio graph ticking (onaudioprocess fires) but
        // gain=0 means mic is NOT routed to speakers — prevents echo feedback.
        const silentSink = audioContext.createGain()
        silentSink.gain.value = 0
        processor.connect(silentSink)
        silentSink.connect(audioContext.destination)
        console.log("Microphone active — streaming to backend")
      } catch (err) {
        console.warn("Mic unavailable:", err.message)
      }
    }

    startMic()

    return () => {
      processor?.disconnect()
      source?.disconnect()
      stream?.getTracks().forEach(t => t.stop())
      audioContext?.close()
    }
  }, [ws])

  useEffect(() => {
    _playback.enabled = audioEnabled
    // Resume AudioContext on first user interaction (browser autoplay policy)
    if (audioEnabled && _playback.ctx.state === "suspended") _playback.ctx.resume()
  }, [audioEnabled])

  useEffect(() => {
    if (!ws || !editor) return
    const interval = setInterval(async () => {
      if (ws.readyState !== WebSocket.OPEN) return
      const shapeIds = [...editor.getCurrentPageShapeIds()]
      if (shapeIds.length === 0) return
      // Wait for shapes to finish rendering before screenshotting
      await new Promise(r => setTimeout(r, 500))
      try {
        const { blob } = await editor.toImage(shapeIds, { 
          format: "png",
          background: true,
          padding: 32
        })
        const reader = new FileReader()
        reader.onloadend = () => {
          if (ws.readyState !== WebSocket.OPEN) return
          const base64 = reader.result.split(",")[1]
          ws.send(JSON.stringify({ type: "canvas_image", payload: { data: base64 } }))
        }
        reader.readAsDataURL(blob)
      } catch (err) {
        // Silently skip — shape may still be rendering
      }
    }, 15000)
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
      {/* Audio toggle button */}
      <button
        onClick={() => setAudioEnabled(v => !v)}
        style={{
          position: "fixed", top: 16, right: 20, zIndex: 9999,
          background: "rgba(0,0,0,0.5)", border: "1px solid rgba(255,255,255,0.1)",
          borderRadius: 6, padding: "4px 8px", cursor: "pointer",
          fontSize: 16, lineHeight: 1
        }}
        title={audioEnabled ? "Mute AI voice" : "Enable AI voice"}
      >
        {audioEnabled ? "🔊" : "🔇"}
      </button>
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
