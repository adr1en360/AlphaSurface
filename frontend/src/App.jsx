import { useEffect, useRef, useState } from "react"
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
  nextTime: 0,      // cursor: when the last scheduled chunk ends
  enabled: true,    // controlled by 🔊/🔇 button
  sources: [],      // track active source nodes so we can stop them on interrupt
}

// Stop all currently-playing AI audio immediately (called on ai_interrupted)
function flushAudioPlayback() {
  for (const src of _playback.sources) {
    try { src.stop() } catch (_) {}
  }
  _playback.sources = []
  _playback.nextTime = 0
}

// Handler for incoming WebSocket messages - extracted outside component to avoid stale closures
function handleCanvasMessage(editor, message) {
  if (!editor) return
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
          geo: p.geo ?? "rectangle",
          w: p.w ?? 200,
          h: p.h ?? 120,
          richText: toRichText(p.text ?? ""),
          color: p.color ?? "blue",
          fill: p.fill ?? "semi",
          dash: p.dash ?? "draw",
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
          arrowheadEnd: p.arrowhead ?? "arrow",
          arrowheadStart: "none",
        }
      })
      break

    // ── Bind Arrow (shape-to-shape connection) ────────────────
    case "bind_arrow": {
      if (p.fromShapeId && p.toShapeId) {
        const fromShape = editor.getShape(p.fromShapeId)
        const toShape = editor.getShape(p.toShapeId)
        if (fromShape && toShape) {
          const arrowId = createShapeId()
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

    // ── Embed (YouTube, Figma, CodeSandbox, Google Maps, etc.) ─
    // tldraw supports iframes for a curated list of services.
    // Full list: https://tldraw.dev/reference/tldraw/TLEmbedShape
    case "add_embed":
      editor.createShape({
        type: "embed",
        x: p.x ?? 200, y: p.y ?? 200,
        props: {
          url: p.url,
          w: p.w ?? 560,
          h: p.h ?? 315,
        }
      })
      break

    // ── Bookmark (rich link card — title, desc, thumbnail) ────
    case "add_bookmark":
      editor.createShape({
        type: "bookmark",
        x: p.x ?? 200, y: p.y ?? 200,
        props: {
          url: p.url,
          w: 300,
          h: 160,
          assetId: null,
        }
      })
      break

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
      const bytes = new Uint8Array(buf)
      for (let i = 0; i < raw.length; i++) bytes[i] = raw.charCodeAt(i)

      if (_playback.ctx.state === "suspended") _playback.ctx.resume()

      const audioBuffer = _playback.ctx.createBuffer(1, buf.byteLength / 2, 24000)
      const channel = audioBuffer.getChannelData(0)
      const pcm = new Int16Array(buf)
      for (let i = 0; i < pcm.length; i++) channel[i] = pcm[i] / 32768

      const source = _playback.ctx.createBufferSource()
      source.buffer = audioBuffer
      source.connect(_playback.ctx.destination)

      const now = _playback.ctx.currentTime
      if (_playback.nextTime < now) _playback.nextTime = now
      source.start(_playback.nextTime)
      _playback.nextTime += audioBuffer.duration

      // Track source so we can stop it on barge-in interrupt
      _playback.sources.push(source)
      source.onended = () => {
        _playback.sources = _playback.sources.filter(s => s !== source)
      }
      break
    }

    // ── Gemini barge-in: stop playing mid-sentence ────────────
    // Fires when user speaks over the AI — flush queued audio immediately.
    case "ai_interrupted":
      flushAudioPlayback()
      break

    // ── AI status updates ─────────────────────────────────────
    // Handled in AlphaSurfaceInner via setAiStatus — not here.
    case "ai_status":
    case "canvas_snapshot":
      break

    default:
      console.warn("Unknown message type:", message.type)
  }
}

// ── Status pill config ────────────────────────────────────────────────────────
const STATUS_CONFIG = {
  idle:         { label: "Listening",   dot: "#10b981", pulse: false },
  thinking:     { label: "Thinking…",   dot: "#f59e0b", pulse: true  },
  speaking:     { label: "Speaking",    dot: "#06b6d4", pulse: true  },
  disconnected: { label: "Offline",     dot: "#6b7280", pulse: false },
}

function AlphaSurfaceInner() {
  const editor = useEditor()
  const [ws, setWs] = useState(null)
  const [indicator, setIndicator] = useState(false)  // top stripe on canvas action
  const [audioEnabled, setAudioEnabled] = useState(false)
  const [aiStatus, setAiStatus] = useState("disconnected")
  const wsRef = useRef(null)  // always-current ref for audio processor callback

  // ── WebSocket connection with exponential backoff ─────────────────────────
  useEffect(() => {
    if (!editor) return

    let socket
    let retryDelay = 1000
    let retryTimeout
    let disposed = false

    function connect() {
      if (disposed) return
      socket = new WebSocket("/ws")
      wsRef.current = socket

      socket.onopen = () => {
        console.log("Connected to AlphaSurface backend")
        retryDelay = 1000
        setWs(socket)
        setAiStatus("idle")
      }

      socket.onmessage = (event) => {
        if (disposed) return
        const message = JSON.parse(event.data)

        // Route ai_status updates to React state; everything else to canvas
        if (message.type === "ai_status") {
          setAiStatus(message.payload?.status ?? "idle")
          return
        }
        if (message.type === "ai_interrupted") {
          flushAudioPlayback()
          setAiStatus("idle")
          return
        }

        // Flash the top action stripe for any canvas mutation
        const isCanvasAction = message.type !== "canvas_snapshot"
        if (isCanvasAction) {
          setIndicator(true)
          setTimeout(() => setIndicator(false), 1500)
        }

        handleCanvasMessage(editor, message)
      }

      socket.onerror = () => {}

      socket.onclose = () => {
        if (disposed) return
        console.log(`Disconnected. Retrying in ${retryDelay / 1000}s…`)
        setWs(null)
        wsRef.current = null
        setAiStatus("disconnected")
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

  // ── Canvas shape inventory — backend needs real shape IDs ─────────────────
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

  // ── Microphone → WebSocket audio stream ───────────────────────────────────
  // echoCancellation MUST be true — without it the mic hears the AI's own voice
  // and Gemini never detects a real barge-in from the user.
  useEffect(() => {
    if (!ws) return
    let audioContext, processor, source, stream

    async function startMic() {
      try {
        stream = await navigator.mediaDevices.getUserMedia({
          audio: {
            echoCancellation: true,   // KEY: prevents AI voice feeding back as user speech
            noiseSuppression: true,
            autoGainControl: true,
            sampleRate: 16000,
            channelCount: 1,
          },
          video: false,
        })
        audioContext = new AudioContext({ sampleRate: 16000 })
        source = audioContext.createMediaStreamSource(stream)
        processor = audioContext.createScriptProcessor(4096, 1, 1)

        processor.onaudioprocess = (e) => {
          const currentWs = wsRef.current
          if (!currentWs || currentWs.readyState !== WebSocket.OPEN) return
          const input = e.inputBuffer.getChannelData(0)
          // Send continuous stream — Gemini's auto-VAD needs silence frames too
          // to reliably detect speech onset/offset and trigger barge-in.
          const pcm16 = new Int16Array(input.length)
          for (let i = 0; i < input.length; i++) {
            pcm16[i] = Math.max(-32768, Math.min(32767, input[i] * 32768))
          }
          const base64 = btoa(String.fromCharCode(...new Uint8Array(pcm16.buffer)))
          currentWs.send(JSON.stringify({ type: "audio_chunk", payload: { data: base64 } }))
        }

        source.connect(processor)
        // Silent sink: keeps audio graph ticking but mic NOT routed to speakers
        const silentSink = audioContext.createGain()
        silentSink.gain.value = 0
        processor.connect(silentSink)
        silentSink.connect(audioContext.destination)
        console.log("Mic active with echo cancellation — streaming to backend")
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

  // ── Audio playback toggle ─────────────────────────────────────────────────
  useEffect(() => {
    _playback.enabled = audioEnabled
    if (audioEnabled && _playback.ctx.state === "suspended") _playback.ctx.resume()
  }, [audioEnabled])

  // ── Canvas screenshot → Gemini vision (rate-limited) ─────────────────────
  useEffect(() => {
    if (!ws || !editor) return
    const interval = setInterval(async () => {
      if (ws.readyState !== WebSocket.OPEN) return
      const shapeIds = [...editor.getCurrentPageShapeIds()]
      if (shapeIds.length === 0) return
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
      } catch (_) {
        // Shape may still be rendering — skip silently
      }
    }, 15000)
    return () => clearInterval(interval)
  }, [ws, editor])

  // ── Save / Load session ───────────────────────────────────────────────────
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
      reader.onload = (ev) => loadSnapshot(editor.store, JSON.parse(ev.target.result))
      reader.readAsText(file)
    }
    input.click()
  }

  // ── Render ────────────────────────────────────────────────────────────────
  const status = STATUS_CONFIG[aiStatus] ?? STATUS_CONFIG.disconnected

  return (
    <>
      {/* Top action stripe — flashes on every canvas mutation */}
      {indicator && (
        <div style={{
          position: "fixed", top: 0, left: 0, right: 0,
          height: "3px", background: "linear-gradient(90deg, #06b6d4, #8b5cf6)",
          zIndex: 9999, animation: "pulse 0.5s ease-out"
        }} />
      )}

      {/* AI status pill — top center */}
      <div style={{
        position: "fixed", top: 14, left: "50%", transform: "translateX(-50%)",
        zIndex: 9999, display: "flex", alignItems: "center", gap: 7,
        padding: "5px 11px", borderRadius: 999,
        background: "rgba(10, 10, 10, 0.6)",
        backdropFilter: "blur(8px)",
        border: "1px solid rgba(255,255,255,0.08)",
        color: "#d1d5db", fontSize: 11, fontWeight: 500,
        userSelect: "none",
      }}>
        <div style={{
          width: 7, height: 7, borderRadius: "50%",
          background: status.dot,
          boxShadow: status.pulse ? `0 0 6px ${status.dot}` : "none",
          animation: status.pulse ? "statusPulse 1.2s ease-in-out infinite" : "none",
        }} />
        {status.label}
      </div>

      {/* Audio toggle — top right */}
      <button
        onClick={() => setAudioEnabled(v => !v)}
        style={{
          position: "fixed", top: 14, right: 20, zIndex: 9999,
          background: "rgba(10,10,10,0.6)", backdropFilter: "blur(8px)",
          border: "1px solid rgba(255,255,255,0.08)",
          borderRadius: 8, padding: "5px 9px", cursor: "pointer",
          fontSize: 15, lineHeight: 1,
        }}
        title={audioEnabled ? "Mute AI voice" : "Enable AI voice"}
      >
        {audioEnabled ? "🔊" : "🔇"}
      </button>

      {/* Save / Load — left side */}
      <div style={{
        position: "fixed", top: "50%", transform: "translateY(-50%)", left: 18,
        zIndex: 9999, display: "flex", flexDirection: "column", gap: 6,
      }}>
        {[["Save", handleSave], ["Load", handleLoad]].map(([label, fn]) => (
          <button key={label} onClick={fn} style={{
            padding: "6px 10px", borderRadius: 7,
            background: "rgba(10,10,10,0.6)", backdropFilter: "blur(8px)",
            color: "#d1d5db", border: "1px solid rgba(255,255,255,0.08)",
            cursor: "pointer", fontSize: 11, fontWeight: 500,
          }}>
            {label}
          </button>
        ))}
      </div>

      {/* Keyframe animations injected as a style tag */}
      <style>{`
        @keyframes statusPulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.4; }
        }
      `}</style>
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
