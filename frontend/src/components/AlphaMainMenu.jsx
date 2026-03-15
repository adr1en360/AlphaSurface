// ── AlphaMainMenu ─────────────────────────────────────────────────────────────
// Custom tldraw main menu with Save / Load / Export PDF / Upload Document

import { useEditor, toRichText, createShapeId, getSnapshot, loadSnapshot, DefaultMainMenu, DefaultMainMenuContent, TldrawUiMenuGroup, TldrawUiMenuItem } from "tldraw"
import { jsPDF } from "jspdf"

export function AlphaMainMenu() {
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
      const res = await fetch(url, { method: "GET", signal: controller.signal, cache: "no-store" })
      return res.ok
    } catch { return false }
    finally { clearTimeout(timeoutId) }
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
        if (!pagesByUrl.has(src)) pagesByUrl.set(src, new Set())
        pagesByUrl.get(src).add(page.name || "Untitled page")
      }
    }
    const failures = []
    const checks = await Promise.all([...pagesByUrl.keys()].map(async (src) => ({ src, ok: await isAssetReachable(src) })))
    for (const check of checks) {
      if (check.ok) continue
      for (const pageName of pagesByUrl.get(check.src)) failures.push({ pageName, src: check.src })
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
    const pagesWithShapes = pages.map((page) => ({ page, shapeIds: [...editor.getPageShapeIds(page.id)] }))
    if (pagesWithShapes.every(({ shapeIds }) => shapeIds.length === 0)) return
    const originalPageId = editor.getCurrentPageId()
    try {
      const unreachableAssets = await getUnreachableImageAssets(pagesWithShapes)
      if (unreachableAssets.length > 0) {
        throw new Error(`Export blocked: image on page "${unreachableAssets[0].pageName}" is unreachable.`)
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
          editor.toImage(liveShapeIds, { format: "png", background: true, padding: 32 }),
          new Promise((_, reject) => setTimeout(() => reject(new Error(`Timed out`)), 12000)),
        ])
        const dataUrl = await blobToDataUrl(blob)
        const img = await loadImage(dataUrl)
        if (wrotePage) pdf.addPage("a4", "portrait")
        const pageW = pdf.internal.pageSize.getWidth()
        const pageH = pdf.internal.pageSize.getHeight()
        const headerY = 28, headerGap = 18
        const usableW = pageW - 48, usableH = pageH - 64 - headerGap
        const scale = Math.min(usableW / img.width, usableH / img.height)
        const drawW = img.width * scale, drawH = img.height * scale
        const x = (pageW - drawW) / 2, y = headerY + headerGap
        pdf.setFontSize(11); pdf.setTextColor(90, 90, 90)
        pdf.text(page.name || "Untitled page", 24, headerY)
        pdf.addImage(dataUrl, "PNG", x, y, drawW, drawH, undefined, "FAST")
        wrotePage = true
      }
      if (wrotePage) pdf.save("alphasurface-export.pdf")
    } catch (err) {
      console.error("[AlphaSurface] PDF export failed", err)
      window.alert(err instanceof Error ? err.message : "PDF export failed.")
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
        const res = await fetch("/api/upload", { method: "POST", body: formData })
        const data = await res.json()
        if (data.status === "success") {
          const vp = editor.getViewportPageBounds()
          editor.createShape({
            id: createShapeId(), type: "note",
            x: (vp?.x ?? 0) + Math.max(40, (vp?.w ?? 1000) * 0.25),
            y: (vp?.y ?? 0) + Math.max(40, (vp?.h ?? 700) * 0.2),
            props: { richText: toRichText(`📄 ${file.name}`), color: "blue", size: "m" },
          })
        }
      } catch (err) { console.error("Upload failed", err) }
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
