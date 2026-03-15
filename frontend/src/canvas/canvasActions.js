// ── Canvas action handler ─────────────────────────────────────────────────────
// Handles all messages from the Python backend that manipulate the tldraw canvas.
// Includes original AlphaSurface actions + precision actions from tldraw template.

import { createShapeId, toRichText, AssetRecordType, b64Vecs } from "tldraw"

// ── Valid action types ────────────────────────────────────────────────────────
export const VALID_ACTIONS = new Set([
  // Create
  "add_text", "add_note", "add_geo", "add_arrow", "bind_arrow",
  "add_embed", "add_bookmark", "add_image",
  "add_research_card", "add_provocation_card",
  // Read / navigate
  "focus_artifact", "focus_shape", "zoom_to_fit",
  // Precision actions (from tldraw template)
  "move_shape",       // anchor-aware move (upgraded from simple x/y set)
  "place_shape",      // place relative to another shape (NEW)
  "update_shape",     // edit existing shape props
  "resize_shape",     // scale-based resize (upgraded)
  "align_shapes",     // align multiple shapes
  "distribute_shapes",
  // Edit
  "delete_shapes", "clear_canvas",
  "select_shapes", "group_shapes", "label_shape",
  "create_frame",
  "undo", "redo",
  // New organize and freehand
  "draw_freehand", "stack_shapes", "rotate_shapes", "bring_to_front", "send_to_back", "set_viewport",
  // Internal / audio
  "audio_response", "ai_interrupted", "ai_status",
  "canvas_snapshot", "config_ack", "task_dashboard",
])

// ── Validation ────────────────────────────────────────────────────────────────
export function validateCanvasAction(message) {
  if (!message || typeof message !== "object") return { valid: false, reason: "invalid_message" }
  if (typeof message.type !== "string") return { valid: false, reason: "missing_type" }
  if (!VALID_ACTIONS.has(message.type)) return { valid: false, reason: "unknown_type" }

  const needsPayload = new Set([
    "add_text", "add_note", "add_geo", "add_arrow", "bind_arrow",
    "add_embed", "add_bookmark",
    "add_research_card", "add_provocation_card",
    "focus_artifact", "delete_shapes", "focus_shape",
    "move_shape", "place_shape", "update_shape", "select_shapes",
    "align_shapes", "distribute_shapes", "resize_shape",
    "create_frame", "group_shapes", "label_shape",
    "audio_response",
    // New
    "draw_freehand",
    "stack_shapes", "rotate_shapes", "bring_to_front", "send_to_back", "set_viewport",
  ])


  if (needsPayload.has(message.type) && (!message.payload || typeof message.payload !== "object")) {
    return { valid: false, reason: "missing_payload" }
  }

  if (message.type === "add_image") {
    if (!message.id || !message.src) return { valid: false, reason: "missing_add_image_fields" }
  }

  return { valid: true }
}

// ── Helpers ───────────────────────────────────────────────────────────────────
const TL_COLORS = new Set([
  "black", "grey", "light-violet", "violet", "blue", "light-blue",
  "yellow", "orange", "green", "light-green", "light-red", "red", "white",
])

function normalizeTlColor(value, fallback = "black") {
  const raw = String(value ?? "").trim().toLowerCase().replace(/_/g, "-")
  const aliases = {
    gray: "grey", purple: "violet",
    "light-purple": "light-violet", "light purple": "light-violet",
    cyan: "light-blue", teal: "blue",
  }
  const normalized = aliases[raw] ?? raw
  return TL_COLORS.has(normalized) ? normalized : fallback
}

function resolveShapeId(rawId) {
  if (!rawId) return createShapeId()
  return String(rawId).startsWith("shape:") ? rawId : createShapeId(rawId)
}

// Convert simple IDs (without "shape:" prefix) to tldraw IDs
function toTldrawId(simpleId) {
  if (!simpleId) return null
  return String(simpleId).startsWith("shape:") ? simpleId : `shape:${simpleId}`
}

function toShapeMeta(meta = {}, fallbackRole = "unknown") {
  return {
    semanticRole: meta.semanticRole ?? meta.semantic_role ?? fallbackRole,
    source: meta.source ?? "unknown",
    confidence: meta.confidence ?? 1,
    linked_to: Array.isArray(meta.linked_to) ? meta.linked_to : [],
    addedBy: meta.addedBy ?? meta.added_by ?? "live_agent",
  }
}

function createSemanticCard(editor, { id, x, y, w, h, title, body, color, semanticRole, meta }) {
  editor.createShape({
    id: resolveShapeId(id),
    type: "geo",
    x: x ?? 240, y: y ?? 220,
    props: {
      geo: "rectangle",
      w: w ?? 340, h: h ?? 220,
      richText: toRichText(`${title}\n\n${body}`),
      color: normalizeTlColor(color, "blue"),
      fill: "semi", dash: "solid", size: "m",
    },
    meta: toShapeMeta(meta, semanticRole),
  })
}

// ── Main handler ──────────────────────────────────────────────────────────────
export function handleCanvasMessage(editor, message, audioCallbacks) {
  if (!editor) return
  const validation = validateCanvasAction(message)
  if (!validation.valid) {
    console.warn("[AlphaSurface] Dropped invalid canvas action", validation.reason, message)
    return
  }

  const p = message.payload ?? {}

  switch (message.type) {

    // ── Create actions ──────────────────────────────────────────────────────

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
          fill: p.fill ?? "semi", dash: p.dash ?? "draw", size: p.size ?? "m",
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
        },
      })
      editor.createBinding({ type: "arrow", fromId: arrowId, toId: p.fromShapeId, props: { terminal: "start", normalizedAnchor: { x: 0.5, y: 0.5 }, isExact: false, isPrecise: false } })
      editor.createBinding({ type: "arrow", fromId: arrowId, toId: p.toShapeId, props: { terminal: "end", normalizedAnchor: { x: 0.5, y: 0.5 }, isExact: false, isPrecise: false } })
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
        ? p.bullets.map(item => `- ${item}`).join("\n") : ""
      const body = [p.summary ?? "", bullets, p.url ? `Source: ${p.url}` : ""].filter(Boolean).join("\n\n")
      createSemanticCard(editor, {
        id: p.id, x: p.x, y: p.y, w: p.w ?? 420, h: p.h ?? 280,
        title: p.title ?? "Research", body, color: "light-blue",
        semanticRole: "research_card",
        meta: { ...(p.meta ?? {}), source: p.source ?? "ResearchAgent", confidence: p.confidence ?? 0.75, linked_to: p.linked_to ?? [], addedBy: "ResearchAgent" },
      })
      break
    }

    case "add_provocation_card":
      createSemanticCard(editor, {
        id: p.id, x: p.x, y: p.y, w: p.w ?? 360, h: p.h ?? 220,
        title: "Provocation", body: p.text ?? "", color: "violet",
        semanticRole: "provocation_card",
        meta: { ...(p.meta ?? {}), source: p.source ?? "AlphaSurface", confidence: p.confidence ?? 0.7, linked_to: p.linked_to ?? [], addedBy: "AlphaSurface" },
      })
      break

    case "add_image": {
      const { id, x, y, width, height, src, meta } = message
      const assetId = AssetRecordType.createId()
      editor.createAssets([{
        id: assetId, type: "image", typeName: "asset",
        props: { name: id || "image", src, w: width ?? 480, h: height ?? 480, mimeType: "image/png", isAnimated: false },
        meta: {},
      }])
      editor.createShape({
        id: resolveShapeId(id), type: "image",
        x: x ?? 200, y: y ?? 200,
        props: { w: width ?? 480, h: height ?? 480, assetId },
        meta: toShapeMeta(meta, "image"),
      })
      break
    }

    case "draw_freehand": {
      if (!p.points || p.points.length < 2) break
      const minX = Math.min(...p.points.map(pt => pt.x))
      const minY = Math.min(...p.points.map(pt => pt.y))
      const interpolated = []
      for (let i = 0; i < p.points.length - 1; i++) {
        const curr = p.points[i]
        const next = p.points[i + 1]
        interpolated.push(curr)
        const dist = Math.sqrt((next.x - curr.x) ** 2 + (next.y - curr.y) ** 2)
        const steps = Math.floor(dist / 8)
        for (let j = 1; j < steps; j++) {
          const t = j / steps
          interpolated.push({
            x: Math.round(curr.x + (next.x - curr.x) * t),
            y: Math.round(curr.y + (next.y - curr.y) * t),
          })
        }
      }
      interpolated.push(p.points[p.points.length - 1])
      if (p.closed && interpolated.length > 0) interpolated.push(interpolated[0])
      const segPoints = interpolated.map(pt => ({
        x: pt.x - minX, y: pt.y - minY, z: 0.75,
      }))
      const encoded = b64Vecs.encodePoints(segPoints)
      const shapeId = p.id || createShapeId()
      editor.createShape({
        id: shapeId,
        type: "draw",
        x: minX,
        y: minY,
        props: {
          color: p.color || "black",
          fill: "none",
          dash: "draw",
          size: "s",
          segments: [{ type: "free", path: encoded }],
          isComplete: true,
          isClosed: !!p.closed,
          isPen: false,
        },
      })
      break
    }

    // ── Precision move (anchor-aware, from tldraw template) ─────────────────
    // Unlike the old move_shape which just set x/y, this correctly accounts for
    // the offset between a shape's origin and its visible bounds,
    // and moves to the specified anchor point on the shape.

    case "move_shape": {
      const shapeId = toTldrawId(p.shapeId)
      if (!shapeId) break
      const shape = editor.getShape(shapeId)
      if (!shape) break

      const shapeBounds = editor.getShapePageBounds(shapeId)
      if (!shapeBounds) break

      const targetX = p.x ?? shape.x
      const targetY = p.y ?? shape.y
      const anchor = p.anchor ?? "top-left"

      // Offset between shape record origin and its page bounds top-left
      const originDeltaX = shape.x - shapeBounds.minX
      const originDeltaY = shape.y - shapeBounds.minY

      // Anchor offsets
      const anchorOffsets = {
        "top-left":      [0,                   0],
        "top-center":    [shapeBounds.w / 2,    0],
        "top-right":     [shapeBounds.w,        0],
        "center-left":   [0,                   shapeBounds.h / 2],
        "center":        [shapeBounds.w / 2,    shapeBounds.h / 2],
        "center-right":  [shapeBounds.w,        shapeBounds.h / 2],
        "bottom-left":   [0,                   shapeBounds.h],
        "bottom-center": [shapeBounds.w / 2,    shapeBounds.h],
        "bottom-right":  [shapeBounds.w,        shapeBounds.h],
      }

      const [ax, ay] = anchorOffsets[anchor] ?? [0, 0]
      const newX = targetX - ax + originDeltaX
      const newY = targetY - ay + originDeltaY

      editor.updateShape({ id: shapeId, type: shape.type, x: newX, y: newY })
      break
    }

    // ── Place shape relative to another shape (NEW, from tldraw template) ───
    // "place the diagram to the right of the title, centered"

    case "place_shape": {
      const shapeId = toTldrawId(p.shapeId)
      const refId = toTldrawId(p.referenceShapeId)
      if (!shapeId || !refId) break

      const shape = editor.getShape(shapeId)
      const refShape = editor.getShape(refId)
      if (!shape || !refShape) break

      const bbA = editor.getShapePageBounds(shapeId)
      const bbR = editor.getShapePageBounds(refId)
      if (!bbA || !bbR) break

      const side = p.side ?? "right"
      const align = p.align ?? "center"
      const sideOffset = p.sideOffset ?? 20
      const alignOffset = p.alignOffset ?? 0

      let newX = shape.x
      let newY = shape.y

      if (side === "right") {
        newX = bbR.maxX + sideOffset
        newY = align === "start" ? bbR.minY + alignOffset
          : align === "end" ? bbR.maxY - bbA.h - alignOffset
          : bbR.midY - bbA.h / 2 + alignOffset
      } else if (side === "left") {
        newX = bbR.minX - bbA.w - sideOffset
        newY = align === "start" ? bbR.minY + alignOffset
          : align === "end" ? bbR.maxY - bbA.h - alignOffset
          : bbR.midY - bbA.h / 2 + alignOffset
      } else if (side === "top") {
        newY = bbR.minY - bbA.h - sideOffset
        newX = align === "start" ? bbR.minX + alignOffset
          : align === "end" ? bbR.maxX - bbA.w - alignOffset
          : bbR.midX - bbA.w / 2 + alignOffset
      } else if (side === "bottom") {
        newY = bbR.maxY + sideOffset
        newX = align === "start" ? bbR.minX + alignOffset
          : align === "end" ? bbR.maxX - bbA.w - alignOffset
          : bbR.midX - bbA.w / 2 + alignOffset
      }

      editor.updateShape({ id: shapeId, type: shape.type, x: newX, y: newY })
      break
    }

    // ── Update existing shape (upgraded to support more props) ───────────────

    case "update_shape": {
      const shapeId = toTldrawId(p.shapeId)
      if (!shapeId) break
      const shape = editor.getShape(shapeId)
      if (!shape) break
      const props = { ...shape.props }
      if (p.text !== undefined) props.richText = toRichText(p.text)
      if (p.color !== undefined) props.color = normalizeTlColor(p.color, shape.props?.color ?? "black")
      if (p.fill !== undefined) props.fill = p.fill
      if (p.w !== undefined) props.w = p.w
      if (p.h !== undefined) props.h = p.h
      editor.updateShape({ id: shapeId, type: shape.type, props })
      break
    }

    // ── Resize (scale-based, from tldraw template) ───────────────────────────

    case "resize_shape": {
      // Supports both simple w/h and scale-based resize
      if (p.scaleX !== undefined && p.scaleY !== undefined) {
        const shapeIds = (p.shapeIds ?? [p.shapeId]).filter(Boolean).map(toTldrawId)
        const origin = { x: p.originX ?? 0, y: p.originY ?? 0 }
        for (const sid of shapeIds) {
          if (sid) editor.resizeShape(sid, { x: p.scaleX, y: p.scaleY }, { scaleOrigin: origin })
        }
      } else {
        // Simple w/h resize (backward compat)
        const shapeId = toTldrawId(p.shapeId)
        if (!shapeId) break
        const shape = editor.getShape(shapeId)
        if (shape) {
          editor.updateShape({ id: shapeId, type: shape.type, props: { w: p.w, h: p.h } })
        }
      }
      break
    }

    // ── Navigation ───────────────────────────────────────────────────────────

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
        editor.zoomToSelection(ids); editor.select(...ids)
      } else if (p.primaryShapeId && editor.getShape(p.primaryShapeId)) {
        editor.zoomToSelection([p.primaryShapeId]); editor.select(p.primaryShapeId)
      }
      break
    }

    // ── Edit ─────────────────────────────────────────────────────────────────

    case "delete_shapes":
      if (p.shapeIds?.length > 0) editor.deleteShapes(p.shapeIds)
      break

    case "clear_canvas": {
      const allIds = [...editor.getCurrentPageShapeIds()]
      if (allIds.length > 0) editor.deleteShapes(allIds)
      break
    }

    case "select_shapes":
      if (p.shapeIds?.length > 0) editor.select(...p.shapeIds)
      break

    case "align_shapes":
      editor.alignShapes(p.shapeIds, p.alignment)
      break

    case "distribute_shapes":
      editor.distributeShapes(p.shapeIds, p.direction)
      break

    case "group_shapes":
      editor.groupShapes(p.shapeIds)
      break

    case "label_shape": {
      const shape = editor.getShape(p.shapeId)
      if (shape) {
        editor.updateShape({
          id: p.shapeId, type: shape.type,
          meta: { ...shape.meta, semanticRole: p.semanticRole ?? "unknown", addedBy: p.addedBy ?? "live_agent" },
        })
      }
      break
    }

    case "create_frame": {
      editor.createShape({
        id: resolveShapeId(p.id),
        type: "frame",
        x: p.x ?? 0, y: p.y ?? 0,
        props: { w: p.w ?? 800, h: p.h ?? 600, name: p.name ?? "Frame" },
      })
      break
    }

    case "undo":
      editor.undo()
      break

    case "redo":
      editor.redo()
      break

    // ── Audio (delegated to AudioPlayback) ───────────────────────────────────

    case "audio_response":
      if (audioCallbacks?.onAudio) audioCallbacks.onAudio(p.data)
      break

    case "ai_interrupted":
      if (audioCallbacks?.onInterrupt) audioCallbacks.onInterrupt()
      break

    // ── Internal (handled upstream, ignored here) ─────────────────────────────

    case "ai_status":
    case "canvas_snapshot":
    case "config_ack":
    case "task_dashboard":
      break

    default:
      console.warn("[AlphaSurface] Unknown message type:", message.type)
  }
}
