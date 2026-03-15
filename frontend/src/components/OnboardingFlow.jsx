import React, { useState, useEffect, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Brain, Presentation, ArrowRight, Github, Twitter, Linkedin } from "lucide-react";

const FONTS = `@import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700;800;900&family=JetBrains+Mono:wght@300;400;500&display=swap');`;

const SNAP = { duration: 0.3, ease: [0.4, 0, 0.2, 1] };
const RISE = { duration: 0.55, ease: [0.16, 1, 0.3, 1] };

export function OnboardingFlow({ onComplete }) {
  const [step, setStep] = useState(0);
  const [mode, setMode] = useState(null);
  const [goal, setGoal] = useState("");
  const [audience, setAudience] = useState(null);
  const [uploadedFileName, setUploadedFileName] = useState("");
  const [uploading, setUploading] = useState(false);
  const [hovered, setHovered] = useState(null);
  const inputRef = useRef(null);

  useEffect(() => {
    if (step === 2) setTimeout(() => inputRef.current?.focus(), 300);
  }, [step]);

  useEffect(() => {
    const onKey = (e) => { if (e.key === "Escape" && step > 0) setStep(s => s - 1); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [step]);

  const handleModeSelect = (m) => { setMode(m); setStep(2); };
  const handleFinish = () => {
    onComplete({ mode, goal: goal.trim(), audience, uploadedFile: uploadedFileName, voiceEnabled: true, webSearch: false, mcps: [] });
  };

  const handleUpload = () => {
    const input = Object.assign(document.createElement("input"), { type: "file", accept: ".pdf,.doc,.docx,.txt" });
    input.onchange = async (e) => {
      const file = e.target.files?.[0];
      if (!file) return;
      setUploading(true);
      const fd = new FormData();
      fd.append("file", file);
      try {
        const res = await fetch("/api/upload", { method: "POST", body: fd });
        const data = await res.json();
        if (data.status === "success") setUploadedFileName(file.name);
      } catch { }
      finally { setUploading(false); }
    };
    input.click();
  };

  return (
    <>
      <style>{`
        ${FONTS}
        *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
        :root {
          --bg: #030507;
          --surface: rgba(255,255,255,0.035);
          --surface-hover: rgba(255,255,255,0.06);
          --border: rgba(255,255,255,0.08);
          --border-glow: rgba(0,212,245,0.3);
          --cyan: #00d4f5;
          --violet: #7c5cbf;
          --rose: #e8547a;
          --text: #f0f2f5;
          --muted: rgba(240,242,245,0.45);
          --muted2: rgba(240,242,245,0.25);
        }
        .alpha-root {
          position: fixed; inset: 0;
          background: var(--bg);
          font-family: 'Outfit', sans-serif;
          color: var(--text);
          overflow: hidden;
        }
        .mono { font-family: 'JetBrains Mono', monospace; }

        /* Noise overlay */
        .alpha-root::before {
          content: '';
          position: fixed; inset: 0;
          background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)' opacity='0.03'/%3E%3C/svg%3E");
          pointer-events: none; z-index: 0; opacity: 0.4;
        }

        /* Glass card */
        .glass {
          background: var(--surface);
          border: 1px solid var(--border);
          backdrop-filter: blur(24px);
          -webkit-backdrop-filter: blur(24px);
          border-radius: 20px;
          transition: border-color 0.3s, background 0.3s, box-shadow 0.3s;
        }
        .glass:hover {
          border-color: rgba(255,255,255,0.14);
          background: var(--surface-hover);
        }

        /* Mode card iridescent border on hover */
        .mode-card-think:hover {
          border-color: rgba(124,92,191,0.5) !important;
          box-shadow: 0 0 40px rgba(124,92,191,0.12), inset 0 1px 0 rgba(255,255,255,0.06) !important;
        }
        .mode-card-present:hover {
          border-color: rgba(0,212,245,0.5) !important;
          box-shadow: 0 0 40px rgba(0,212,245,0.12), inset 0 1px 0 rgba(255,255,255,0.06) !important;
        }

        /* Tag buttons */
        .tag {
          padding: 9px 20px; border-radius: 100px;
          font-size: 13px; font-weight: 500; cursor: pointer;
          transition: all 0.18s;
          border: 1px solid var(--border);
          background: transparent; color: var(--muted);
          font-family: 'Outfit', sans-serif;
        }
        .tag:hover { border-color: rgba(255,255,255,0.2); color: var(--text); }
        .tag.active {
          background: rgba(0,212,245,0.1);
          border-color: rgba(0,212,245,0.4);
          color: var(--cyan);
        }

        /* Input */
        .alpha-input {
          width: 100%;
          background: rgba(255,255,255,0.04);
          border: 1px solid var(--border);
          border-radius: 14px;
          padding: 18px 64px 18px 22px;
          font-size: 16px; font-family: 'Outfit', sans-serif;
          color: var(--text);
          transition: border-color 0.2s, box-shadow 0.2s;
        }
        .alpha-input:focus {
          border-color: rgba(0,212,245,0.4);
          box-shadow: 0 0 0 3px rgba(0,212,245,0.08);
          outline: none;
        }
        .alpha-input::placeholder { color: var(--muted2); }

        /* Upload zone */
        .upload-zone {
          width: 100%; border: 1.5px dashed rgba(255,255,255,0.1);
          border-radius: 14px; padding: 22px 24px;
          background: transparent; cursor: pointer;
          transition: border-color 0.2s, background 0.2s;
          text-align: left; font-family: 'Outfit', sans-serif;
          display: flex; align-items: center; gap: 16px;
        }
        .upload-zone:hover {
          border-color: rgba(0,212,245,0.3);
          background: rgba(0,212,245,0.04);
        }
        .upload-success {
          border: 1px solid rgba(74,220,128,0.3);
          border-radius: 14px; padding: 16px 20px;
          background: rgba(74,220,128,0.06);
          display: flex; align-items: center; justify-content: space-between; gap: 12px;
        }

        /* Primary button */
        .btn-primary {
          display: inline-flex; align-items: center; gap: 10px;
          background: linear-gradient(135deg, rgba(0,212,245,0.15), rgba(124,92,191,0.15));
          border: 1px solid rgba(0,212,245,0.3);
          border-radius: 12px; padding: 16px 32px;
          font-size: 15px; font-weight: 600; font-family: 'Outfit', sans-serif;
          color: var(--text); cursor: pointer;
          transition: all 0.2s;
          box-shadow: 0 0 24px rgba(0,212,245,0.08);
        }
        .btn-primary:hover {
          background: linear-gradient(135deg, rgba(0,212,245,0.22), rgba(124,92,191,0.22));
          border-color: rgba(0,212,245,0.5);
          box-shadow: 0 0 40px rgba(0,212,245,0.15);
          transform: translateY(-1px);
        }

        /* Back link */
        .back-link {
          background: none; border: none;
          color: var(--muted); font-size: 13px;
          cursor: pointer; font-family: 'JetBrains Mono', monospace;
          letter-spacing: 0.04em; transition: color 0.15s;
        }
        .back-link:hover { color: var(--text); }

        ::-webkit-scrollbar { display: none; }
      `}</style>

      <div className="alpha-root">

        {/* ── Ambient background glows ── */}
        <div style={{ position: "fixed", inset: 0, pointerEvents: "none", zIndex: 0 }}>
          {/* Cyan glow top-left */}
          <div style={{
            position: "absolute", top: "-20%", left: "-10%",
            width: "60vw", height: "60vw",
            background: "radial-gradient(circle, rgba(0,212,245,0.07) 0%, transparent 65%)",
            filter: "blur(60px)"
          }} />
          {/* Violet glow center */}
          <div style={{
            position: "absolute", top: "20%", left: "30%",
            width: "50vw", height: "50vw",
            background: "radial-gradient(circle, rgba(124,92,191,0.06) 0%, transparent 65%)",
            filter: "blur(80px)"
          }} />
          {/* Rose glow bottom-right */}
          <div style={{
            position: "absolute", bottom: "-10%", right: "-10%",
            width: "45vw", height: "45vw",
            background: "radial-gradient(circle, rgba(232,84,122,0.06) 0%, transparent 65%)",
            filter: "blur(70px)"
          }} />
        </div>

        <AnimatePresence mode="wait">

          {/* ══ STEP 0: WELCOME ══ */}
          {step === 0 && (
            <motion.div key="s0"
              initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
              transition={SNAP}
              style={{ position: "absolute", inset: 0, zIndex: 1, display: "flex", alignItems: "center", justifyContent: "center", padding: "6vh 8vw" }}
            >
              <div style={{ display: "flex", flexDirection: "column", alignItems: "center", textAlign: "center", maxWidth: 700, width: "100%" }}>

                {/* Logo */}
                <motion.div
                  initial={{ scale: 0.85, opacity: 0 }} animate={{ scale: 1, opacity: 1 }}
                  transition={{ ...RISE, delay: 0.1 }}
                  style={{ marginBottom: 40, position: "relative" }}
                >
                  <motion.div
                    animate={{ y: [0, -12, 0] }}
                    transition={{ duration: 5, ease: "easeInOut", repeat: Infinity }}
                  >
                    <img src="/logo.png" alt="AlphaSurface"
                      style={{
                        width: 140, height: 140, objectFit: "contain",
                        filter: "drop-shadow(0 0 40px rgba(0,212,245,0.35)) drop-shadow(0 0 80px rgba(124,92,191,0.25))"
                      }}
                    />
                  </motion.div>
                  {/* Glow ring */}
                  <div style={{
                    position: "absolute", inset: -20,
                    background: "radial-gradient(circle, rgba(0,212,245,0.08) 0%, transparent 70%)",
                    borderRadius: "50%", pointerEvents: "none"
                  }} />
                </motion.div>

                {/* Wordmark */}
                <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ ...RISE, delay: 0.2 }}>
                  <div style={{ fontFamily: "'JetBrains Mono'", fontSize: 11, letterSpacing: "0.2em", textTransform: "uppercase", color: "var(--cyan)", marginBottom: 16, opacity: 0.8 }}>
                    ◆ Spatial AI Workspace
                  </div>
                  <h1 style={{ fontSize: "clamp(52px, 9vw, 88px)", fontWeight: 800, letterSpacing: "-0.04em", lineHeight: 0.95, marginBottom: 24 }}>
                    Alpha
                    <span style={{
                      background: "linear-gradient(135deg, var(--cyan), var(--violet), var(--rose))",
                      WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent",
                      backgroundClip: "text"
                    }}>Surface</span>
                  </h1>
                  <p style={{ fontSize: 18, color: "var(--muted)", lineHeight: 1.65, marginBottom: 48, maxWidth: 480, margin: "0 auto 48px" }}>
                    AI that thinks alongside you — not for you.<br />
                    Voice-first. Spatially aware. Genuinely curious.
                  </p>
                </motion.div>

                {/* CTA */}
                <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ ...RISE, delay: 0.4 }}>
                  <button className="btn-primary" onClick={() => setStep(1)}>
                    Begin session <ArrowRight size={17} />
                  </button>
                </motion.div>

                {/* Social links */}
                <motion.div
                  initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.7 }}
                  style={{ display: "flex", gap: 28, marginTop: 56, alignItems: "center" }}
                >
                  {[
                    { icon: <Github size={14} />, label: "GitHub", href: "https://github.com/adr1en360/AlphaSurface" },
                    { icon: <Twitter size={14} />, label: "X", href: "https://x.com/artiflux360" },
                    { icon: <Linkedin size={14} />, label: "LinkedIn", href: "https://www.linkedin.com/in/adrienoke/" },
                  ].map(({ icon, label, href }) => (
                    <a key={label} href={href} target="_blank" rel="noopener noreferrer"
                      style={{ display: "flex", alignItems: "center", gap: 7, color: "var(--muted)", textDecoration: "none", fontSize: 13, fontFamily: "'JetBrains Mono'", transition: "color 0.15s", letterSpacing: "0.03em" }}
                      onMouseEnter={(e) => e.currentTarget.style.color = "var(--text)"}
                      onMouseLeave={(e) => e.currentTarget.style.color = "var(--muted)"}
                    >
                      {icon}{label}
                    </a>
                  ))}
                  <span style={{ color: "var(--muted2)", fontSize: 11, fontFamily: "'JetBrains Mono'", letterSpacing: "0.06em", marginLeft: 8 }}>
                    Gemini Live · Google ADK
                  </span>
                </motion.div>
              </div>
            </motion.div>
          )}

          {/* ══ STEP 1: MODE ══ */}
          {step === 1 && (
            <motion.div key="s1"
              initial={{ opacity: 0, y: 40 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -20 }}
              transition={RISE}
              style={{ position: "absolute", inset: 0, zIndex: 1, display: "flex", alignItems: "center", justifyContent: "center", padding: "8vh 8vw" }}
            >
              <div style={{ width: "100%", maxWidth: 780 }}>
                <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.1 }}
                  style={{ fontFamily: "'JetBrains Mono'", fontSize: 10, color: "var(--cyan)", letterSpacing: "0.16em", textTransform: "uppercase", marginBottom: 20, opacity: 0.8 }}
                >
                  01 / session type
                </motion.div>
                <motion.h2 initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ ...RISE, delay: 0.15 }}
                  style={{ fontSize: "clamp(30px, 5vw, 52px)", fontWeight: 800, letterSpacing: "-0.03em", marginBottom: 10 }}
                >
                  How are you working today?
                </motion.h2>
                <motion.p initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.25 }}
                  style={{ color: "var(--muted)", fontSize: 16, marginBottom: 44 }}
                >
                  AlphaSurface reshapes itself entirely around your context.
                </motion.p>

                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 18, marginBottom: 36 }}>
                  {[
                    {
                      cls: "mode-card-think", m: "think",
                      color: "var(--violet)", colorRgb: "124,92,191",
                      icon: <Brain size={26} color="#7c5cbf" />,
                      label: "Think Mode",
                      sub: "Solo exploration",
                      desc: "You develop ideas. The AI watches, listens, and injects provocations — open questions that reframe your thinking. It never answers for you."
                    },
                    {
                      cls: "mode-card-present", m: "explain",
                      color: "var(--cyan)", colorRgb: "0,212,245",
                      icon: <Presentation size={26} color="#00d4f5" />,
                      label: "Present Mode",
                      sub: "Live presentation",
                      desc: "You present, the AI scribes in real time. Dates, concepts, visuals land on canvas as you speak. Silent unless asked. Always one step behind by design."
                    },
                  ].map(({ cls, m, color, colorRgb, icon, label, sub, desc }, i) => (
                    <motion.button key={m}
                      className={`glass ${cls}`}
                      onClick={() => handleModeSelect(m)}
                      initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
                      transition={{ ...RISE, delay: 0.3 + i * 0.1 }}
                      onMouseEnter={() => setHovered(m)}
                      onMouseLeave={() => setHovered(null)}
                      style={{
                        padding: "36px 32px", textAlign: "left", cursor: "pointer",
                        position: "relative", overflow: "hidden",
                        transition: "all 0.3s",
                      }}
                    >
                      {/* Hover shimmer */}
                      <motion.div
                        animate={{ opacity: hovered === m ? 1 : 0 }}
                        transition={{ duration: 0.3 }}
                        style={{
                          position: "absolute", top: 0, left: 0, right: 0, height: 1,
                          background: `linear-gradient(90deg, transparent, rgba(${colorRgb},0.6), transparent)`,
                        }}
                      />
                      <div style={{ marginBottom: 20 }}>{icon}</div>
                      <div style={{ fontFamily: "'JetBrains Mono'", fontSize: 10, color: color, letterSpacing: "0.1em", textTransform: "uppercase", marginBottom: 8, opacity: 0.8 }}>{sub}</div>
                      <div style={{ fontSize: 22, fontWeight: 700, letterSpacing: "-0.02em", marginBottom: 14, color: "#fff" }}>{label}</div>
                      <div style={{ fontSize: 14, color: "#fff", lineHeight: 1.7 }}>{desc}</div>
                      <div style={{ position: "absolute", bottom: 24, right: 24, opacity: 0.2 }}>
                        <ArrowRight size={16} />
                      </div>
                    </motion.button>
                  ))}
                </div>

                <button className="back-link" onClick={() => setStep(0)}>← back</button>
              </div>
            </motion.div>
          )}

          {/* ══ STEP 2: SETUP ══ */}
          {step === 2 && (
            <motion.div key="s2"
              initial={{ opacity: 0, y: 40 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -20 }}
              transition={RISE}
              style={{ position: "absolute", inset: 0, zIndex: 1, display: "flex", alignItems: "center", justifyContent: "center", padding: "8vh 8vw" }}
            >
              <div style={{ width: "100%", maxWidth: 620 }}>
                <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.1 }}
                  style={{ fontFamily: "'JetBrains Mono'", fontSize: 10, color: "var(--cyan)", letterSpacing: "0.16em", textTransform: "uppercase", marginBottom: 20, opacity: 0.8 }}
                >
                  02 / {mode === "explain" ? "presentation setup" : "session focus"}
                </motion.div>
                <motion.h2 initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ ...RISE, delay: 0.15 }}
                  style={{ fontSize: "clamp(26px, 4vw, 42px)", fontWeight: 800, letterSpacing: "-0.03em", marginBottom: 10 }}
                >
                  {mode === "explain" ? "Set up your presentation" : "What are you exploring?"}
                </motion.h2>
                <motion.p initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.2 }}
                  style={{ color: "var(--muted)", fontSize: 15, marginBottom: 36 }}
                >
                  Optional — helps AlphaSurface orient immediately.
                </motion.p>

                {/* Goal input */}
                <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ ...RISE, delay: 0.25 }}
                  style={{ position: "relative", marginBottom: 28 }}
                >
                  <input ref={inputRef} className="alpha-input"
                    value={goal}
                    onChange={(e) => setGoal(e.target.value)}
                    onKeyDown={(e) => { if (e.key === "Enter") handleFinish(); }}
                    placeholder={mode === "explain" ? "e.g. Quarterly business review for the board..." : "e.g. Mapping a new product architecture..."}
                  />
                  <motion.button
                    animate={{ opacity: goal.length > 0 ? 1 : 0.3 }}
                    onClick={goal.length > 0 ? handleFinish : undefined}
                    style={{
                      position: "absolute", right: 10, top: "50%", transform: "translateY(-50%)",
                      width: 40, height: 40, borderRadius: 10,
                      background: goal.length > 0 ? "linear-gradient(135deg, rgba(0,212,245,0.2), rgba(124,92,191,0.2))" : "transparent",
                      border: goal.length > 0 ? "1px solid rgba(0,212,245,0.3)" : "1px solid rgba(255,255,255,0.06)",
                      display: "flex", alignItems: "center", justifyContent: "center",
                      cursor: goal.length > 0 ? "pointer" : "default",
                      transition: "all 0.2s"
                    }}
                  >
                    <ArrowRight size={16} color={goal.length > 0 ? "var(--cyan)" : "var(--muted)"} />
                  </motion.button>
                </motion.div>

                {/* Explain mode extras */}
                {mode === "explain" && (
                  <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ ...RISE, delay: 0.35 }}
                    style={{ display: "flex", flexDirection: "column", gap: 28, marginBottom: 28 }}
                  >
                    {/* Audience */}
                    <div>
                      <div style={{ fontFamily: "'JetBrains Mono'", fontSize: 10, color: "var(--muted)", letterSpacing: "0.1em", textTransform: "uppercase", marginBottom: 14 }}>
                        Audience
                      </div>
                      <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
                        {["Students", "Colleagues", "General Audience"].map((a) => (
                          <button key={a} className={`tag ${audience === a ? "active" : ""}`}
                            onClick={() => setAudience(a)}>{a}</button>
                        ))}
                      </div>
                    </div>

                    {/* File upload */}
                    <div>
                      <div style={{ fontFamily: "'JetBrains Mono'", fontSize: 10, color: "var(--muted)", letterSpacing: "0.1em", textTransform: "uppercase", marginBottom: 14 }}>
                        Reference material
                      </div>
                      {!uploadedFileName ? (
                        <button className="upload-zone" onClick={handleUpload} disabled={uploading}>
                          <div style={{ width: 36, height: 36, borderRadius: 8, background: "rgba(255,255,255,0.05)", border: "1px solid var(--border)", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                            <span style={{ fontSize: 16 }}>{uploading ? "⏳" : "📎"}</span>
                          </div>
                          <div>
                            <div style={{ fontSize: 14, fontWeight: 500, color: "var(--text)", marginBottom: 3 }}>
                              {uploading ? "Uploading..." : "Upload PDF / Docx notes"}
                            </div>
                            <div style={{ fontSize: 12, color: "var(--muted)" }}>
                              Agent uses this for grounded, accurate responses
                            </div>
                          </div>
                        </button>
                      ) : (
                        <div className="upload-success">
                          <div style={{ display: "flex", alignItems: "center", gap: 14, minWidth: 0 }}>
                            <div style={{ width: 36, height: 36, borderRadius: 8, background: "rgba(74,220,128,0.1)", border: "1px solid rgba(74,220,128,0.3)", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                              <span style={{ fontSize: 16 }}>✓</span>
                            </div>
                            <div style={{ minWidth: 0 }}>
                              <div style={{ fontSize: 14, fontWeight: 600, color: "#4adc80", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                                {uploadedFileName}
                              </div>
                              <div style={{ fontFamily: "'JetBrains Mono'", fontSize: 11, color: "var(--muted)", marginTop: 3 }}>
                                Loaded · Agent will reference this
                              </div>
                            </div>
                          </div>
                          <button
                            onClick={() => setUploadedFileName("")}
                            style={{
                              background: "rgba(232,84,122,0.08)", border: "1px solid rgba(232,84,122,0.25)",
                              color: "var(--rose)", borderRadius: 8, padding: "7px 16px",
                              fontFamily: "'JetBrains Mono'", fontSize: 11, letterSpacing: "0.04em",
                              cursor: "pointer", flexShrink: 0, textTransform: "uppercase",
                              transition: "background 0.15s", fontWeight: 500
                            }}
                            onMouseEnter={(e) => e.currentTarget.style.background = "rgba(232,84,122,0.16)"}
                            onMouseLeave={(e) => e.currentTarget.style.background = "rgba(232,84,122,0.08)"}
                          >
                            Remove
                          </button>
                        </div>
                      )}
                    </div>
                  </motion.div>
                )}

                {/* Footer nav */}
                <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.5 }}
                  style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}
                >
                  <button className="back-link" onClick={() => setStep(1)}>← back</button>
                  <button className="back-link" onClick={handleFinish} style={{ color: "var(--muted)" }}>
                    {mode === "explain" ? "start presentation →" : "skip, start canvas →"}
                  </button>
                </motion.div>
              </div>
            </motion.div>
          )}

        </AnimatePresence>
      </div>
    </>
  );
}

export default OnboardingFlow;