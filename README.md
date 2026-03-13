# AlphaSurface

AI that thinks alongside you, not for you.

AlphaSurface is a real-time voice and vision canvas where an AI co-thinker watches what you draw, listens to what you say, and places provocations, connections, and support material directly on a shared infinite whiteboard. It is built with [tldraw](https://tldraw.dev), Gemini Live capabilities, and the [Agent Development Kit (ADK)](https://google.github.io/adk-docs/).

![React](https://img.shields.io/badge/React-19-blue)
![Gemini](https://img.shields.io/badge/Gemini-2.5_Flash-orange)
![License](https://img.shields.io/badge/License-MIT-green)

---

## Why AlphaSurface

- Think with voice and visuals in one flow.
- Get AI support on-canvas instead of in a separate chat window.
- Switch between solo thinking and teaching workflows.
- Use a Live Agent architecture with multimodal input and output.

---

## Features

- Live voice conversation with interruption handling (barge-in).
- Continuous canvas vision from periodic screenshot capture.
- Two session modes:
  - Think Mode: challenge assumptions with targeted provocations.
  - Explain Mode: support teaching with references and media.
- Canvas-native actions: text, notes, arrows, geo shapes, embeds, bookmarks, and images.
- Optional web-assisted research and specialist sub-agents.
- Document upload support for contextual assistance.

---

## Installation

### Prerequisites

- Python 3.12+
- Node.js 18+
- [uv](https://docs.astral.sh/uv/) (recommended)
- A [Gemini API key](https://aistudio.google.com/apikey)

### Setup

```bash
git clone https://github.com/<your-username>/AlphaSurface.git
cd AlphaSurface

cd backend
uv sync
cd ..

cd frontend
npm install
cd ..
```

---

## Quickstart (Local)

### 1) Configure backend env

Create `backend/.env`:

```bash
GEMINI_API_KEY=your-key-here
ALPHASURFACE_MODE=think
ALPHASURFACE_WEB_SEARCH=false
```

Optional for YouTube features:

```bash
YOUTUBE_API_KEY=your-youtube-data-api-key
```

### 2) Run backend

```bash
cd backend
uv run uvicorn main:app --reload --port 8000
```

### 3) Run frontend

In a second terminal:

```bash
cd frontend
npm run dev
```

### 4) Launch

Open [http://localhost:5173](http://localhost:5173), choose mode/settings, and click Launch.

---

## Usage

### Think Mode

- Draw an architecture or idea map and ask for weak points.
- Ask for missing assumptions, hidden risks, or contradictions.
- Speak while drawing so the agent combines audio and canvas context.

### Explain Mode

- Set audience and goal in onboarding.
- Upload a source document from the menu.
- Ask the agent to place references or videos directly on the canvas.

### Canvas menu actions

- Save canvas
- Load canvas
- Export PDF
- Upload document

---

## Configuration

| Environment variable | Default | Description |
|---|---|---|
| `GEMINI_API_KEY` | - | Required for Gemini access. |
| `ALPHASURFACE_MODE` | `think` | `think` or `explain`. |
| `ALPHASURFACE_WEB_SEARCH` | `false` | Enables web-assisted behavior. |
| `YOUTUBE_API_KEY` | - | Required for YouTubeAgent lookups/embeds. |
| `MEMORY_BACKEND` | `sqlite` | `sqlite` or `firestore`. |
| `MEMORY_DB_PATH` | backend local path | SQLite file path override. |
| `GOOGLE_GENAI_USE_VERTEXAI` | `false` | Use Vertex AI path when `true`. |
| `GOOGLE_CLOUD_PROJECT` | - | Required if using Vertex AI. |

Many of these can also be set from onboarding for session behavior.

---

## Architecture

```text
Browser (React + tldraw)
  <-> WebSocket (audio chunks + canvas snapshots + actions)
FastAPI (main.py)
  -> AlphaSurfaceAgent (ADK LiveRequestQueue + Runner)
  -> tools dispatcher + sub-agents
  -> broadcast actions/events back to browser
```

A visual architecture diagram will be added after local testing.

---

## Deployment Status

This project is being validated locally first, then deployed to Cloud Run.

Planned final submission artifacts:

- Cloud Run deployment proof.
- Architecture diagram.
- Public demo video.

---

## Development

```bash
# Backend
cd backend
uv run uvicorn main:app --reload --port 8000

# Frontend
cd frontend
npm run dev

# Frontend lint
npm run lint

# Backend tests
cd ../backend
uv run pytest
```

Health check:

```bash
curl http://localhost:8000/health
```

---

## Contributing

1. Fork the repo and create a branch.
2. Keep each pull request focused on one feature or fix.
3. Test both Think and Explain modes before opening a pull request.
4. Include a clear summary and test notes.

---

## License

MIT
