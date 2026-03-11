import React, { useState, useEffect, useRef } from "react";
import { motion, AnimatePresence, useScroll, useTransform, useMotionValue, useSpring } from "framer-motion";
import { Brain, Presentation, ArrowRight, Github, Twitter, Linkedin, ChevronDown } from "lucide-react";

export function OnboardingFlow({ onComplete }) {
  const [step, setStep] = useState(0); // 0 = Welcome, 1 = Mode, 2 = Goal
  const [mode, setMode] = useState(null);
  const [goal, setGoal] = useState("");
  const [audience, setAudience] = useState(null);
  const [uploadedFileName, setUploadedFileName] = useState("");

  const handleModeSelect = (selectedMode) => {
    setMode(selectedMode);
    setStep(2);
  };

  const handleFinish = () => {
    localStorage.setItem("alpha_onboarding_complete", "true");
    onComplete({
      mode: mode,
      goal: goal.trim(),
      audience: audience,
      uploadedFile: uploadedFileName,
      voiceEnabled: true,
      webSearch: false,
      mcps: [] 
    });
  };

  const handleUploadClick = () => {
    const input = Object.assign(document.createElement("input"), { type: "file", accept: ".pdf,.doc,.docx,.txt" });
    input.onchange = async (e) => {
      const file = e.target.files?.[0];
      if (!file) return;
      const formData = new FormData();
      formData.append("file", file);
      try {
        const res = await fetch("/api/upload", {
          method: "POST",
          body: formData
        });
        const data = await res.json();
        if (data.status === "success") {
          setUploadedFileName(file.name);
        }
      } catch (err) {
        console.error("Upload failed", err);
      }
    };
    input.click();
  };

  // Mouse tracking for reactive gradient
  const mouseX = useMotionValue(0);
  const mouseY = useMotionValue(0);
  
  // Smooth out the mouse values
  const smoothX = useSpring(mouseX, { damping: 50, stiffness: 400 });
  const smoothY = useSpring(mouseY, { damping: 50, stiffness: 400 });

  // Top-level transforms (React Hooks cannot be called conditionally inside JSX)
  const glow1X = useTransform(smoothX, [-1, 1], ["-60%", "-40%"]);
  const glow1Y = useTransform(smoothY, [-1, 1], ["-60%", "-40%"]);
  const glow2X = useTransform(smoothX, [-1, 1], ["-40%", "-60%"]);
  const glow2Y = useTransform(smoothY, [-1, 1], ["-40%", "-60%"]);
  
  const logoRotateX = useTransform(smoothY, [-1, 1], [15, -15]);
  const logoRotateY = useTransform(smoothX, [-1, 1], [-15, 15]);

  useEffect(() => {
    const handleMouseMove = (e) => {
      // Normalize to -1 to 1 based on window size
      mouseX.set((e.clientX / window.innerWidth) * 2 - 1);
      mouseY.set((e.clientY / window.innerHeight) * 2 - 1);
    };
    window.addEventListener("mousemove", handleMouseMove);
    return () => window.removeEventListener("mousemove", handleMouseMove);
  }, [mouseX, mouseY]);

  // Handle wheel scrolling to transition from step 0 to 1
  useEffect(() => {
    const handleWheel = (e) => {
      if (step === 0 && e.deltaY > 50) {
        setStep(1);
      } else if (step === 1 && e.deltaY < -50) {
        // Optional: scroll back up to welcome
        setStep(0);
      }
    };
    window.addEventListener("wheel", handleWheel);
    return () => window.removeEventListener("wheel", handleWheel);
  }, [step]);

  return (
    <div style={{
      position: "fixed", inset: 0,
      background: "#020617", // Very dark base
      display: "flex", alignItems: "center", justifyContent: "center",
      fontFamily: "'Inter', 'Segoe UI', system-ui, sans-serif",
      color: "#e2e8f0",
      zIndex: 9999,
      overflow: "hidden"
    }}>
      
      {/* ── Reactive Toodle / Background Glow Layer ── */}
      <div style={{ position: "absolute", inset: 0, overflow: "hidden", pointerEvents: "none" }}>
        {/* Glow 1: Cyan/Teal tracking mouse */}
        <motion.div style={{
          position: "absolute", top: "50%", left: "50%", 
          width: "80vw", height: "80vw",
          background: "radial-gradient(circle, rgba(6,182,212,0.15) 0%, transparent 60%)",
          x: glow1X,
          y: glow1Y,
          filter: "blur(60px)",
          opacity: step === 0 ? 1 : 0.3,
          transition: "opacity 1s ease"
        }} />
        
        {/* Glow 2: Magenta/Pink contrasting motion */}
        <motion.div style={{
          position: "absolute", top: "50%", left: "50%", 
          width: "70vw", height: "70vw",
          background: "radial-gradient(circle, rgba(217,70,239,0.12) 0%, transparent 60%)",
          x: glow2X,
          y: glow2Y,
          filter: "blur(80px)",
          opacity: step === 0 ? 1 : 0.4,
          transition: "opacity 1s ease"
        }} />

        {/* Glow 3: Deep Blue base */}
        <motion.div style={{
          position: "absolute", top: "50%", left: "50%", 
          width: "100vw", height: "100vw",
          background: "radial-gradient(circle, rgba(59,130,246,0.08) 0%, transparent 70%)",
          x: "-50%", y: "-50%",
          filter: "blur(100px)",
        }} />
      </div>

      <AnimatePresence mode="wait">
        {step === 0 && (
          <motion.div
            key="step0"
            initial={{ opacity: 0, filter: "blur(0px)" }}
            animate={{ opacity: 1, filter: "blur(0px)" }}
            exit={{ opacity: 0, y: -60, filter: "blur(15px)" }}
            transition={{ duration: 0.8, ease: [0.16, 1, 0.3, 1] }}
            style={{ 
              position: "relative", zIndex: 1, width: "100%", height: "100%", 
              display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "space-between",
              padding: "8vh 24px"
            }}
          >
            {/* Top / Logo Area */}
            <div style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", width: "100%" }}>
              <motion.div
                initial={{ scale: 0.8, opacity: 0 }}
                animate={{ scale: 1, opacity: 1 }}
                transition={{ duration: 1.2, ease: "easeOut", delay: 0.2 }}
                style={{
                  position: "relative",
                  marginBottom: 40
                }}
              >
                {/* Reactive logo container */}
                <motion.div style={{
                  rotateX: logoRotateX,
                  rotateY: logoRotateY,
                  perspective: 1000
                }}>
                  <motion.div
                    animate={{ y: [0, -15, 0] }}
                    transition={{ duration: 6, ease: "easeInOut", repeat: Infinity }}
                  >
                    <img 
                      src="/logo.png" 
                      alt="AlphaSurface Logo" 
                      style={{ 
                        width: 240, height: "auto", 
                        filter: "drop-shadow(0 20px 40px rgba(6,182,212,0.4)) drop-shadow(0 0 80px rgba(217,70,239,0.3))" 
                      }} 
                    />
                  </motion.div>
                </motion.div>
              </motion.div>

              <motion.div 
                initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.6, duration: 0.8 }}
                style={{ textAlign: "center", maxWidth: 600 }}
              >
                <h1 style={{ 
                  fontSize: 56, fontWeight: 800, letterSpacing: "-0.04em", margin: "0 0 16px 0",
                  background: "linear-gradient(135deg, #fff 0%, #cbd5e1 100%)",
                  WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent"
                }}>
                  AlphaSurface
                </h1>
                <p style={{ fontSize: 20, color: "#94a3b8", fontWeight: 400, margin: 0, lineHeight: 1.5 }}>
                  AI that thinks alongside you — not for you. <br />
                  A spatial workspace for unbounded exploration.
                </p>
              </motion.div>
            </div>

            {/* Bottom / Social Cards */}
            <motion.div 
              initial={{ opacity: 0, y: 40 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.8, duration: 0.8 }}
              style={{ width: "100%", maxWidth: 1000, display: "flex", flexDirection: "column", gap: 32 }}
            >
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: 24 }}>
                <SocialCard 
                  icon={<Github size={24} color="#f8fafc" />}
                  title="GitHub"
                  handle="adr1en360/AlphaSurface"
                  href="https://github.com/adr1en360/AlphaSurface"
                  color="rgba(255,255,255,0.05)"
                  hoverColor="rgba(255,255,255,0.1)"
                  delay={1.0}
                />
                <SocialCard 
                  icon={<Twitter size={24} color="#38bdf8" />}
                  title="X (Twitter)"
                  handle="@artiflux360"
                  href="https://x.com/artiflux360"
                  color="rgba(56,189,248,0.05)"
                  hoverColor="rgba(56,189,248,0.15)"
                  delay={1.1}
                />
                <SocialCard 
                  icon={<Linkedin size={24} color="#3b82f6" />}
                  title="LinkedIn"
                  handle="adrienoke"
                  href="https://www.linkedin.com/in/adrienoke/"
                  color="rgba(59,130,246,0.05)"
                  hoverColor="rgba(59,130,246,0.15)"
                  delay={1.2}
                />
              </div>

              {/* Scroll prompt */}
              <motion.div 
                animate={{ y: [0, 8, 0], opacity: [0.5, 1, 0.5] }}
                transition={{ duration: 2, ease: "easeInOut", repeat: Infinity }}
                onClick={() => setStep(1)}
                style={{ 
                  display: "flex", flexDirection: "column", alignItems: "center", gap: 8, 
                  color: "#64748b", fontSize: 13, fontWeight: 500, letterSpacing: "0.1em", textTransform: "uppercase",
                  cursor: "pointer", paddingBottom: 16
                }}
              >
                <span>Scroll or click to begin</span>
                <ChevronDown size={20} />
              </motion.div>
            </motion.div>
          </motion.div>
        )}

        {step === 1 && (
          <motion.div
            key="step1"
            initial={{ opacity: 0, y: 60, scale: 0.95, filter: "blur(0px)" }}
            animate={{ opacity: 1, y: 0, scale: 1, filter: "blur(0px)" }}
            exit={{ opacity: 0, y: -40, filter: "blur(10px)", scale: 0.95 }}
            transition={{ duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
            style={{ position: "relative", zIndex: 1, width: "100%", maxWidth: 800, padding: "0 24px" }}
          >
            <div style={{ textAlign: "center", marginBottom: 64 }}>
              <motion.div 
                initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1, duration: 0.6 }}
                style={{ fontSize: 40, fontWeight: 700, letterSpacing: "-0.03em", marginBottom: 16 }}
              >
                How are you working today?
              </motion.div>
              <motion.div 
                initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.3, duration: 0.6 }}
                style={{ fontSize: 18, color: "#94a3b8", fontWeight: 400 }}
              >
                AlphaSurface adapts its behaviour based on your current focus.
              </motion.div>
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 24 }}>
              <ModeCard 
                icon={<Brain size={36} color="#d946ef" />}
                title="Think Mode"
                description="I'm exploring an idea alone. Let the AI inject provocations and questions."
                delay={0.2}
                onClick={() => handleModeSelect("think")}
                glowColor="rgba(217,70,239,0.3)"
              />
              <ModeCard 
                icon={<Presentation size={36} color="#06b6d4" />}
                title="Present Mode"
                description="I'm presenting to others. Keep the AI supportive, silent, and contextual."
                delay={0.3}
                onClick={() => handleModeSelect("explain")}
                glowColor="rgba(6,182,212,0.3)"
              />
            </div>
            
            <div style={{ textAlign: "center", marginTop: 40 }}>
              <button
                onClick={() => setStep(0)}
                style={{
                  background: "transparent", border: "none", color: "#475569", fontSize: 14,
                  cursor: "pointer", padding: "8px 16px", transition: "color 0.2s"
                }}
                onMouseEnter={(e) => e.target.style.color = "#94a3b8"}
                onMouseLeave={(e) => e.target.style.color = "#475569"}
              >
                ← Back to Welcome
              </button>
            </div>
          </motion.div>
        )}

        {step === 2 && (
          <motion.div
            key="step2"
            initial={{ opacity: 0, y: 40, filter: "blur(10px)" }}
            animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
            exit={{ opacity: 0, y: -40 }}
            transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
            style={{ position: "relative", zIndex: 1, width: "100%", maxWidth: 640, padding: "0 24px", display: "flex", flexDirection: "column", gap: 24 }}
          >
             <div style={{ textAlign: "center", marginBottom: 24 }}>
              <div style={{ fontSize: 32, fontWeight: 700, letterSpacing: "-0.03em", marginBottom: 12 }}>
                {mode === "explain" ? "Session setup" : "What are you working on?"}
              </div>
              <div style={{ fontSize: 16, color: "#94a3b8" }}>
                Optional. Helps contextualise the canvas immediately. 
              </div>
            </div>

            <div style={{ position: "relative" }}>
               <input
                autoFocus
                value={goal}
                onChange={(e) => setGoal(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') handleFinish();
                }}
                placeholder={mode === "explain" ? "e.g. Presenting quarterly metrics..." : "e.g. Planning a new app architecture..."}
                style={{
                  width: "100%",
                  background: "rgba(15, 23, 42, 0.6)",
                  border: "1px solid rgba(148, 163, 184, 0.2)",
                  borderRadius: 24,
                  padding: "24px 32px",
                  fontSize: 20,
                  color: "#f8fafc",
                  outline: "none",
                  boxShadow: "inset 0 2px 4px rgba(0,0,0,0.2), 0 20px 40px rgba(0,0,0,0.4)",
                  transition: "border-color 0.3s, box-shadow 0.3s, background 0.3s",
                  backdropFilter: "blur(20px)"
                }}
                onFocus={(e) => {
                  e.target.style.borderColor = "rgba(6, 182, 212, 0.5)";
                  e.target.style.background = "rgba(15, 23, 42, 0.8)";
                  e.target.style.boxShadow = "inset 0 2px 4px rgba(0,0,0,0.2), 0 0 0 4px rgba(6, 182, 212, 0.15), 0 20px 40px rgba(0,0,0,0.4)";
                }}
                onBlur={(e) => {
                  e.target.style.borderColor = "rgba(148, 163, 184, 0.2)";
                  e.target.style.background = "rgba(15, 23, 42, 0.6)";
                  e.target.style.boxShadow = "inset 0 2px 4px rgba(0,0,0,0.2), 0 20px 40px rgba(0,0,0,0.4)";
                }}
              />
              
              <motion.button
                initial={{ opacity: 0, scale: 0.8 }}
                animate={{ opacity: goal.length > 0 ? 1 : 0, scale: goal.length > 0 ? 1 : 0.8 }}
                onClick={handleFinish}
                style={{
                  position: "absolute",
                  right: 16, top: 16, bottom: 16,
                  background: "linear-gradient(135deg, #06b6d4, #3b82f6)",
                  border: "none", borderRadius: 16,
                  width: 56,
                  display: "flex", alignItems: "center", justifyContent: "center",
                  cursor: goal.length > 0 ? "pointer" : "default",
                  pointerEvents: goal.length > 0 ? "auto" : "none",
                  boxShadow: "0 8px 20px rgba(6,182,212,0.3)",
                }}
                whileHover={{ scale: 1.05 }}
                whileTap={{ scale: 0.95 }}
              >
                <ArrowRight color="white" size={24} />
              </motion.button>
            </div>

            {mode === "explain" && (
              <div style={{ display: "flex", flexDirection: "column", gap: 24, marginTop: 8 }}>
                <div>
                  <div style={{ fontSize: 13, fontWeight: 600, color: "#cbd5e1", marginBottom: 12, marginLeft: 8, textTransform: "uppercase", letterSpacing: "0.05em" }}>
                    Who are you presenting to?
                  </div>
                  <div style={{ display: "flex", gap: 12, flexWrap: "wrap", justifyContent: "center" }}>
                    {["Students", "Colleagues", "General Audience"].map((a) => (
                      <button
                        key={a}
                        onClick={() => setAudience(a)}
                        style={{
                          background: audience === a ? "rgba(6, 182, 212, 0.2)" : "rgba(15, 23, 42, 0.6)",
                          border: `1px solid ${audience === a ? "rgba(6, 182, 212, 0.5)" : "rgba(255, 255, 255, 0.05)"}`,
                          color: audience === a ? "#fff" : "#94a3b8",
                          padding: "12px 24px", borderRadius: 24, boxSizing: "border-box", fontSize: 14, cursor: "pointer", transition: "all 0.2s"
                        }}
                      >
                        {a}
                      </button>
                    ))}
                  </div>
                </div>

                <div>
                  <div style={{ fontSize: 13, fontWeight: 600, color: "#cbd5e1", marginBottom: 12, marginLeft: 8, textTransform: "uppercase", letterSpacing: "0.05em" }}>
                    Pre-load Reference Material
                  </div>
                  <div style={{ display: "flex", justifyContent: "center" }}>
                    <button
                      onClick={handleUploadClick}
                      style={{
                        background: uploadedFileName ? "rgba(52, 211, 153, 0.15)" : "rgba(15, 23, 42, 0.6)",
                        border: uploadedFileName ? "1px solid rgba(52, 211, 153, 0.4)" : "1px dashed rgba(255, 255, 255, 0.2)",
                        color: uploadedFileName ? "#34d399" : "#94a3b8",
                        padding: "16px 32px", borderRadius: 24, width: "100%", fontSize: 15, cursor: "pointer", transition: "all 0.2s"
                      }}
                      onMouseEnter={(e) => {
                        if (!uploadedFileName) e.currentTarget.style.borderColor = "rgba(255, 255, 255, 0.4)";
                      }}
                      onMouseLeave={(e) => {
                        if (!uploadedFileName) e.currentTarget.style.borderColor = "rgba(255, 255, 255, 0.2)";
                      }}
                    >
                      {uploadedFileName ? `📄 Uploaded: ${uploadedFileName}` : "Click to upload PDF / Docx notes"}
                    </button>
                  </div>
                </div>
              </div>
            )}

            <div style={{ textAlign: "center", marginTop: 16, display: "flex", justifyContent: "center", gap: 32 }}>
              <button
                onClick={() => setStep(1)}
                style={{
                  background: "transparent", border: "none", color: "#475569", fontSize: 14,
                  cursor: "pointer", padding: "8px 16px", transition: "color 0.2s"
                }}
                onMouseEnter={(e) => e.target.style.color = "#94a3b8"}
                onMouseLeave={(e) => e.target.style.color = "#475569"}
              >
                ← Back
              </button>
              <button
                onClick={handleFinish}
                style={{
                  background: "transparent", border: "none", color: "#64748b", fontSize: 14,
                  cursor: "pointer", padding: "8px 16px", transition: "color 0.2s",
                  fontWeight: 500
                }}
                onMouseEnter={(e) => e.target.style.color = "#f8fafc"}
                onMouseLeave={(e) => e.target.style.color = "#64748b"}
              >
                {mode === "explain" ? "Start Presentation" : "Skip & Start Canvas"}
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
      <style>{`
        input::placeholder { color: #475569; }
        ::-webkit-scrollbar { width: 0; }
      `}</style>
    </div>
  );
}

function ModeCard({ title, description, icon, delay, onClick, glowColor }) {
  return (
    <motion.button
      onClick={onClick}
      initial={{ opacity: 0, y: 30 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay, duration: 0.7, ease: [0.16, 1, 0.3, 1] }}
      whileHover={{ y: -8, scale: 1.02 }}
      whileTap={{ scale: 0.98 }}
      style={{
        background: "rgba(15, 23, 42, 0.4)",
        border: "1px solid rgba(255, 255, 255, 0.05)",
        borderRadius: 32,
        padding: "40px 32px",
        textAlign: "left",
        cursor: "pointer",
        backdropFilter: "blur(40px)",
        boxShadow: "0 20px 40px rgba(0,0,0,0.3), inset 0 1px 0 rgba(255,255,255,0.05)",
        display: "flex", flexDirection: "column", gap: 24,
        position: "relative",
        overflow: "hidden",
        transition: "border-color 0.4s ease, background 0.4s ease, box-shadow 0.4s ease"
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.borderColor = glowColor.replace("0.3", "0.5");
        e.currentTarget.style.background = "rgba(15, 23, 42, 0.7)";
        e.currentTarget.style.boxShadow = `0 20px 40px rgba(0,0,0,0.4), 0 0 60px ${glowColor}, inset 0 1px 0 rgba(255,255,255,0.1)`;
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.borderColor = "rgba(255, 255, 255, 0.05)";
        e.currentTarget.style.background = "rgba(15, 23, 42, 0.4)";
        e.currentTarget.style.boxShadow = "0 20px 40px rgba(0,0,0,0.3), inset 0 1px 0 rgba(255,255,255,0.05)";
      }}
    >
      <div style={{ 
        width: 72, height: 72, borderRadius: 20, 
        background: "rgba(15, 23, 42, 0.8)", border: "1px solid rgba(255,255,255,0.05)",
        display: "flex", alignItems: "center", justifyContent: "center",
        boxShadow: "inset 0 1px 0 rgba(255,255,255,0.1), 0 8px 16px rgba(0,0,0,0.4)"
      }}>
        {icon}
      </div>
      <div>
        <div style={{ fontSize: 26, fontWeight: 700, color: "#f8fafc", marginBottom: 12, letterSpacing: "-0.02em" }}>
          {title}
        </div>
        <div style={{ fontSize: 16, color: "#94a3b8", lineHeight: 1.6 }}>
          {description}
        </div>
      </div>
    </motion.button>
  );
}

function SocialCard({ icon, title, handle, href, color, hoverColor, delay }) {
  return (
    <motion.a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      initial={{ opacity: 0, y: 20, scale: 0.95 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ delay, duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
      whileHover={{ y: -4, scale: 1.03 }}
      whileTap={{ scale: 0.97 }}
      style={{
        display: "flex", alignItems: "center", gap: 16,
        background: color,
        border: "1px solid rgba(255,255,255,0.08)",
        borderRadius: 20,
        padding: "20px 24px",
        textDecoration: "none",
        color: "#e2e8f0",
        backdropFilter: "blur(20px)",
        boxShadow: "0 10px 30px rgba(0,0,0,0.2)",
        transition: "background 0.3s ease, border-color 0.3s ease"
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.background = hoverColor;
        e.currentTarget.style.borderColor = "rgba(255,255,255,0.2)";
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.background = color;
        e.currentTarget.style.borderColor = "rgba(255,255,255,0.08)";
      }}
    >
      <div style={{ 
        width: 48, height: 48, borderRadius: 12, 
        background: "rgba(0,0,0,0.2)",
        display: "flex", alignItems: "center", justifyContent: "center"
      }}>
        {icon}
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
        <span style={{ fontSize: 13, fontWeight: 600, color: "#94a3b8", textTransform: "uppercase", letterSpacing: "0.05em" }}>{title}</span>
        <span style={{ fontSize: 16, fontWeight: 600, letterSpacing: "-0.01em" }}>{handle}</span>
      </div>
    </motion.a>
  );
}

export default OnboardingFlow;
