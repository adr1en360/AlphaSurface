import { useEffect, useRef, useState, useCallback } from "react"
import { Tldraw, useEditor, toRichText, getSnapshot, loadSnapshot, AssetRecordType, createShapeId } from "tldraw"
import { Settings, Save, FolderOpen, FileUp, FileDown } from "lucide-react"
import { jsPDF } from "jspdf"
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

    case 'align_shapes': {
      editor.alignShapes(p.shapeIds, p.alignment)
      break
    }

    case 'distribute_shapes': {
      editor.distributeShapes(p.shapeIds, p.direction)
      break
    }

    case 'resize_shape': {
      editor.updateShape({
        id: p.shapeId,
        type: editor.getShape(p.shapeId)?.type,
        props: { w: p.w, h: p.h },
      })
      break
    }

    case 'create_frame': {
      editor.createShape({
        id: createShapeId(),
        type: 'frame',
        x: p.x, y: p.y,
        props: { w: p.w, h: p.h, name: p.label },
      })
      break
    }

    case 'group_shapes': {
      editor.groupShapes(p.shapeIds)
      break
    }

    case 'label_shape': {
      const shape = editor.getShape(p.shapeId)
      if (shape) {
        editor.updateShape({
          id: p.shapeId,
          type: shape.type,
          meta: {
            ...shape.meta,
            semanticRole: p.semanticRole ?? 'unknown',
            addedBy: p.addedBy ?? 'live_agent',
          },
        })
      }
      break
    }

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

    case "add_image": {
      const { id, x, y, width, height, src } = message;
      const assetId = AssetRecordType.createId();
      editor.createAssets([{
        id: assetId,
        type: "image",
        typeName: "asset",
        props: {
          name: id || "image",
          src: src,
          w: width ?? 480,
          h: height ?? 480,
          mimeType: "image/png",
          isAnimated: false,
        },
        meta: {},
      }]);
      editor.createShape({
        id: createShapeId(id),
        type: "image",
        x: x ?? 200,
        y: y ?? 200,
        props: {
          w: width ?? 480,
          h: height ?? 480,
          assetId: assetId,
        },
      });
      break;
    }

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

import OnboardingFlow from "./components/OnboardingFlow"

// ═══════════════════════════════════════════════════════════════════════════════
// ONBOARDING SCREEN (Replaced LaunchScreen)
// ═══════════════════════════════════════════════════════════════════════════════

// ═══════════════════════════════════════════════════════════════════════════════
// CANVAS INNER  (mounts inside <Tldraw>)
// ═══════════════════════════════════════════════════════════════════════════════
function AlphaSurfaceInner({ config }) {
  const editor = useEditor()
  const [ws, setWs] = useState(null)
  const [indicator, setIndicator] = useState(false)
  const [aiStatus, setAiStatus] = useState("disconnected")
  const [muted, setMuted] = useState(false)
  const [showSettings, setShowSettings] = useState(false)
  const [provocFreq, setProvocFreq] = useState("Normal")
  const [provocStyle, setProvocStyle] = useState("Socratic")

  const wsRef = useRef(null)
  const prevShapeCount = useRef(0)
  const mutedRef = useRef(false)

  const updateBackendConfig = (newFreq, newStyle) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({
        type: "set_config",
        payload: {
          mode: config.mode,
          webSearch: config.webSearch,
          mcps: config.mcps,
          goal: config.goal,
          audience: config.audience,
          uploadedFile: config.uploadedFile,
          provocationFrequency: newFreq ?? provocFreq,
          provocationStyle: newStyle ?? provocStyle
        }
      }))
    }
  }

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
          payload: { 
            mode: config.mode, 
            webSearch: config.webSearch, 
            mcps: config.mcps,
            goal: config.goal,
            audience: config.audience,
            uploadedFile: config.uploadedFile,
            provocationFrequency: provocFreq,
            provocationStyle: provocStyle
          }
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
      
      const sortedIds = editor.getSortedChildIdsForParent(editor.getCurrentPageId())
      const zIndexMap = {}
      sortedIds.forEach((id, i) => { zIndexMap[id] = i })

      const viewport = editor.getViewportPageBounds()
      const selectedIds = new Set(editor.getSelectedShapeIds())

      const shapes = editor.getCurrentPageShapes().map(shape => {
        const bounds = editor.getShapePageBounds(shape.id)
        const inViewport = viewport && bounds
          ? !(bounds.x + bounds.w < viewport.x ||
              bounds.x > viewport.x + viewport.w ||
              bounds.y + bounds.h < viewport.y ||
              bounds.y > viewport.y + viewport.h)
          : false

        const enriched = {
          id:       shape.id,
          type:     shape.type,
          x:        bounds?.x  ?? shape.x ?? 0,
          y:        bounds?.y  ?? shape.y ?? 0,
          w:        bounds?.w  ?? shape.props?.w ?? 100,
          h:        bounds?.h  ?? shape.props?.h ?? 60,
          text: (
            shape.props?.text ??
            (typeof shape.props?.richText === 'string' ? shape.props.richText : '') ??
            ''
          ).trim(),
          color:    shape.props?.color    ?? 'black',
          rotation: shape.rotation        ?? 0,
          parentId: shape.parentId === editor.getCurrentPageId()
                      ? null
                      : shape.parentId,
          zIndex:   zIndexMap[shape.id]   ?? 0,
          inViewport,
          isLocked: shape.isLocked        ?? false,
          meta: {
            semanticRole: shape.meta?.semanticRole ?? 'unknown',
            addedBy:      shape.meta?.addedBy      ?? 'user',
            confidence:   shape.meta?.confidence   ?? 1.0,
          },
        }

        if (shape.type === 'arrow') {
          enriched.arrowBindings = {
            startShapeId: shape.props?.start?.boundShapeId ?? null,
            endShapeId:   shape.props?.end?.boundShapeId   ?? null,
          }
        }
        return enriched
      })

      ws.send(JSON.stringify({
        type: "canvas_snapshot",
        payload: { 
          shapes, 
          shape_count: shapes.length,
          viewport: {
            x:    viewport?.x ?? 0,
            y:    viewport?.y ?? 0,
            w:    viewport?.w ?? 1200,
            h:    viewport?.h ?? 800,
            zoom: editor.getZoomLevel(),
          },
          selectedShapeIds: [...selectedIds],
        }
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

  const handleExportPdf = async () => {
    const shapeIds = [...editor.getCurrentPageShapeIds()]
    if (shapeIds.length === 0) {
      console.warn("[AlphaSurface] Export skipped: canvas is empty")
      return
    }

    try {
      const { blob } = await editor.toImage(shapeIds, {
        format: "png",
        background: true,
        padding: 32,
      })

      const dataUrl = await new Promise((resolve, reject) => {
        const reader = new FileReader()
        reader.onloadend = () => resolve(reader.result)
        reader.onerror = reject
        reader.readAsDataURL(blob)
      })

      const img = new Image()
      await new Promise((resolve, reject) => {
        img.onload = resolve
        img.onerror = reject
        img.src = dataUrl
      })

      const orientation = img.width >= img.height ? "landscape" : "portrait"
      const pdf = new jsPDF({ orientation, unit: "pt", format: "a4" })
      const pageW = pdf.internal.pageSize.getWidth()
      const pageH = pdf.internal.pageSize.getHeight()
      const scale = Math.min(pageW / img.width, pageH / img.height)
      const drawW = img.width * scale
      const drawH = img.height * scale
      const x = (pageW - drawW) / 2
      const y = (pageH - drawH) / 2

      pdf.addImage(dataUrl, "PNG", x, y, drawW, drawH, undefined, "FAST")
      pdf.save("alphasurface-export.pdf")
    } catch (err) {
      console.error("[AlphaSurface] PDF export failed", err)
    }
  }

  const handleUploadClick = () => {
    const input = Object.assign(document.createElement("input"), { type: "file", accept: ".pdf,.doc,.docx,.txt" })
    input.onchange = async (e) => {
      const file = e.target.files?.[0]
      if (!file) return
      
      const formData = new FormData()
      formData.append("file", file)
      
      try {
        setAiStatus("thinking")
        const res = await fetch("/api/upload", {
          method: "POST",
          body: formData
        })
        const data = await res.json()
        if (data.status === "success" && wsRef.current?.readyState === WebSocket.OPEN) {
          const id = createShapeId()
          editor.createShape({
            id,
            type: "note", 
            x: window.innerWidth / 2 - 100, 
            y: window.innerHeight / 2 - 100,
            props: { richText: toRichText(`📄 Uploaded Document: ${file.name}\n\nThe agent now has access to this file.`), color: "blue" }
          })
        }
      } catch (err) {
        console.error("Upload failed", err)
      } finally {
        if (wsRef.current?.readyState === WebSocket.OPEN) setAiStatus("idle")
      }
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
        display: "flex", flexDirection: "column", gap: 10,
        fontFamily: "'Inter','Segoe UI',sans-serif",
      }}>
        {[
          ["Save", handleSave, Save], 
          ["Load", handleLoad, FolderOpen], 
          ["Export PDF", handleExportPdf, FileDown],
          ["Upload Doc", handleUploadClick, FileUp]
        ].map(([label, fn, Icon]) => (
          <button key={label} onClick={fn} style={{
            padding: "12px", borderRadius: 14,
            background: "rgba(15, 23, 42, 0.6)", backdropFilter: "blur(16px)", WebkitBackdropFilter: "blur(16px)",
            color: "#94a3b8", border: "1px solid rgba(255,255,255,0.1)",
            boxShadow: "0 4px 12px rgba(0,0,0,0.2)",
            cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center",
            transition: "all 0.2s ease",
            position: "relative",
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.color = "#f8fafc";
            e.currentTarget.style.background = "rgba(30, 41, 59, 0.8)";
            e.currentTarget.style.borderColor = "rgba(255,255,255,0.2)";
            e.currentTarget.style.transform = "scale(1.05)";
            const tooltip = e.currentTarget.querySelector(".btn-tooltip");
            if (tooltip) {
               tooltip.style.opacity = "1";
               tooltip.style.transform = "translateX(0)";
            }
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.color = "#94a3b8";
            e.currentTarget.style.background = "rgba(15, 23, 42, 0.6)";
            e.currentTarget.style.borderColor = "rgba(255,255,255,0.1)";
            e.currentTarget.style.transform = "scale(1)";
            const tooltip = e.currentTarget.querySelector(".btn-tooltip");
            if (tooltip) {
               tooltip.style.opacity = "0";
               tooltip.style.transform = "translateX(-5px)";
            }
          }}>
            <Icon size={20} strokeWidth={2} />
            <div className="btn-tooltip" style={{
              position: "absolute", left: "100%", marginLeft: "14px",
              background: "rgba(15, 23, 42, 0.95)", backdropFilter: "blur(8px)",
              padding: "6px 10px", borderRadius: "8px",
              fontSize: "13px", fontWeight: 500, color: "#f8fafc",
              border: "1px solid rgba(255,255,255,0.1)",
              pointerEvents: "none", opacity: 0, transform: "translateX(-5px)",
              transition: "all 0.2s cubic-bezier(0.16, 1, 0.3, 1)", whiteSpace: "nowrap",
              boxShadow: "0 4px 12px rgba(0,0,0,0.3)"
            }}>
              {label}
            </div>
          </button>
        ))}

        <div style={{ width: "24px", height: "1px", background: "rgba(255,255,255,0.1)", margin: "4px auto" }} />

        {/* Settings Button */}
        <button 
          onClick={() => setShowSettings(!showSettings)} 
          style={{
            padding: "12px", borderRadius: 14,
            background: showSettings ? "rgba(6, 182, 212, 0.2)" : "rgba(15, 23, 42, 0.6)", 
            backdropFilter: "blur(16px)", WebkitBackdropFilter: "blur(16px)",
            color: showSettings ? "#fff" : "#94a3b8", 
            border: `1px solid ${showSettings ? "rgba(6, 182, 212, 0.5)" : "rgba(255,255,255,0.1)"}`,
            boxShadow: showSettings ? "0 0 16px rgba(6,182,212,0.3)" : "0 4px 12px rgba(0,0,0,0.2)",
            cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center",
            transition: "all 0.2s ease", position: "relative"
          }}
          onMouseEnter={(e) => {
            if (!showSettings) {
                e.currentTarget.style.color = "#f8fafc";
                e.currentTarget.style.background = "rgba(30, 41, 59, 0.8)";
                e.currentTarget.style.borderColor = "rgba(255,255,255,0.2)";
            }
            e.currentTarget.style.transform = "scale(1.05)";
            const tooltip = e.currentTarget.querySelector(".btn-tooltip");
            if (tooltip && !showSettings) {
               tooltip.style.opacity = "1";
               tooltip.style.transform = "translateX(0)";
            }
          }}
          onMouseLeave={(e) => {
            if (!showSettings) {
                e.currentTarget.style.color = "#94a3b8";
                e.currentTarget.style.background = "rgba(15, 23, 42, 0.6)";
                e.currentTarget.style.borderColor = "rgba(255,255,255,0.1)";
            }
            e.currentTarget.style.transform = "scale(1)";
            const tooltip = e.currentTarget.querySelector(".btn-tooltip");
            if (tooltip) {
               tooltip.style.opacity = "0";
               tooltip.style.transform = "translateX(-5px)";
            }
          }}
        >
          <Settings size={20} strokeWidth={2} />
          <div className="btn-tooltip" style={{
              position: "absolute", left: "100%", marginLeft: "14px",
              background: "rgba(15, 23, 42, 0.95)", backdropFilter: "blur(8px)",
              padding: "6px 10px", borderRadius: "8px",
              fontSize: "13px", fontWeight: 500, color: "#f8fafc",
              border: "1px solid rgba(255,255,255,0.1)",
              pointerEvents: "none", opacity: 0, transform: "translateX(-5px)",
              transition: "all 0.2s cubic-bezier(0.16, 1, 0.3, 1)", whiteSpace: "nowrap",
              boxShadow: "0 4px 12px rgba(0,0,0,0.3)",
              display: showSettings ? "none" : "block"
            }}>
              Settings
          </div>
        </button>

        {/* Settings Panel */}
        {showSettings && (
          <div style={{
            position: "absolute", left: "100%", top: "40%", marginLeft: 16, width: 220,
            background: "rgba(15, 23, 42, 0.9)", backdropFilter: "blur(20px)",
            border: "1px solid rgba(148, 163, 184, 0.2)", borderRadius: 12, padding: 16,
            boxShadow: "0 10px 30px rgba(0,0,0,0.5)", color: "#f8fafc"
          }}>
            <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 12, color: "#cbd5e1" }}>Provocation Settings</div>
            
            <div style={{ marginBottom: 16 }}>
              <div style={{ fontSize: 11, color: "#94a3b8", marginBottom: 6, textTransform: "uppercase", letterSpacing: "0.05em" }}>Frequency</div>
              <div style={{ display: "flex", gap: 4, background: "rgba(0,0,0,0.3)", padding: 4, borderRadius: 8 }}>
                {["Rare", "Normal", "Frequent"].map(f => (
                  <button 
                    key={f}
                    onClick={() => { setProvocFreq(f); updateBackendConfig(f, provocStyle); }}
                    style={{
                      flex: 1, padding: "4px 0", fontSize: 11, cursor: "pointer",
                      background: provocFreq === f ? "rgba(6, 182, 212, 0.3)" : "transparent",
                      color: provocFreq === f ? "#fff" : "#94a3b8",
                      border: "none", borderRadius: 4, transition: "all 0.2s"
                    }}
                  >{f}</button>
                ))}
              </div>
            </div>

            <div>
              <div style={{ fontSize: 11, color: "#94a3b8", marginBottom: 6, textTransform: "uppercase", letterSpacing: "0.05em" }}>Style</div>
              <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                {["Socratic", "Direct", "Devil's Advocate"].map(s => (
                  <button 
                    key={s}
                    onClick={() => { setProvocStyle(s); updateBackendConfig(provocFreq, s); }}
                    style={{
                      padding: "6px 8px", fontSize: 11, cursor: "pointer", textAlign: "left",
                      background: provocStyle === s ? "rgba(6, 182, 212, 0.15)" : "transparent",
                      color: provocStyle === s ? "#fff" : "#94a3b8",
                      border: `1px solid ${provocStyle === s ? "rgba(6, 182, 212, 0.3)" : "transparent"}`, 
                      borderRadius: 6, transition: "all 0.2s"
                    }}
                  >{s}</button>
                ))}
              </div>
            </div>
          </div>
        )}
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
  const [config, setConfig] = useState(() => {
    const saved = localStorage.getItem("alpha_surface_config")
    if (saved) {
      try {
        return JSON.parse(saved)
      } catch (e) {
        return null
      }
    }
    return null
  })

  const handleLaunch = useCallback((cfg) => {
    _playback.enabled = cfg.voiceEnabled
    setConfig(cfg)
    localStorage.setItem("alpha_surface_config", JSON.stringify(cfg))
  }, [])

  if (!config) return <OnboardingFlow onComplete={handleLaunch} />

  return (
    <div style={{ position: "fixed", inset: 0 }}>
      <Tldraw persistenceKey="alphasurface">
        <AlphaSurfaceInner config={config} />
      </Tldraw>
    </div>
  )
}
