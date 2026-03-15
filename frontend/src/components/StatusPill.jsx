// ── StatusPill ────────────────────────────────────────────────────────────────
// Top-center floating pill showing AI status, mode, and mic state.
// Clicking it toggles mute.

const STATUS = {
  idle:         { label: "Active",     dot: "#10b981", pulse: false },
  listening:    { label: "Listening",  dot: "#10b981", pulse: true  },
  thinking:     { label: "Thinking…",  dot: "#f59e0b", pulse: true  },
  speaking:     { label: "Speaking",   dot: "#06b6d4", pulse: true  },
  disconnected: { label: "Offline",    dot: "#6b7280", pulse: false },
}

export function StatusPill({ aiStatus, listening, muted, speakerMuted, config, onToggleMute, onToggleSpeaker }) {
  const status = (
    aiStatus === "idle" && listening && !muted && config.voiceEnabled
      ? STATUS.listening
      : (STATUS[aiStatus] ?? STATUS.disconnected)
  )

  return (
    <>
      <div
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
          userSelect: "none", outline: "none", WebkitAppearance: "none",
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
        {/* Status section */}
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

        <div style={{ width: 1, height: 12, background: "rgba(255,255,255,0.08)", flexShrink: 0 }} />

        {/* Mode/web/mic section */}
        <div style={{ display: "flex", alignItems: "center", gap: 5, padding: "5px 10px" }}>
          <span style={{ color: "rgba(255,255,255,0.48)", textTransform: "capitalize" }}>{config.mode}</span>
          {config.webSearch && (
            <span style={{ color: "#60a5fa", fontSize: 9, fontWeight: 700, letterSpacing: "0.05em", padding: "1px 5px", borderRadius: 4, background: "rgba(96,165,250,0.1)" }}>WEB</span>
          )}
          <button
            onClick={onToggleMute}
            title={muted ? "Click to unmute mic" : "Click to mute mic"}
            style={{
              background: "none", border: "none", padding: 0, margin: 0, cursor: "pointer",
              outline: "none", display: "flex", alignItems: "center"
            }}
          >
            {muted || !config.voiceEnabled ? (
              <span style={{ color: "#f87171", fontSize: 9, fontWeight: 700, letterSpacing: "0.05em", padding: "1px 5px", borderRadius: 4, background: "rgba(248,113,113,0.12)" }}>MIC OFF</span>
            ) : (
              <span style={{ color: "#34d399", fontSize: 9, fontWeight: 700, letterSpacing: "0.05em", padding: "1px 5px", borderRadius: 4, background: "rgba(52,211,153,0.1)" }}>MIC ON</span>
            )}
          </button>
        </div>

        <div style={{ width: 1, height: 12, background: "rgba(255,255,255,0.08)", flexShrink: 0 }} />

        {/* Speaker section */}
        <div style={{ display: "flex", alignItems: "center", gap: 5, padding: "5px 13px 5px 10px" }}>
          <button
            onClick={onToggleSpeaker}
            title={speakerMuted ? "Click to unmute speaker" : "Click to mute speaker"}
            style={{
              background: "none", border: "none", padding: 0, margin: 0, cursor: "pointer",
              outline: "none", display: "flex", alignItems: "center"
            }}
          >
            {speakerMuted ? (
              <span style={{ color: "#f87171", fontSize: 9, fontWeight: 700, letterSpacing: "0.05em", padding: "1px 5px", borderRadius: 4, background: "rgba(248,113,113,0.12)" }}>SPEAKER OFF</span>
            ) : (
              <span style={{ color: "#34d399", fontSize: 9, fontWeight: 700, letterSpacing: "0.05em", padding: "1px 5px", borderRadius: 4, background: "rgba(52,211,153,0.1)" }}>SPEAKER ON</span>
            )}
          </button>
        </div>
      </div>

      <style>{`
        @keyframes sPulse { 0%,100% { opacity:1; } 50% { opacity:.4; } }
        button:focus { outline: none; }
      `}</style>
    </>
  )
}
