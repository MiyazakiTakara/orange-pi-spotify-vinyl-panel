const ui = {
  stage: document.getElementById('recordRotor').closest('.platter-stage'),
  cover: document.getElementById('coverHolder'),
  title: document.getElementById('trackTitle'),
  playtime: document.getElementById('playtime'),
  tonearm: document.getElementById('tonearm'),
  trackInfo: document.getElementById('trackInfo')
};

const POLL_INTERVAL_MS = 5000;
const SSE_STALE_MS = 35000;
const VISUAL_INTERVAL_MS = 100;
const CLOCK_INTERVAL_MS = 1000;

let state = null;
let playbackAnchor = {
  positionMs: 0,
  durationMs: 0,
  status: 'waiting',
  receivedAt: performance.now()
};
let eventSource = null;
let pollingTimer = null;
let reconnectTimer = null;
let watchdogTimer = null;
let visualTimer = null;
let clockTimer = null;
let lastSseMessageAt = 0;
let lastRevision = -1;
let lastPlaybackKey = '';
let lastTrackId = '';
let lastCoverSrc = '';

function asNumber(value, fallback = 0) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function formatTime(ms) {
  const seconds = Math.max(0, Math.floor(asNumber(ms) / 1000));
  const minutes = Math.floor(seconds / 60);
  const rest = seconds % 60;
  return `${String(minutes).padStart(2, '0')}:${String(rest).padStart(2, '0')}`;
}

function normalize(payload) {
  const current = payload.current_track || {};
  const playback = payload.playback || {};

  return {
    revision: asNumber(payload.server_revision ?? payload.revision),
    updatedAt: payload.updated_at || '',
    track: {
      id: current.id || payload.track_id || '',
      name: current.name || payload.title || '',
      durationMs: asNumber(current.duration_ms || payload.duration_ms),
      coverUrl: current.cover_url || payload.thumbnail_url || '',
      coverLocalUrl: current.cover_local_url || payload.local_thumbnail_url || ''
    },
    pendingTrack: payload.pending_track || {},
    playback: {
      status: playback.status || payload.event || 'waiting',
      positionMs: asNumber(playback.position_ms ?? payload.position_ms),
      durationMs: asNumber(playback.duration_ms || current.duration_ms || payload.duration_ms),
      updatedAt: playback.updated_at || payload.playback_updated_at || ''
    }
  };
}

function playbackKey(next) {
  return [
    next.track.id,
    next.playback.status,
    next.playback.positionMs,
    next.playback.durationMs,
    next.playback.updatedAt
  ].join('|');
}

function applyPlaybackAnchor(next) {
  playbackAnchor = {
    positionMs: next.playback.positionMs,
    durationMs: next.playback.durationMs || next.track.durationMs,
    status: next.playback.status,
    receivedAt: performance.now()
  };
}

function currentPosition() {
  let position = playbackAnchor.positionMs;
  if (playbackAnchor.status === 'playing') {
    position += performance.now() - playbackAnchor.receivedAt;
  }
  return Math.max(0, Math.min(playbackAnchor.durationMs || position, position));
}

function setCover(track) {
  const src = track.coverLocalUrl || track.coverUrl || '';
  if (src === lastCoverSrc) return;
  lastCoverSrc = src;

  if (!src) {
    const placeholder = document.createElement('div');
    placeholder.className = 'cover-placeholder';
    placeholder.textContent = '♪';
    ui.cover.replaceChildren(placeholder);
    return;
  }

  const image = new Image();
  image.alt = '';
  image.decoding = 'async';
  image.referrerPolicy = 'no-referrer';
  image.addEventListener('load', () => {
    if (src === lastCoverSrc) ui.cover.replaceChildren(image);
  }, { once: true });
  image.addEventListener('error', () => {
    if (track.coverUrl && src !== track.coverUrl) {
      lastCoverSrc = '';
      setCover({ ...track, coverLocalUrl: '' });
    }
  }, { once: true });
  image.src = src;
}

function preloadPendingCover(next) {
  const pending = next.pendingTrack || {};
  const src = pending.cover_local_url || pending.cover_url || '';
  if (!src) return;
  const image = new Image();
  image.decoding = 'async';
  image.src = src;
}

function renderStatic(next) {
  const title = next.track.name || 'Czekam na utwór...';
  ui.title.textContent = title;
  document.title = next.track.name ? `${title} — Orange Pi Audio` : 'Orange Pi Audio';
  ui.stage.classList.toggle('playing', next.playback.status === 'playing');
  setCover(next.track);
}

function renderVisuals() {
  if (!state) return;

  const duration = playbackAnchor.durationMs;
  const position = currentPosition();
  const progress = duration > 0 ? Math.min(1, position / duration) : 0;

  let rotation;
  if (state.playback.status === 'playing' || state.playback.status === 'paused') {
    rotation = 14 + progress * 7.5;
  } else {
    rotation = 0;
  }

  ui.tonearm.setAttribute('transform', `rotate(${rotation.toFixed(3)} 278 42)`);
}

function renderClock() {
  const position = currentPosition();
  const duration = playbackAnchor.durationMs;
  ui.playtime.textContent = `${formatTime(position)} / ${formatTime(duration)}`;
}

function animateTrackChange() {
  ui.trackInfo.classList.remove('changing');
  void ui.trackInfo.offsetWidth;
  ui.trackInfo.classList.add('changing');
}

function applyState(payload, force = false) {
  const next = normalize(payload);
  if (!force && next.revision && next.revision <= lastRevision) return;

  const nextKey = playbackKey(next);
  if (!state || nextKey !== lastPlaybackKey) {
    applyPlaybackAnchor(next);
    lastPlaybackKey = nextKey;
  }

  state = next;
  if (next.revision) lastRevision = next.revision;

  if (next.track.id !== lastTrackId) {
    lastTrackId = next.track.id;
    animateTrackChange();
  }

  renderStatic(next);
  renderVisuals();
  renderClock();
  preloadPendingCover(next);
}

async function fetchState(force = false) {
  try {
    const response = await fetch('/api/state', { cache: 'no-store' });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    applyState(await response.json(), force);
  } catch (_) {
    // Keep rendering the last known state. Reconnect/polling will retry.
  }
}

function startPolling() {
  if (pollingTimer) return;
  fetchState(false);
  pollingTimer = window.setInterval(() => fetchState(false), POLL_INTERVAL_MS);
}

function stopPolling() {
  if (!pollingTimer) return;
  window.clearInterval(pollingTimer);
  pollingTimer = null;
}

function closeEvents() {
  if (!eventSource) return;
  eventSource.close();
  eventSource = null;
}

function scheduleReconnect() {
  if (reconnectTimer || document.hidden) return;
  reconnectTimer = window.setTimeout(() => {
    reconnectTimer = null;
    connectEvents();
  }, 3000);
}

function connectEvents() {
  if (!window.EventSource || document.hidden) {
    startPolling();
    return;
  }

  closeEvents();
  const source = new EventSource('/api/events');
  eventSource = source;

  source.addEventListener('open', () => {
    lastSseMessageAt = Date.now();
    stopPolling();
  });

  source.addEventListener('state', (event) => {
    lastSseMessageAt = Date.now();
    try {
      applyState(JSON.parse(event.data), false);
    } catch (_) {
      // Ignore malformed realtime payload and wait for the next one.
    }
  });

  source.addEventListener('ping', () => {
    lastSseMessageAt = Date.now();
  });

  source.addEventListener('error', () => {
    if (eventSource !== source) return;
    closeEvents();
    startPolling();
    scheduleReconnect();
  });
}

function handleVisibilityChange() {
  if (document.hidden) {
    closeEvents();
    stopPolling();
    return;
  }

  renderVisuals();
  renderClock();
  fetchState(false);
  connectEvents();
}

document.addEventListener('visibilitychange', handleVisibilityChange);
window.addEventListener('online', () => {
  fetchState(false);
  connectEvents();
});
window.addEventListener('offline', () => {
  closeEvents();
  startPolling();
});

visualTimer = window.setInterval(renderVisuals, VISUAL_INTERVAL_MS);
clockTimer = window.setInterval(renderClock, CLOCK_INTERVAL_MS);
watchdogTimer = window.setInterval(() => {
  if (eventSource?.readyState === EventSource.OPEN && Date.now() - lastSseMessageAt > SSE_STALE_MS) {
    closeEvents();
    startPolling();
    scheduleReconnect();
  }
}, 5000);

fetchState(true);
connectEvents();
