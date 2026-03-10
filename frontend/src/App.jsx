import { useEffect, useRef, useState, useCallback } from "react"
import { Tldraw, useEditor, toRichText, getSnapshot, loadSnapshot, AssetRecordType, createShapeId } from "tldraw"
import "tldraw/tldraw.css"

// ── Audio playback singleton ──────────────────────────────────────────────────
const _playback = {
  _ctx: null,
  get ctx() {
    if (!this._ctx) this._ctx = new AudioContext({ sampleRate: 24000 })
    return this._ctx
  },
  nextTime: 0,
  enabled: false,
  sources: [],
}

function flushAudioPlayback() {
  for (const s of _playback.sources) { try { s.stop() } catch (_) {} }
  _playback.sources = []
  _playback.nextTime = 0
}

// ── Canvas message handler ────────────────────────────────────────────────────
function handleCanvasMessage(editor, message) {
  if (!editor) return
  const p = message.payload

  switch (message.type) {

    case "add_text":
      editor.createShape({
        type: "text", x: p.x ?? 200, y: p.y ?? 200,
        props: { richText: toRichText(p.text), size: p.size ?? "m", color: p.color ?? "black" }
      })
      break

    case "add_note":
      editor.createShape({
        type: "note", x: p.x ?? 300, y: p.y ?? 300,
        props: { richText: toRichText(p.text), color: p.color ?? "yellow", size: p.size ?? "m" }
      })
      break

    case "add_geo":
      editor.createShape({
        type: "geo", x: p.x ?? 200, y: p.y ?? 200,
        props: {
          geo: p.geo ?? "rectangle",
          w: p.w ?? 200, h: p.h ?? 120,
          richText: toRichText(p.text ?? ""),
          color: p.color ?? "blue",
          fill: p.fill ?? "semi",
          dash: p.dash ?? "draw",
          size: p.size ?? "m",
        }
      })
      break

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

    case "bind_arrow": {
      const fromShape = editor.getShape(p.fromShapeId)
      const toShape = editor.getShape(p.toShapeId)
      if (!fromShape || !toShape) break
      const arrowId = createShapeId()
      const cx = (fromShape.x + toShape.x) / 2
      const cy = (fromShape.y + toShape.y) / 2
      editor.createShape({
        id: arrowId, type: "arrow", x: cx, y: cy,
        props: {
          start: { x: 0, y: 0 },
          end: { x: toShape.x - fromShape.x, y: toShape.y - fromShape.y },
          richText: toRichText(p.label ?? ""),
          color: p.color ?? "black", size: p.size ?? "m",
          arrowheadEnd: "arrow", arrowheadStart: "none",
        }
      })
      editor.createBinding({
        type: "arrow", fromId: arrowId, toId: p.fromShapeId,
        props: { terminal: "start", normalizedAnchor: { x: 0.5, y: 0.5 }, isExact: false, isPrecise: false }
      })
      editor.createBinding({
        type: "arrow", fromId: arrowId, toId: p.toShapeId,
        props: { terminal: "end", normalizedAnchor: { x: 0.5, y: 0.5 }, isExact: false, isPrecise: false }
      })
      break
    }

    case "add_embed":
      editor.createShape({
        type: "embed", x: p.x ?? 200, y: p.y ?? 200,
        props: { url: p.url, w: p.w ?? 560, h: p.h ?? 315 }
      })
      break

    case "add_bookmark":
      editor.createShape({
        type: "bookmark", x: p.x ?? 200, y: p.y ?? 200,
        props: { url: p.url, w: 300, h: 160, assetId: null }
      })
      break

    case "clear_canvas": {
      const allIds = [...editor.getCurrentPageShapeIds()]
      if (allIds.length > 0) editor.deleteShapes(allIds)
      break
    }

    case "delete_shapes":
      if (p.shapeIds?.length > 0) editor.deleteShapes(p.shapeIds)
      break

    case "zoom_to_fit":
      editor.zoomToFit()
      break

    case "focus_shape": {
      const shape = p.shapeId && editor.getShape(p.shapeId)
      if (shape) { editor.zoomToSelection([p.shapeId]); editor.select(p.shapeId) }
      break
    }

    case "move_shape": {
      const shape = p.shapeId && editor.getShape(p.shapeId)
      if (shape) editor.updateShape({ id: p.shapeId, type: shape.type, x: p.x, y: p.y })
      break
    }

    case "update_shape": {
      const shape = p.shapeId && editor.getShape(p.shapeId)
      if (shape) {
        const props = { ...shape.props }
        if (p.text !== undefined) props.richText = toRichText(p.text)
        if (p.color !== undefined) props.color = p.color
        editor.updateShape({ id: p.shapeId, type: shape.type, props })
      }
      break
    }

    case "select_shapes":
      if (p.shapeIds?.length > 0) editor.select(...p.shapeIds)
      break

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
      _playback.sources.push(source)
      source.onended = () => { _playback.sources = _playback.sources.filter(s => s !== source) }
      break
    }

    case "ai_interrupted":
      flushAudioPlayback()
      break

    case "ai_status":
    case "canvas_snapshot":
    case "config_ack":
      break

    default:
      console.warn("[AlphaSurface] Unknown message:", message.type)
  }
}

// ── Status config ─────────────────────────────────────────────────────────────
const STATUS = {
  idle:         { label: "Active",     dot: "#10b981", pulse: false },
  thinking:     { label: "Thinking…",  dot: "#f59e0b", pulse: true  },
  speaking:     { label: "Speaking",   dot: "#06b6d4", pulse: true  },
  disconnected: { label: "Offline",    dot: "#6b7280", pulse: false },
}

// ═══════════════════════════════════════════════════════════════════════════════
// LAUNCH SCREEN
// ═══════════════════════════════════════════════════════════════════════════════
function LaunchScreen({ onLaunch }) {
  const [mode, setMode] = useState("think")
  const [voiceEnabled, setVoiceEnabled] = useState(true)
  const [webSearch, setWebSearch] = useState(false)
  const [mcpInput, setMcpInput] = useState("")
  const [mcps, setMcps] = useState([])
  const [showAdvanced, setShowAdvanced] = useState(false)

  const addMcp = () => {
    const url = mcpInput.trim()
    if (url && !mcps.includes(url)) { setMcps(m => [...m, url]); setMcpInput("") }
  }

  return (
    <div style={{
      position: "fixed", inset: 0,
      background: "radial-gradient(ellipse at 60% 40%, #0f172a 0%, #020617 100%)",
      display: "flex", alignItems: "flex-start", justifyContent: "center",
      overflowY: "auto",
      padding: "24px 0",
      fontFamily: "'Inter', 'Segoe UI', sans-serif",
      color: "#e2e8f0",
    }}>
      {/* Ambient glow */}
      <div style={{
        position: "absolute", inset: 0, overflow: "hidden", pointerEvents: "none"
      }}>
        <div style={{
          position: "absolute", top: "20%", left: "30%",
          width: 600, height: 600,
          background: "radial-gradient(circle, rgba(139,92,246,0.08) 0%, transparent 70%)",
          transform: "translate(-50%,-50%)",
        }} />
        <div style={{
          position: "absolute", top: "70%", left: "70%",
          width: 400, height: 400,
          background: "radial-gradient(circle, rgba(6,182,212,0.06) 0%, transparent 70%)",
          transform: "translate(-50%,-50%)",
        }} />
      </div>

      <div style={{ position: "relative", zIndex: 1, width: "100%", maxWidth: 520, padding: "0 24px" }}>
        {/* Logo */}
          <div style={{ textAlign: "center", marginBottom: 20 }}>
          <div style={{ fontSize: 30, fontWeight: 700, letterSpacing: "-1px", marginBottom: 4 }}>
            <span style={{ color: "#8b5cf6" }}>Alpha</span>
            <span style={{ color: "#e2e8f0" }}>Surface</span>
          </div>
          <div style={{ fontSize: 13, color: "#64748b", fontWeight: 400 }}>
            AI that thinks alongside you — not for you
          </div>
        </div>

        {/* Card */}
        <div style={{
          background: "rgba(15, 23, 42, 0.8)",
          border: "1px solid rgba(148,163,184,0.1)",
          borderRadius: 16, padding: "20px 24px",
          backdropFilter: "blur(12px)",
          boxShadow: "0 25px 50px rgba(0,0,0,0.5)",
        }}>

          <div style={{ marginBottom: 16 }}>
            <div style={{ fontSize: 11, fontWeight: 600, color: "#64748b", letterSpacing: "0.08em", marginBottom: 10, textTransform: "uppercase" }}>
              Session Mode
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
              {[
                {
                  id: "think",
                  title: "Think Mode",
                  subtitle: "Solo thinking · Student · Research",
                  icon: "🧠",
                  desc: "Blank canvas. AI injects Sarkar provocations — open questions, missing links — as you think.",
                },
                {
                  id: "explain",
                  title: "Explain Mode",
                  subtitle: "Teacher · Presenter · Live lecture",
                  icon: "📡",
                  desc: "Pre-loaded docs. AI surfaces relevant material and generates visuals without interrupting.",
                },
              ].map(m => (
                <button
                  key={m.id}
                  onClick={() => setMode(m.id)}
                  style={{
                    background: mode === m.id
                      ? "rgba(139,92,246,0.15)"
                      : "rgba(30,41,59,0.6)",
                    border: mode === m.id
                      ? "1px solid rgba(139,92,246,0.5)"
                      : "1px solid rgba(148,163,184,0.08)",
                    borderRadius: 10, padding: "10px 12px",
                    cursor: "pointer", textAlign: "left",
                    color: "#e2e8f0",
                    transition: "all 0.15s ease",
                  }}
                >
                  <div style={{ fontSize: 16, marginBottom: 4 }}>{m.icon}</div>
                  <div style={{ fontSize: 11, color: mode === m.id ? "#c4b5fd" : "#e2e8f0", marginBottom: 2 }}>{m.title}</div>
                  <div style={{ fontSize: 10, color: "#64748b", marginBottom: 4 }}>{m.subtitle}</div>
                  <div style={{ fontSize: 10, color: "#475569", lineHeight: 1.4 }}>{m.desc}</div>
                </button>
              ))}
            </div>
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: 8, marginBottom: 14 }}>
            {[
              {
                label: "Voice", sublabel: "Mic + AI audio responses",
                value: voiceEnabled, toggle: () => setVoiceEnabled(v => !v),
                icon: voiceEnabled ? "🎙️" : "🔇",
              },
              {
                label: "Web Search", sublabel: "AI can look things up and bookmark results",
                value: webSearch, toggle: () => setWebSearch(v => !v),
                icon: "🔍",
              },
            ].map(t => (
              <div
                key={t.label}
                onClick={t.toggle}
                style={{
                  display: "flex", alignItems: "center", gap: 10,
                  padding: "9px 12px", borderRadius: 10, cursor: "pointer",
                  background: t.value ? "rgba(139,92,246,0.08)" : "rgba(30,41,59,0.4)",
                  border: t.value ? "1px solid rgba(139,92,246,0.25)" : "1px solid rgba(148,163,184,0.07)",
                  transition: "all 0.15s ease",
                }}
              >
                <span style={{ fontSize: 18, width: 24, textAlign: "center" }}>{t.icon}</span>
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 13, fontWeight: 500, color: "#e2e8f0" }}>{t.label}</div>
                  <div style={{ fontSize: 11, color: "#64748b" }}>{t.sublabel}</div>
                </div>
                {/* Pill toggle */}
                <div style={{
                  width: 36, height: 20, borderRadius: 10,
                  background: t.value ? "#8b5cf6" : "#334155",
                  position: "relative", transition: "background 0.15s ease",
                  flexShrink: 0,
                }}>
                  <div style={{
                    position: "absolute", top: 2,
                    left: t.value ? 18 : 2,
                    width: 16, height: 16, borderRadius: "50%",
                    background: "#fff", transition: "left 0.15s ease",
                  }} />
                </div>
              </div>
            ))}
          </div>

          <div style={{ marginBottom: 14 }}>
            <button
              onClick={() => setShowAdvanced(v => !v)}
              style={{
                background: "none", border: "none", cursor: "pointer",
                color: "#64748b", fontSize: 12, padding: 0,
                display: "flex", alignItems: "center", gap: 6,
              }}
            >
              <span style={{ transform: showAdvanced ? "rotate(90deg)" : "none", display: "inline-block", transition: "transform 0.15s" }}>▶</span>
              Advanced · Custom MCP servers
            </button>
            {showAdvanced && (
              <div style={{ marginTop: 12, padding: "14px", borderRadius: 10, background: "rgba(15,23,42,0.6)", border: "1px solid rgba(148,163,184,0.07)" }}>
                <div style={{ fontSize: 11, color: "#64748b", marginBottom: 10 }}>
                  Add MCP server URLs. These extend what the AI can do (databases, APIs, custom tools).
                </div>
                <div style={{ display: "flex", gap: 8 }}>
                  <input
                    value={mcpInput}
                    onChange={e => setMcpInput(e.target.value)}
                    onKeyDown={e => e.key === "Enter" && addMcp()}
                    placeholder="https://mcp.example.com/sse"
                    style={{
                      flex: 1, background: "rgba(30,41,59,0.6)",
                      border: "1px solid rgba(148,163,184,0.1)", borderRadius: 7,
                      padding: "8px 10px", color: "#e2e8f0", fontSize: 12,
                      outline: "none",
                    }}
                  />
                  <button
                    onClick={addMcp}
                    style={{
                      background: "#334155", border: "none", borderRadius: 7,
                      padding: "8px 12px", cursor: "pointer", color: "#94a3b8", fontSize: 12,
                    }}
                  >Add</button>
                </div>
                {mcps.length > 0 && (
                  <div style={{ marginTop: 10, display: "flex", flexWrap: "wrap", gap: 6 }}>
                    {mcps.map(url => (
                      <div key={url} style={{
                        background: "rgba(139,92,246,0.1)", border: "1px solid rgba(139,92,246,0.2)",
                        borderRadius: 6, padding: "3px 8px", fontSize: 11, color: "#c4b5fd",
                        display: "flex", alignItems: "center", gap: 6,
                      }}>
                        {url.replace("https://", "")}
                        <span onClick={() => setMcps(m => m.filter(u => u !== url))} style={{ cursor: "pointer", color: "#64748b" }}>×</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Launch button */}
          <button
            onClick={() => onLaunch({ mode, voiceEnabled, webSearch, mcps })}
            style={{
              width: "100%", padding: "11px",
              background: "linear-gradient(135deg, #8b5cf6, #6d28d9)",
              border: "none", borderRadius: 10, cursor: "pointer",
              color: "#fff", fontSize: 14, fontWeight: 600, letterSpacing: "0.02em",
              boxShadow: "0 4px 24px rgba(139,92,246,0.35)",
              transition: "all 0.15s ease",
            }}
            onMouseEnter={e => e.currentTarget.style.transform = "translateY(-1px)"}
            onMouseLeave={e => e.currentTarget.style.transform = "none"}
          >
            Launch Canvas →
          </button>
        </div>

        <div style={{ textAlign: "center", marginTop: 12, fontSize: 10, color: "#1e293b" }}>
          AlphaSurface · Built for Google Live API Hackathon
        </div>
      </div>

      <style>{`
        * { box-sizing: border-box; }
        input::placeholder { color: #334155; }
      `}</style>
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
// CANVAS INNER  (mounts inside <Tldraw>)
// ═══════════════════════════════════════════════════════════════════════════════
function AlphaSurfaceInner({ config }) {
  const editor = useEditor()
  const [ws, setWs] = useState(null)
  const [indicator, setIndicator] = useState(false)
  const [aiStatus, setAiStatus] = useState("disconnected")
  const [muted, setMuted] = useState(false)
  const wsRef = useRef(null)
  const prevShapeCount = useRef(0)
  const mutedRef = useRef(false)

  // ── WebSocket connection ────────────────────────────────────────────────────
  useEffect(() => {
    if (!editor) return
    let socket, retryDelay = 1000, retryTimeout, disposed = false

    function connect() {
      if (disposed) return
      socket = new WebSocket("/ws")
      wsRef.current = socket

      socket.onopen = () => {
        retryDelay = 1000
        setWs(socket)
        setAiStatus("idle")
        // Send launch config to backend
        socket.send(JSON.stringify({
          type: "set_config",
          payload: { mode: config.mode, webSearch: config.webSearch, mcps: config.mcps }
        }))
      }

      socket.onmessage = (event) => {
        if (disposed) return
        const message = JSON.parse(event.data)
        if (message.type === "ai_status") { setAiStatus(message.payload?.status ?? "idle"); return }
        if (message.type === "ai_interrupted") { flushAudioPlayback(); setAiStatus("idle"); return }
        if (message.type !== "canvas_snapshot" && message.type !== "config_ack") {
          setIndicator(true)
          setTimeout(() => setIndicator(false), 1200)
        }
        handleCanvasMessage(editor, message)
      }

      socket.onerror = () => {}
      socket.onclose = () => {
        if (disposed) return
        setWs(null); wsRef.current = null; setAiStatus("disconnected")
        retryTimeout = setTimeout(() => { retryDelay = Math.min(retryDelay * 2, 30000); connect() }, retryDelay)
      }
    }

    connect()
    return () => { disposed = true; clearTimeout(retryTimeout); socket?.close() }
  }, [editor])

  // ── Rich canvas snapshot → backend (includes shape bounds) ─────────────────
  // Also detects when user adds/removes shapes so we can snapshot immediately.
  useEffect(() => {
    if (!ws || !editor) return

    const sendSnapshot = () => {
      if (ws.readyState !== WebSocket.OPEN) return
      const shapeIds = [...editor.getCurrentPageShapeIds()]
      if (shapeIds.length === 0) return
      const shapes = shapeIds.map(id => {
        const s = editor.getShape(id)
        const b = editor.getShapePageBounds(id)
        return {
          id: id.toString(),
          type: s?.type ?? "unknown",
          x: Math.round(b?.x ?? 0),
          y: Math.round(b?.y ?? 0),
          w: Math.round(b?.w ?? 100),
          h: Math.round(b?.h ?? 60),
        }
      })
      ws.send(JSON.stringify({
        type: "canvas_snapshot",
        payload: { shapes, shape_count: shapes.length }
      }))
    }

    // Periodic snapshot every 3s
    const interval = setInterval(sendSnapshot, 3000)

    // Immediate snapshot on any store change (shape added/removed by user)
    // Debounced so rapid drawing doesn't spam
    let debounce
    const unsub = editor.store.listen(() => {
      const count = editor.getCurrentPageShapeIds().size
      if (count !== prevShapeCount.current) {
        prevShapeCount.current = count
        clearTimeout(debounce)
        debounce = setTimeout(sendSnapshot, 400)
      }
    }, { scope: "document" })

    return () => { clearInterval(interval); clearTimeout(debounce); unsub() }
  }, [ws, editor])

  // ── Microphone → backend (echoCancellation prevents barge-in loop) ─────────
  useEffect(() => {
    if (!ws || !config.voiceEnabled) return
    let audioContext, processor, source, stream

    async function startMic() {
      try {
        stream = await navigator.mediaDevices.getUserMedia({
          audio: {
            echoCancellation: true,   // CRITICAL: without this, AI hears itself and can't barge-in
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
          if (mutedRef.current) return
          const input = e.inputBuffer.getChannelData(0)
          const pcm16 = new Int16Array(input.length)
          for (let i = 0; i < input.length; i++) {
            pcm16[i] = Math.max(-32768, Math.min(32767, input[i] * 32768))
          }
          const b64 = btoa(String.fromCharCode(...new Uint8Array(pcm16.buffer)))
          currentWs.send(JSON.stringify({ type: "audio_chunk", payload: { data: b64 } }))
        }
        source.connect(processor)
        const silentSink = audioContext.createGain()
        silentSink.gain.value = 0
        processor.connect(silentSink)
        silentSink.connect(audioContext.destination)
      } catch (err) {
        console.warn("[AlphaSurface] Mic error:", err.message)
      }
    }

    startMic()
    return () => {
      processor?.disconnect(); source?.disconnect()
      stream?.getTracks().forEach(t => t.stop()); audioContext?.close()
    }
  }, [ws, config.voiceEnabled])

  // ── Audio playback (voice on by default if voiceEnabled in config) ─────────
  useEffect(() => {
    _playback.enabled = config.voiceEnabled
    if (config.voiceEnabled && _playback.ctx.state === "suspended") _playback.ctx.resume()
  }, [config.voiceEnabled])

  // ── Canvas screenshot → Gemini vision ─────────────────────────────────────
  // Also triggers immediately when shapes change (catches marker/pen drawings)
  useEffect(() => {
    if (!ws || !editor) return

    const captureAndSend = async () => {
      if (ws.readyState !== WebSocket.OPEN) return
      const shapeIds = [...editor.getCurrentPageShapeIds()]
      if (shapeIds.length === 0) return
      await new Promise(r => setTimeout(r, 600)) // let shapes finish rendering
      try {
        const { blob } = await editor.toImage(shapeIds, { format: "jpeg", quality: 0.65, background: true, padding: 32 })
        const reader = new FileReader()
        reader.onloadend = () => {
          if (ws.readyState !== WebSocket.OPEN) return
          ws.send(JSON.stringify({ type: "canvas_image", payload: { data: reader.result.split(",")[1], mime: "image/jpeg" } }))
        }
        reader.readAsDataURL(blob)
      } catch (_) {}
    }

    // Send every 12s
    const interval = setInterval(captureAndSend, 12000)

    // Also capture immediately when shapes change (catches freehand pen/marker)
    let debounce
    const unsub = editor.store.listen(() => {
      clearTimeout(debounce)
      debounce = setTimeout(captureAndSend, 4000)
    }, { scope: "document" })

    return () => { clearInterval(interval); clearTimeout(debounce); unsub() }
  }, [ws, editor])

  // ── Save / Load ────────────────────────────────────────────────────────────
  const handleSave = () => {
    const blob = new Blob([JSON.stringify(getSnapshot(editor.store))], { type: "application/json" })
    const url = URL.createObjectURL(blob)
    Object.assign(document.createElement("a"), { href: url, download: "alphasurface.tldr" }).click()
    URL.revokeObjectURL(url)
  }
  const handleLoad = () => {
    const input = Object.assign(document.createElement("input"), { type: "file", accept: ".tldr" })
    input.onchange = e => {
      const reader = new FileReader()
      reader.onload = ev => loadSnapshot(editor.store, JSON.parse(ev.target.result))
      reader.readAsText(e.target.files[0])
    }
    input.click()
  }

  const status = STATUS[aiStatus] ?? STATUS.disconnected

  return (
    <>
      {/* Top action stripe */}
      {indicator && (
        <div style={{
          position: "fixed", top: 0, left: 0, right: 0, height: 3, zIndex: 9999,
          background: "linear-gradient(90deg, #8b5cf6, #06b6d4)",
        }} />
      )}

      {/* ── Status pill ── */}
      <button
        onClick={() => {
          const next = !muted
          setMuted(next)
          mutedRef.current = next
          _playback.enabled = !next
          if (!next && _playback.ctx.state === "suspended") _playback.ctx.resume()
          if (next) flushAudioPlayback()
        }}
        title={muted ? "Click to unmute" : "Click to mute"}
        style={{
          position: "fixed", top: 12, left: "50%", transform: "translateX(-50%)",
          zIndex: 9999, display: "flex", alignItems: "center", gap: 0,
          padding: 0, borderRadius: 999,
          background: "rgba(6,6,8,0.78)",
          backdropFilter: "blur(16px)", WebkitBackdropFilter: "blur(16px)",
          border: "1px solid rgba(255,255,255,0.06)",
          boxShadow: "0 2px 12px rgba(0,0,0,0.45), inset 0 1px 0 rgba(255,255,255,0.03)",
          fontFamily: "'Inter','Segoe UI',system-ui,sans-serif",
          fontSize: 10, fontWeight: 500, letterSpacing: "0.02em",
          userSelect: "none", cursor: "pointer", outline: "none", WebkitAppearance: "none",
          transition: "border-color 0.25s ease, box-shadow 0.25s ease",
        }}
        onMouseEnter={e => {
          e.currentTarget.style.borderColor = "rgba(255,255,255,0.13)"
          e.currentTarget.style.boxShadow = "0 2px 20px rgba(0,0,0,0.55), inset 0 1px 0 rgba(255,255,255,0.05)"
        }}
        onMouseLeave={e => {
          e.currentTarget.style.borderColor = "rgba(255,255,255,0.06)"
          e.currentTarget.style.boxShadow = "0 2px 12px rgba(0,0,0,0.45), inset 0 1px 0 rgba(255,255,255,0.03)"
        }}
      >
        {/* AI state — always visible */}
        <div style={{ display: "flex", alignItems: "center", gap: 6, padding: "5px 10px 5px 13px" }}>
          <div style={{
            width: 6, height: 6, borderRadius: "50%",
            background: status.dot,
            boxShadow: `0 0 7px 1px ${status.dot}45`,
            animation: status.pulse ? "sPulse 1.2s ease-in-out infinite" : "none",
            flexShrink: 0, transition: "background 0.3s, box-shadow 0.3s",
          }} />
          <span style={{ color: status.dot, fontWeight: 600, transition: "color 0.3s" }}>
            {status.label}
          </span>
        </div>

        {/* Divider */}
        <div style={{ width: 1, height: 12, background: "rgba(255,255,255,0.08)", flexShrink: 0 }} />

        {/* Mode + flags */}
        <div style={{ display: "flex", alignItems: "center", gap: 5, padding: "5px 13px 5px 10px" }}>
          <span style={{ color: "rgba(255,255,255,0.48)", textTransform: "capitalize" }}>{config.mode}</span>
          {config.webSearch && (
            <span style={{
              color: "#60a5fa", fontSize: 9, fontWeight: 700, letterSpacing: "0.05em",
              padding: "1px 5px", borderRadius: 4, background: "rgba(96,165,250,0.1)",
            }}>WEB</span>
          )}
          {muted ? (
            <span style={{
              color: "#f87171", fontSize: 9, fontWeight: 700, letterSpacing: "0.05em",
              padding: "1px 5px", borderRadius: 4, background: "rgba(248,113,113,0.12)",
            }}>MIC OFF</span>
          ) : config.voiceEnabled && (
            <span style={{
              color: "#34d399", fontSize: 9, fontWeight: 700, letterSpacing: "0.05em",
              padding: "1px 5px", borderRadius: 4, background: "rgba(52,211,153,0.1)",
            }}>MIC ON</span>
          )}
        </div>
      </button>

      {/* Save / Load — vertically centered on left edge */}
      <div style={{
        position: "fixed", top: "50%", left: 18, transform: "translateY(-50%)",
        zIndex: 9999,
        display: "flex", flexDirection: "column", gap: 6,
        fontFamily: "'Inter','Segoe UI',sans-serif",
      }}>
        {[["Save", handleSave], ["Load", handleLoad]].map(([label, fn]) => (
          <button key={label} onClick={fn} style={{
            padding: "6px 14px", borderRadius: 8,
            background: "rgba(10,10,10,0.65)", backdropFilter: "blur(10px)",
            color: "#9ca3af", border: "1px solid rgba(255,255,255,0.07)",
            cursor: "pointer", fontSize: 11, fontWeight: 500,
          }}>{label}</button>
        ))}
      </div>


      <style>{`
        @keyframes sPulse {
          0%,100% { opacity:1; }
          50% { opacity:.4; }
        }
        button:focus { outline: none; }
      `}</style>
    </>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
// ROOT APP
// ═══════════════════════════════════════════════════════════════════════════════
export default function App() {
  const [config, setConfig] = useState(null)  // null = show launch screen

  const handleLaunch = useCallback((cfg) => {
    _playback.enabled = cfg.voiceEnabled
    setConfig(cfg)
  }, [])

  if (!config) return <LaunchScreen onLaunch={handleLaunch} />

  return (
    <div style={{ position: "fixed", inset: 0 }}>
      <Tldraw persistenceKey="alphasurface">
        <AlphaSurfaceInner config={config} />
      </Tldraw>
    </div>
  )
}
