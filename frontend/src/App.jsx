// ── App.jsx ───────────────────────────────────────────────────────────────────
// Root component. Was 1264 lines. Now 50.
// All logic lives in dedicated modules.

import { useCallback, useState } from "react"
import { Tldraw } from "tldraw"
import "tldraw/tldraw.css"

import { activatePlaybackContext, setPlaybackEnabled } from "./audio/AudioPlayback"
import { AlphaSurfaceInner } from "./agent/AlphaSurfaceInner"
import { AlphaMainMenu } from "./components/AlphaMainMenu"
import { OnboardingFlow } from "./components/OnboardingFlow"

export default function App() {
  const [config, setConfig] = useState(() => {
    const saved = localStorage.getItem("alpha_surface_config")
    if (saved) {
      try { return JSON.parse(saved) } catch { return null }
    }
    return null
  })

  const handleLaunch = useCallback((cfg) => {
    setPlaybackEnabled(cfg.voiceEnabled)
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
