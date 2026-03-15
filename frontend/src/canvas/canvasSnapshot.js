// ── Canvas snapshot builder ───────────────────────────────────────────────────
// Builds the three-tier snapshot sent to the Python backend via WebSocket.
// Replaces the flat shape list from the old App.jsx canvas_snapshot.
//
// The Python backend feeds this into Gemini's context so it understands
// the canvas spatially — not just as a flat list of all shapes.

import {
  convertToBlurryShape,
  convertToFocusedShape,
  convertToPeripheralClusters,
} from "./shapeConverters"

/**
 * Build and send the three-tier canvas snapshot over WebSocket.
 * Called periodically (every 3s) and immediately when shape count changes.
 *
 * @param {object} editor - tldraw editor instance
 * @param {WebSocket} ws - open WebSocket connection
 */
export function sendCanvasSnapshot(editor, ws) {
  if (!editor || !ws || ws.readyState !== WebSocket.OPEN) return

  const viewport = editor.getViewportPageBounds()
  const currentPage = editor.getCurrentPage()
  const currentPageId = currentPage.id
  const allShapes = editor.getCurrentPageShapes()
  const selectedIds = new Set(editor.getSelectedShapeIds())
  const pages = editor.getPages().map(p => ({
    id: p.id,
    name: p.name,
    shapeCount: editor.getPageShapeIds(p.id).size,
  }))

  // ── TIER 1: Blurry shapes (viewport shapes, lightweight) ─────────────────
  const shapesInViewport = allShapes.filter(shape => {
    const bounds = editor.getShapeMaskedPageBounds(shape)
    if (!bounds) return false
    return !(
      bounds.x + bounds.w < viewport.x ||
      bounds.x > viewport.x + viewport.w ||
      bounds.y + bounds.h < viewport.y ||
      bounds.y > viewport.y + viewport.h
    )
  })

  const blurryShapes = shapesInViewport
    .map(shape => convertToBlurryShape(editor, shape))
    .filter(Boolean)

  // ── TIER 2: Focused shapes (selected shapes, full detail) ─────────────────
  const selectedShapes = allShapes.filter(s => selectedIds.has(s.id))
  const focusedShapes = selectedShapes.map(shape => convertToFocusedShape(editor, shape))

  // Also include shapes with semantic roles (agent-placed content) that are
  // in viewport but not selected — these get upgraded to focused for better context
  const agentShapesInViewport = shapesInViewport.filter(
    s => !selectedIds.has(s.id) && s.meta?.addedBy && s.meta.addedBy !== "user"
  )
  const agentFocused = agentShapesInViewport
    .slice(0, 10) // cap to avoid flooding context
    .map(shape => convertToFocusedShape(editor, shape))

  const allFocused = [...focusedShapes, ...agentFocused]

  // ── TIER 3: Peripheral clusters (outside viewport, grouped) ───────────────
  const shapesOutsideViewport = allShapes.filter(shape => {
    const bounds = editor.getShapeMaskedPageBounds(shape)
    if (!bounds) return false
    return (
      bounds.x + bounds.w < viewport.x ||
      bounds.x > viewport.x + viewport.w ||
      bounds.y + bounds.h < viewport.y ||
      bounds.y > viewport.y + viewport.h
    )
  })

  const peripheralClusters = convertToPeripheralClusters(editor, shapesOutsideViewport)

  // ── Build and send ────────────────────────────────────────────────────────
  ws.send(JSON.stringify({
    type: "canvas_snapshot",
    payload: {
      // Three-tier context
      blurryShapes,
      focusedShapes: allFocused,
      peripheralClusters,

      // Selection
      selectedShapeIds: [...selectedIds].map(id =>
        id.startsWith("shape:") ? id.slice(6) : id
      ),

      // Page context
      currentPageId,
      currentPageName: currentPage.name,
      pages,
      shape_count: allShapes.length,

      // Viewport
      viewport: {
        x: Math.round(viewport.x),
        y: Math.round(viewport.y),
        w: Math.round(viewport.w),
        h: Math.round(viewport.h),
        zoom: editor.getZoomLevel(),
      },
    },
  }))
}
