// ── Shape converters — three-tier canvas context system ──────────────────────
// Adapted from tldraw agent-template shared/format/
// Gives Gemini spatially intelligent canvas understanding:
//   BlurryShape      — shapes in viewport (lightweight: id, type, bounds, text)
//   FocusedShape     — selected/context shapes (full detail: color, fill, etc.)
//   PeripheralCluster — shapes outside viewport (grouped by proximity)

// ── Type mapping: tldraw geo types → focused type names ──────────────────────
const GEO_TYPE_MAP = {
  rectangle: "rectangle",
  ellipse: "ellipse",
  triangle: "triangle",
  diamond: "diamond",
  hexagon: "hexagon",
  oval: "pill",
  cloud: "cloud",
  "x-box": "x-box",
  "check-box": "check-box",
  heart: "heart",
  pentagon: "pentagon",
  octagon: "octagon",
  star: "star",
  rhombus: "parallelogram-right",
  "rhombus-2": "parallelogram-left",
  trapezoid: "trapezoid",
  "arrow-right": "fat-arrow-right",
  "arrow-left": "fat-arrow-left",
  "arrow-up": "fat-arrow-up",
  "arrow-down": "fat-arrow-down",
}

// Strip "shape:" prefix for model-friendly IDs
function toSimpleId(shapeId) {
  return typeof shapeId === "string" && shapeId.startsWith("shape:")
    ? shapeId.slice(6)
    : shapeId
}

function getFocusedType(shape) {
  if (shape.type === "geo") return GEO_TYPE_MAP[shape.props?.geo] ?? "rectangle"
  if (["text", "line", "arrow", "note", "draw"].includes(shape.type)) return shape.type
  return "unknown"
}

function getShapeText(editor, shape) {
  try {
    const util = editor.getShapeUtil(shape)
    return util.getText(shape) ?? ""
  } catch {
    return shape.props?.text ?? ""
  }
}

// ── TIER 1: BlurryShape ───────────────────────────────────────────────────────
// Lightweight — used for all shapes visible in the agent's viewport
// Model sees: position, size, type, text only. No color, no fill details.

export function convertToBlurryShape(editor, shape) {
  const bounds = editor.getShapeMaskedPageBounds(shape)
  if (!bounds) return null
  const text = getShapeText(editor, shape)
  return {
    shapeId: toSimpleId(shape.id),
    type: getFocusedType(shape),
    x: Math.round(bounds.x),
    y: Math.round(bounds.y),
    w: Math.round(bounds.w),
    h: Math.round(bounds.h),
    ...(text ? { text } : {}),
  }
}

// ── TIER 2: FocusedShape ─────────────────────────────────────────────────────
// Full detail — used for selected shapes and shapes given as explicit context
// Model sees: all props including color, fill, text alignment, arrow bindings

export function convertToFocusedShape(editor, shape) {
  const bounds = editor.getShapePageBounds(shape)
  const text = getShapeText(editor, shape)
  const base = {
    shapeId: toSimpleId(shape.id),
    x: Math.round(bounds?.x ?? shape.x ?? 0),
    y: Math.round(bounds?.y ?? shape.y ?? 0),
    note: shape.meta?.note ?? "",
  }

  switch (shape.type) {
    case "note":
      return {
        ...base,
        _type: "note",
        text: text ?? "",
        color: shape.props?.color ?? "yellow",
      }

    case "text":
      return {
        ...base,
        _type: "text",
        text: text ?? "",
        color: shape.props?.color ?? "black",
        fontSize: shape.props?.size ?? "m",
        anchor: shape.props?.textAlign === "middle"
          ? "top-center"
          : shape.props?.textAlign === "end"
          ? "top-right"
          : "top-left",
        maxWidth: shape.props?.autoSize ? null : shape.props?.w ?? null,
      }

    case "geo":
      return {
        ...base,
        _type: GEO_TYPE_MAP[shape.props?.geo] ?? "rectangle",
        text: text ?? "",
        color: shape.props?.color ?? "blue",
        fill: shape.props?.fill ?? "none",
        w: Math.round(shape.props?.w ?? 200),
        h: Math.round(shape.props?.h ?? 120),
        textAlign: shape.props?.align ?? "middle",
      }

    case "arrow": {
      // Find bindings
      let fromId = null
      let toId = null
      try {
        const bindings = editor.store.query.records("binding").get()
        const arrowBindings = [...bindings].filter(
          b => b.type === "arrow" && b.fromId === shape.id
        )
        const startB = arrowBindings.find(b => b.props?.terminal === "start")
        const endB = arrowBindings.find(b => b.props?.terminal === "end")
        if (startB) fromId = toSimpleId(startB.toId)
        if (endB) toId = toSimpleId(endB.toId)
      } catch { /* bindings unavailable */ }

      return {
        ...base,
        _type: "arrow",
        color: shape.props?.color ?? "black",
        text: text ?? "",
        fromId,
        toId,
        x1: Math.round(base.x + (shape.props?.start?.x ?? 0)),
        y1: Math.round(base.y + (shape.props?.start?.y ?? 0)),
        x2: Math.round(base.x + (shape.props?.end?.x ?? 0)),
        y2: Math.round(base.y + (shape.props?.end?.y ?? 0)),
      }
    }

    case "draw":
      return {
        ...base,
        _type: "draw",
        color: shape.props?.color ?? "black",
        fill: shape.props?.fill ?? "none",
      }

    case "line":
      return {
        ...base,
        _type: "line",
        color: shape.props?.color ?? "black",
      }

    default:
      return {
        ...base,
        _type: "unknown",
        subType: shape.type,
      }
  }
}

// ── TIER 3: PeripheralCluster ─────────────────────────────────────────────────
// Shapes outside the viewport are grouped into spatial clusters.
// Model knows roughly how many shapes are off-screen and where, without
// wasting tokens on individual shape details.

export function convertToPeripheralClusters(editor, shapesOutsideViewport, padding = 75) {
  if (shapesOutsideViewport.length === 0) return []

  // Expand each shape's bounds by padding, then group overlapping ones
  const expanded = shapesOutsideViewport.map(shape => {
    const b = editor.getShapeMaskedPageBounds(shape)
    if (!b) return null
    return {
      shape,
      bounds: {
        x: b.x - padding,
        y: b.y - padding,
        w: b.w + padding * 2,
        h: b.h + padding * 2,
      },
    }
  }).filter(Boolean)

  const groups = []

  for (const item of expanded) {
    let landed = false
    for (const group of groups) {
      if (boundsIntersect(group.bounds, item.bounds)) {
        group.count++
        group.bounds = expandBounds(group.bounds, item.bounds)
        landed = true
        break
      }
    }
    if (!landed) {
      groups.push({ bounds: { ...item.bounds }, count: 1 })
    }
  }

  // Shrink back by padding
  return groups.map(g => ({
    numberOfShapes: g.count,
    bounds: {
      x: Math.round(g.bounds.x + padding),
      y: Math.round(g.bounds.y + padding),
      w: Math.round(g.bounds.w - padding * 2),
      h: Math.round(g.bounds.h - padding * 2),
    },
  }))
}

function boundsIntersect(a, b) {
  return !(
    a.x + a.w < b.x ||
    b.x + b.w < a.x ||
    a.y + a.h < b.y ||
    b.y + b.h < a.y
  )
}

function expandBounds(a, b) {
  const x = Math.min(a.x, b.x)
  const y = Math.min(a.y, b.y)
  const x2 = Math.max(a.x + a.w, b.x + b.w)
  const y2 = Math.max(a.y + a.h, b.y + b.h)
  return { x, y, w: x2 - x, h: y2 - y }
}
