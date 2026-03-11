# AlphaSurface

AI that thinks alongside you — not for you.

AlphaSurface is a real-time voice + vision canvas where an AI co-thinker watches what you draw, listens to what you say, and places provocations, connections, and supporting material directly on a shared infinite whiteboard. Built with [tldraw](https://tldraw.dev), Google Gemini's native audio model, and the [Agent Development Kit (ADK)](https://google.github.io/adk-docs/).

![React](https://img.shields.io/badge/React-19-blue)
![Gemini](https://img.shields.io/badge/Gemini-2.5_Flash-orange)
![License](https://img.shields.io/badge/License-MIT-green)

---

## Features

- **Live voice conversation** — speak naturally; the AI hears you and responds with short spoken cues (≤ 6 words) while acting on the canvas.
- **Continuous canvas vision** — periodic screenshots are sent to Gemini so the agent understands your spatial layout, freehand sketches, and existing shapes.
- **Two session modes**
  - **Think Mode** — blank canvas, solo thinking. The AI injects Sarkar-style provocations (violet sticky notes with open questions) to challenge assumptions.
  - **Explain Mode** — teaching / presenting. The AI surfaces definitions, embeds videos, and places bookmarks without interrupting.
- **Rich canvas tools** — text, sticky notes, geometric shapes, arrows, bound connectors, live embeds (YouTube, Figma, Maps), and bookmark cards — all driven by the AI or the user.
- **Barge-in / interruption** — start talking mid-response and playback is flushed instantly.
- **Web search** (optional) — let the AI look things up and drop bookmarks on the canvas.
- **Custom MCP servers** (advanced) — extend the AI's toolset by plugging in external MCP endpoints.

---

## Quickstart

### 1. Prerequisites

- Python ≥ 3.12
- Node.js ≥ 18
- [uv](https://docs.astral.sh/uv/) (recommended) or pip
- A [Gemini API key](https://aistudio.google.com/apikey)

### 2. Setup

```bash
git clone https://github.com/<your-username>/AlphaSurface.git
cd AlphaSurface

# Set up backend
cd backend
uv sync
echo "GEMINI_API_KEY=your-key-here" > .env
cd ..

# Set up frontend
cd frontend
npm install
cd ..
```

### 3. Run the App

Open **two terminals** from the project root:

**Terminal 1 — Backend**
```bash
cd backend
uv run uvicorn main:app --reload --port 8000
```

**Terminal 2 — Frontend**
```bash
cd frontend
npm run dev
```

Open [http://localhost:5173](http://localhost:5173), pick a mode, toggle voice on, and click **Launch**.

---

## Usage Examples

Once connected, try these interactions based on your chosen mode:

**In Think Mode (solo brainstorming)**
- Draw a simple architecture diagram and ask: *"What are the weak points here?"*
- Write down a product idea and say: *"Give me three reasons this will fail."*
- Drop a sticky note and say: *"Expand on this point."*

**In Explain Mode (presenting/teaching)**
- Draw a concept (e.g., a cell structure) and say: *"I'm going to explain mitochondria."* (The AI listens and might quietly drop a reference bookmark or definition.)
- Say: *"Can you place a YouTube video about photosynthesis?"* (The AI finds and embeds a relevant video on the canvas.)

---

## Configuration

| Environment variable | Default | Description |
|---|---|---|
| `GEMINI_API_KEY` | — | Required. Your Google Gemini API key. |
| `ALPHASURFACE_MODE` | `think` | `think` or `explain`. |
| `ALPHASURFACE_WEB_SEARCH` | `false` | Enable AI web search. |

These can also be set from the launch screen in the browser.

---

## Architecture

```text
Browser (React + tldraw)
  ↕  WebSocket (audio PCM + canvas snapshots + shape commands)
FastAPI  ─── main.py   (WS hub, broadcast, CORS)
  │
  └── agent.py  (ADK LiveRequestQueue ↔ Gemini bidi stream)
        │
        └── tools.py  (canvas action queue → broadcast → browser)
```

## Project Structure

```text
backend/
  main.py          # FastAPI app, WebSocket hub, broadcast
  agent.py         # ADK agent, Gemini bidi streaming, system prompts
  tools.py         # Canvas tool definitions (15 tools)
  pyproject.toml   # Python dependencies

frontend/
  src/App.jsx      # tldraw canvas, WS client, launch screen, audio
  src/main.jsx     # React entry point
  index.html       # HTML shell
  package.json     # JS dependencies
```

---

## Development

```bash
# Backend — auto-reload on save
cd backend
uv run uvicorn main:app --reload --port 8000

# Frontend — Vite HMR
cd frontend
npm run dev

# Lint frontend
npm run lint
```

### Health check

```bash
curl http://localhost:8000/health
```
Returns agent status, connected clients, and current mode.

---

## Contributing

1. Fork the repo and create a feature branch.
2. Keep changes focused — one feature or fix per PR.
3. Test both modes (Think + Explain) with voice enabled before submitting.
4. Open a pull request with a clear description.

---

## License

MIT
