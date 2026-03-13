import { useEffect, useRef, useState, useCallback } from "react"
import {
  Tldraw,
  useEditor,
  toRichText,
  getSnapshot,
  loadSnapshot,
  AssetRecordType,
  createShapeId,
  DefaultMainMenu,
  DefaultMainMenuContent,
  TldrawUiMenuGroup,
  TldrawUiMenuItem,
} from "tldraw"
import { jsPDF } from "jspdf"
import "tldraw/tldraw.css"

// ── Audio playback singleton ──────────────────────────────────────────────────
const _playback = {
  _ctx: null,
  nextTime: 0,
  enabled: false,
  sources: [],
}

function activatePlaybackContext() {
  if (!_playback._ctx) {
    _playback._ctx = new AudioContext({ sampleRate: 24000 })
  }
  if (_playback._ctx.state === "suspended") {
    void _playback._ctx.resume().catch(() => {})
  }
  return _playback._ctx
}

function getPlaybackContext() {
  return _playback._ctx
}

function flushAudioPlayback() {
  for (const s of _playback.sources) {
    try {
      s.stop()
    } catch {
      // Ignore sources that have already ended.
    }
  }
  _playback.sources = []
  _playback.nextTime = 0
}

// ── Canvas message handler ────────────────────────────────────────────────────
const VALID_ACTIONS = new Set([
  "add_text",
  "add_note",
  "add_geo",
  "add_arrow",
  "bind_arrow",
  "add_embed",
  "add_bookmark",
  "add_image",
  "add_research_card",
  "add_provocation_card",
  "focus_artifact",
  "clear_canvas",
  "delete_shapes",
  "zoom_to_fit",
  "focus_shape",
  "move_shape",
  "update_shape",
  "select_shapes",
  "align_shapes",
  "distribute_shapes",
  "resize_shape",
  "create_frame",
  "group_shapes",
  "label_shape",
  "audio_response",
  "ai_interrupted",
  "ai_status",
  "canvas_snapshot",
  "config_ack",
  "task_dashboard",
])

function validateCanvasAction(message) {
  if (!message || typeof message !== "object") return { valid: false, reason: "invalid_message" }
  if (typeof message.type !== "string") return { valid: false, reason: "missing_type" }
  if (!VALID_ACTIONS.has(message.type)) return { valid: false, reason: "unknown_type" }

  const needsPayload = new Set([
    "add_text",
    "add_note",
    "add_geo",
    "add_arrow",
    "bind_arrow",
    "add_embed",
    "add_bookmark",
    "add_research_card",
    "add_provocation_card",
    "focus_artifact",
    "delete_shapes",
    "focus_shape",
    "move_shape",
    "update_shape",
    "select_shapes",
    "align_shapes",
    "distribute_shapes",
    "resize_shape",
    "create_frame",
    "group_shapes",
    "label_shape",
    "audio_response",
  ])

  if (needsPayload.has(message.type) && (!message.payload || typeof message.payload !== "object")) {
    return { valid: false, reason: "missing_payload" }
  }

  if (message.type === "add_image") {
    if (!message.id || !message.src) return { valid: false, reason: "missing_add_image_fields" }
  }

  return { valid: true }
}

function handleCanvasMessage(editor, message) {
  if (!editor) return
  const validation = validateCanvasAction(message)
  if (!validation.valid) {
    console.warn("[AlphaSurface] Dropped invalid canvas action", validation.reason, message)
    return
  }

  const p = message.payload ?? {}
  const resolveShapeId = (rawId) => {
    if (!rawId) return createShapeId()
    return String(rawId).startsWith("shape:") ? rawId : createShapeId(rawId)
  }

  const TL_COLORS = new Set([
    "black", "grey", "light-violet", "violet", "blue", "light-blue",
    "yellow", "orange", "green", "light-green", "light-red", "red", "white",
  ])

  const normalizeTlColor = (value, fallback = "black") => {
    const raw = String(value ?? "").trim().toLowerCase().replace(/_/g, "-")
    const aliases = {
      gray: "grey",
      purple: "violet",
      "light-purple": "light-violet",
      "light purple": "light-violet",
      cyan: "light-blue",
      teal: "blue",
    }
    const normalized = aliases[raw] ?? raw
    return TL_COLORS.has(normalized) ? normalized : fallback
  }

  const toShapeMeta = (meta = {}, fallbackRole = "unknown") => ({
    semanticRole: meta.semanticRole ?? meta.semantic_role ?? fallbackRole,
    source: meta.source ?? "unknown",
    confidence: meta.confidence ?? 1,
    linked_to: Array.isArray(meta.linked_to) ? meta.linked_to : [],
    addedBy: meta.addedBy ?? meta.added_by ?? "live_agent",
  })

  const createSemanticCard = ({
    id,
    x,
    y,
    w,
    h,
    title,
    body,
    color,
    semanticRole,
    meta,
  }) => {
    editor.createShape({
      id: resolveShapeId(id),
      type: "geo",
      x: x ?? 240,
      y: y ?? 220,
      props: {
        geo: "rectangle",
        w: w ?? 340,
        h: h ?? 220,
        richText: toRichText(`${title}\n\n${body}`),
          color: normalizeTlColor(color, "blue"),
        fill: "semi",
        dash: "solid",
        size: "m",
      },
      meta: toShapeMeta(meta, semanticRole),
    })
  }

  switch (message.type) {

    case "add_text":
      editor.createShape({
        id: resolveShapeId(p.id),
        type: "text", x: p.x ?? 200, y: p.y ?? 200,
        props: { richText: toRichText(p.text), size: p.size ?? "m", color: normalizeTlColor(p.color, "black") },
        meta: toShapeMeta(p.meta, "text"),
      })
      break

    case "add_note":
      editor.createShape({
        id: resolveShapeId(p.id),
        type: "note", x: p.x ?? 300, y: p.y ?? 300,
        props: { richText: toRichText(p.text), color: normalizeTlColor(p.color, "yellow"), size: p.size ?? "m" },
        meta: toShapeMeta(p.meta, "note"),
      })
      break

    case "add_geo":
      editor.createShape({
        id: resolveShapeId(p.id),
        type: "geo", x: p.x ?? 200, y: p.y ?? 200,
        props: {
          geo: p.geo ?? "rectangle",
          w: p.w ?? 200, h: p.h ?? 120,
          richText: toRichText(p.text ?? ""),
          color: normalizeTlColor(p.color, "blue"),
          fill: p.fill ?? "semi",
          dash: p.dash ?? "draw",
          size: p.size ?? "m",
        },
        meta: toShapeMeta(p.meta, "geo"),
      })
      break

    case "add_arrow":
      editor.createShape({
        id: resolveShapeId(p.id),
        type: "arrow",
        x: p.x1 ?? 100, y: p.y1 ?? 100,
        props: {
          start: { x: 0, y: 0 },
          end: { x: (p.x2 ?? 300) - (p.x1 ?? 100), y: (p.y2 ?? 200) - (p.y1 ?? 100) },
          richText: toRichText(p.label ?? ""),
          color: normalizeTlColor(p.color, "black"),
          size: p.size ?? "m",
          arrowheadEnd: p.arrowhead ?? "arrow",
          arrowheadStart: "none",
        },
        meta: toShapeMeta(p.meta, "arrow"),
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
          color: normalizeTlColor(p.color, "black"), size: p.size ?? "m",
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
        id: resolveShapeId(p.id),
        type: "embed", x: p.x ?? 200, y: p.y ?? 200,
        props: { url: p.url, w: p.w ?? 560, h: p.h ?? 315 },
        meta: toShapeMeta(p.meta, "embed"),
      })
      break

    case "add_bookmark":
      editor.createShape({
        id: resolveShapeId(p.id),
        type: "bookmark", x: p.x ?? 200, y: p.y ?? 200,
        props: { url: p.url, w: 300, h: 160, assetId: null },
        meta: toShapeMeta(p.meta, "bookmark"),
      })
      break

    case "add_research_card": {
      const bullets = Array.isArray(p.bullets) && p.bullets.length > 0
        ? p.bullets.map((item) => `- ${item}`).join("\n")
        : ""
      const body = [p.summary ?? "", bullets, p.url ? `Source: ${p.url}` : ""]
        .filter(Boolean)
        .join("\n\n")

      createSemanticCard({
        id: p.id,
        x: p.x,
        y: p.y,
        w: p.w ?? 420,
        h: p.h ?? 280,
        title: p.title ?? "Research",
        body,
        color: "light-blue",
        semanticRole: "research_card",
        meta: {
          ...(p.meta ?? {}),
          source: p.source ?? p.meta?.source ?? "ResearchAgent",
          confidence: p.confidence ?? p.meta?.confidence ?? 0.75,
          linked_to: p.linked_to ?? p.meta?.linked_to ?? [],
          addedBy: p.meta?.addedBy ?? "ResearchAgent",
        },
      })
      break
    }

    case "add_provocation_card": {
      createSemanticCard({
        id: p.id,
        x: p.x,
        y: p.y,
        w: p.w ?? 360,
        h: p.h ?? 220,
        title: "Provocation",
        body: p.text ?? "",
        color: "violet",
        semanticRole: "provocation_card",
        meta: {
          ...(p.meta ?? {}),
          source: p.source ?? p.meta?.source ?? "AlphaSurface",
          confidence: p.confidence ?? p.meta?.confidence ?? 0.7,
          linked_to: p.linked_to ?? p.meta?.linked_to ?? [],
          addedBy: p.addedBy ?? p.meta?.addedBy ?? "AlphaSurface",
        },
      })
      break
    }

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

    case "focus_artifact": {
      const ids = Array.isArray(p.shapeIds) ? p.shapeIds.filter(Boolean) : []
      if (ids.length > 0) {
        editor.zoomToSelection(ids)
        editor.select(...ids)
      } else if (p.primaryShapeId && editor.getShape(p.primaryShapeId)) {
        editor.zoomToSelection([p.primaryShapeId])
        editor.select(p.primaryShapeId)
      }
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
        if (p.color !== undefined) props.color = normalizeTlColor(p.color, shape.props?.color ?? "black")
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
      const playbackCtx = getPlaybackContext() ?? activatePlaybackContext()
      if (!playbackCtx) break
      const raw = atob(p.data)
      const buf = new ArrayBuffer(raw.length)
      const bytes = new Uint8Array(buf)
      for (let i = 0; i < raw.length; i++) bytes[i] = raw.charCodeAt(i)
      if (playbackCtx.state === "suspended") {
        void playbackCtx.resume().catch(() => {})
      }
      try {
        const audioBuffer = playbackCtx.createBuffer(1, buf.byteLength / 2, 24000)
        const channel = audioBuffer.getChannelData(0)
        const pcm = new Int16Array(buf)
        for (let i = 0; i < pcm.length; i++) channel[i] = pcm[i] / 32768
        const source = playbackCtx.createBufferSource()
        source.buffer = audioBuffer
        source.connect(playbackCtx.destination)
        const now = playbackCtx.currentTime
        if (_playback.nextTime < now) _playback.nextTime = now
        source.start(_playback.nextTime)
        _playback.nextTime += audioBuffer.duration
        _playback.sources.push(source)
        source.onended = () => { _playback.sources = _playback.sources.filter(s => s !== source) }
      } catch (err) {
        console.warn("[AlphaSurface] Audio playback skipped", err)
      }
      break
    }

    case "ai_interrupted":
      flushAudioPlayback()
      break

    case "add_image": {
      const { id, x, y, width, height, src, meta } = message
      const assetId = AssetRecordType.createId()
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
      }])
      editor.createShape({
        id: resolveShapeId(id),
        type: "image",
        x: x ?? 200,
        y: y ?? 200,
        props: {
          w: width ?? 480,
          h: height ?? 480,
          assetId: assetId,
        },
        meta: toShapeMeta(meta, "image"),
      })
      break
    }

    case "ai_status":
    case "canvas_snapshot":
    case "config_ack":
    case "task_dashboard":
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

function AlphaMainMenu() {
  const editor = useEditor()

  const blobToDataUrl = (blob) => new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onloadend = () => resolve(reader.result)
    reader.onerror = reject
    reader.readAsDataURL(blob)
  })

  const loadImage = (src) => new Promise((resolve, reject) => {
    const img = new Image()
    img.onload = () => resolve(img)
    img.onerror = reject
    img.src = src
  })

  const isAssetReachable = async (url) => {
    const controller = new AbortController()
    const timeoutId = setTimeout(() => controller.abort(), 1500)
    try {
      const res = await fetch(url, {
        method: "GET",
        signal: controller.signal,
        cache: "no-store",
      })
      return res.ok
    } catch {
      return false
    } finally {
      clearTimeout(timeoutId)
    }
  }

  const getUnreachableImageAssets = async (pagesWithShapes) => {
    const pagesByUrl = new Map()

    for (const { page, shapeIds } of pagesWithShapes) {
      for (const shapeId of shapeIds) {
        const shape = editor.getShape(shapeId)
        if (!shape || shape.type !== "image") continue
        const asset = shape.props?.assetId ? editor.getAsset(shape.props.assetId) : null
        const src = asset?.props?.src
        if (!src || !/^https?:\/\//.test(src)) continue
        if (!pagesByUrl.has(src)) {
          pagesByUrl.set(src, new Set())
        }
        pagesByUrl.get(src).add(page.name || "Untitled page")
      }
    }

    const failures = []
    const checks = await Promise.all(
      [...pagesByUrl.keys()].map(async (src) => ({ src, ok: await isAssetReachable(src) }))
    )

    for (const check of checks) {
      if (check.ok) continue
      for (const pageName of pagesByUrl.get(check.src)) {
        failures.push({ pageName, src: check.src })
      }
    }

    return failures
  }

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
    const pages = editor.getPages()
    const pagesWithShapes = pages.map((page) => ({
      page,
      shapeIds: [...editor.getPageShapeIds(page.id)],
    }))

    if (pagesWithShapes.every(({ shapeIds }) => shapeIds.length === 0)) {
      console.warn("[AlphaSurface] Export skipped: canvas is empty")
      return
    }

    const originalPageId = editor.getCurrentPageId()

    try {
      const unreachableAssets = await getUnreachableImageAssets(pagesWithShapes)
      if (unreachableAssets.length > 0) {
        const firstFailure = unreachableAssets[0]
        throw new Error(
          `Export blocked because an image asset could not be reached on page "${firstFailure.pageName}". ` +
          `The backend appears to be offline, so localhost:8000 assets cannot be embedded in the PDF.`
        )
      }

      const pdf = new jsPDF({ unit: "pt", format: "a4" })
      let wrotePage = false

      for (const { page, shapeIds } of pagesWithShapes) {
        if (shapeIds.length === 0) continue

        editor.setCurrentPage(page.id)
        await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)))

        const liveShapeIds = [...editor.getCurrentPageShapeIds()]
        if (liveShapeIds.length === 0) continue

        const { blob } = await Promise.race([
          editor.toImage(liveShapeIds, {
            format: "png",
            background: true,
            padding: 32,
          }),
          new Promise((_, reject) => {
            setTimeout(() => reject(new Error(`Timed out exporting page "${page.name || "Untitled page"}"`)), 12000)
          }),
        ])

        const dataUrl = await blobToDataUrl(blob)
        const img = await loadImage(dataUrl)

        if (wrotePage) {
          pdf.addPage("a4", "portrait")
        }

        const pageW = pdf.internal.pageSize.getWidth()
        const pageH = pdf.internal.pageSize.getHeight()
        const headerY = 28
        const headerGap = 18
        const usableW = pageW - 48
        const usableH = pageH - 64 - headerGap
        const scale = Math.min(usableW / img.width, usableH / img.height)
        const drawW = img.width * scale
        const drawH = img.height * scale
        const x = (pageW - drawW) / 2
        const y = headerY + headerGap

        pdf.setFontSize(11)
        pdf.setTextColor(90, 90, 90)
        pdf.text(page.name || "Untitled page", 24, headerY)
        pdf.addImage(dataUrl, "PNG", x, y, drawW, drawH, undefined, "FAST")
        wrotePage = true
      }

      if (!wrotePage) {
        console.warn("[AlphaSurface] Export skipped: no non-empty pages found")
        return
      }

      pdf.save("alphasurface-export.pdf")
    } catch (err) {
      console.error("[AlphaSurface] PDF export failed", err)
      window.alert(err instanceof Error ? err.message : "PDF export failed. Check whether the backend is running and try again.")
    } finally {
      editor.setCurrentPage(originalPageId)
    }
  }

  const handleUploadDoc = () => {
    const input = Object.assign(document.createElement("input"), { type: "file", accept: ".pdf,.doc,.docx,.txt" })
    input.onchange = async (e) => {
      const file = e.target.files?.[0]
      if (!file) return

      const formData = new FormData()
      formData.append("file", file)

      try {
        const res = await fetch("/api/upload", {
          method: "POST",
          body: formData,
        })
        const data = await res.json()
        if (data.status === "success") {
          const vp = editor.getViewportPageBounds()
          editor.createShape({
            id: createShapeId(),
            type: "note",
            x: (vp?.x ?? 0) + Math.max(40, (vp?.w ?? 1000) * 0.25),
            y: (vp?.y ?? 0) + Math.max(40, (vp?.h ?? 700) * 0.2),
            props: {
              richText: toRichText(`Uploaded document: ${file.name}\n\nThe agent now has access to this file.`),
              color: "blue",
              size: "m",
            },
          })
        }
      } catch (err) {
        console.error("Upload failed", err)
      }
    }
    input.click()
  }

  return (
    <DefaultMainMenu>
      <TldrawUiMenuGroup id="alphasurface-file-actions">
        <TldrawUiMenuItem id="alphasurface-save" label="Save canvas" readonlyOk onSelect={handleSave} />
        <TldrawUiMenuItem id="alphasurface-load" label="Load canvas" readonlyOk onSelect={handleLoad} />
        <TldrawUiMenuItem id="alphasurface-export-pdf" label="Export PDF" readonlyOk onSelect={handleExportPdf} />
        <TldrawUiMenuItem id="alphasurface-upload-doc" label="Upload document" readonlyOk onSelect={handleUploadDoc} />
      </TldrawUiMenuGroup>
      <DefaultMainMenuContent />
    </DefaultMainMenu>
  )
}

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

  const wsRef = useRef(null)
  const prevShapeCount = useRef(0)
  const mutedRef = useRef(false)
  const lastInterruptAtRef = useRef(0)
  const configRef = useRef(config)

  const provocFreq = "Normal"
  const provocStyle = "Socratic"

  useEffect(() => {
    configRef.current = config
  }, [config])

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
            mode: configRef.current.mode, 
            webSearch: configRef.current.webSearch, 
            voiceEnabled: configRef.current.voiceEnabled,
            mcps: configRef.current.mcps,
            goal: configRef.current.goal,
            audience: configRef.current.audience,
            uploadedFile: configRef.current.uploadedFile,
            provocationFrequency: provocFreq,
            provocationStyle: provocStyle
          }
        }))
      }

      socket.onmessage = (event) => {
        if (disposed) return
        let message
        try {
          message = JSON.parse(event.data)
        } catch {
          console.warn("[AlphaSurface] Dropped malformed websocket message")
          return
        }
        if (message.type === "ai_status") { setAiStatus(message.payload?.status ?? "idle"); return }
        if (message.type === "ai_interrupted") {
          const now = Date.now()
          if (now - lastInterruptAtRef.current > 250) {
            lastInterruptAtRef.current = now
            flushAudioPlayback()
            setAiStatus("idle")
          }
          return
        }
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
      
      const currentPage = editor.getCurrentPage()
      const currentPageId = currentPage.id
      const sortedIds = editor.getSortedChildIdsForParent(currentPageId)
      const zIndexMap = {}
      sortedIds.forEach((id, i) => { zIndexMap[id] = i })

      const viewport = editor.getViewportPageBounds()
      const selectedIds = new Set(editor.getSelectedShapeIds())
      const pages = editor.getPages().map((page) => ({
        id: page.id,
        name: page.name,
        shapeCount: editor.getPageShapeIds(page.id).size,
      }))

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
            source: shape.meta?.source ?? 'unknown',
            addedBy:      shape.meta?.addedBy      ?? 'user',
            confidence:   shape.meta?.confidence   ?? 1.0,
            linked_to: Array.isArray(shape.meta?.linked_to) ? shape.meta.linked_to : [],
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
          currentPageId,
          currentPageName: currentPage.name,
          pages,
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
  }, [config.voiceEnabled])

  // ── Unlock playback context on first user gesture ─────────────────────────
  useEffect(() => {
    if (!config.voiceEnabled) return
    if (getPlaybackContext()) return

    const unlock = () => {
      activatePlaybackContext()
      window.removeEventListener("pointerdown", unlock)
      window.removeEventListener("keydown", unlock)
      window.removeEventListener("touchstart", unlock)
    }

    window.addEventListener("pointerdown", unlock, { passive: true })
    window.addEventListener("keydown", unlock)
    window.addEventListener("touchstart", unlock, { passive: true })

    return () => {
      window.removeEventListener("pointerdown", unlock)
      window.removeEventListener("keydown", unlock)
      window.removeEventListener("touchstart", unlock)
    }
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
      } catch (err) {
        console.warn("[AlphaSurface] Canvas capture failed", err)
      }
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
          if (!next) activatePlaybackContext()
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
          {muted || !config.voiceEnabled ? (
            <span style={{
              color: "#f87171", fontSize: 9, fontWeight: 700, letterSpacing: "0.05em",
              padding: "1px 5px", borderRadius: 4, background: "rgba(248,113,113,0.12)",
            }}>MIC OFF</span>
          ) : (
            <span style={{
              color: "#34d399", fontSize: 9, fontWeight: 700, letterSpacing: "0.05em",
              padding: "1px 5px", borderRadius: 4, background: "rgba(52,211,153,0.1)",
            }}>MIC ON</span>
          )}
        </div>
      </button>

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
      } catch {
        return null
      }
    }
    return null
  })

  const handleLaunch = useCallback((cfg) => {
    _playback.enabled = cfg.voiceEnabled
    if (cfg.voiceEnabled) activatePlaybackContext()
    setConfig(cfg)
    localStorage.setItem("alpha_surface_config", JSON.stringify(cfg))
  }, [])

  if (!config) return <OnboardingFlow onComplete={handleLaunch} />

  return (
    <div style={{ position: "fixed", inset: 0 }}>
      <Tldraw
        persistenceKey="alphasurface"
        licenseKey="tldraw-2026-06-21/WyIxVGRUUjl0diIsWyIqIl0sMTYsIjIwMjYtMDYtMjEiXQ.C8bp6SdPUOFAStZunx2d1YuoGxlZnIn0WJzKwXRDeuUmDaO9/YFeN2ax/30/QFJd4nXPOVDfpkzvMUXJIAIU+A"
        forceMobile
        components={{ MainMenu: AlphaMainMenu }}
      >
        <AlphaSurfaceInner config={config} />
      </Tldraw>
    </div>
  )
}
