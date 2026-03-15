// ── Audio playback singleton ──────────────────────────────────────────────────
// Extracted from App.jsx — handles queued PCM audio playback from Gemini

const _playback = {
  _ctx: null,
  nextTime: 0,
  enabled: false,
  sources: [],
}

export function activatePlaybackContext() {
  if (!_playback._ctx) {
    _playback._ctx = new AudioContext({ sampleRate: 24000 })
  }
  if (_playback._ctx.state === "suspended") {
    void _playback._ctx.resume().catch(() => {})
  }
  return _playback._ctx
}

export function getPlaybackContext() {
  return _playback._ctx
}

export function flushAudioPlayback() {
  for (const s of _playback.sources) {
    try { s.stop() } catch { /* already ended */ }
  }
  _playback.sources = []
  _playback.nextTime = 0
}

export function setPlaybackEnabled(enabled) {
  _playback.enabled = enabled
}

export function isPlaybackEnabled() {
  return _playback.enabled
}

/**
 * Play a base64-encoded PCM chunk from Gemini.
 * Chunks are queued so they play seamlessly one after another.
 */
export function playAudioChunk(base64Data) {
  if (!base64Data || !_playback.enabled) return
  const playbackCtx = getPlaybackContext() ?? activatePlaybackContext()
  if (!playbackCtx) return

  const raw = atob(base64Data)
  const buf = new ArrayBuffer(raw.length)
  const bytes = new Uint8Array(buf)
  for (let i = 0; i < raw.length; i++) bytes[i] = raw.charCodeAt(i)

  if (playbackCtx.state === "suspended") {
    void playbackCtx.resume().catch(() => {})
  }

  try {
    const audioBuffer = playbackCtx.createBuffer(1, buf.byteLength / 2, 24000)
    const channel = audioBuffer.getChannelData(0)
    const pcm = new Int16Array(buf)
    for (let i = 0; i < pcm.length; i++) channel[i] = pcm[i] / 32768

    const source = playbackCtx.createBufferSource()
    source.buffer = audioBuffer
    source.connect(playbackCtx.destination)

    const now = playbackCtx.currentTime
    if (_playback.nextTime < now) _playback.nextTime = now
    source.start(_playback.nextTime)
    _playback.nextTime += audioBuffer.duration
    _playback.sources.push(source)
    source.onended = () => {
      _playback.sources = _playback.sources.filter(s => s !== source)
    }
  } catch (err) {
    console.warn("[AlphaSurface] Audio playback skipped", err)
  }
}
