const $ = (id) => document.getElementById(id);

const ui = {
  title: $('title'),
  artist: $('artist'),
  progressTitle: $('progressTitle'),
  progressArtist: $('progressArtist'),
  trackId: $('trackIdBox'),
  spotify: $('spotifyBtn'),
  updatedAt: $('updatedAt'),
  miniStatus: $('miniStatus'),
  client: $('clientValue'),
  shuffle: $('shuffleValue'),
  repeat: $('repeatValue'),
  statusBadge: $('statusBadge'),
  connectionBadge: $('connectionBadge'),
  vinylStage: $('vinylStage'),
  cover: $('coverHolder'),
  error: $('errorBox'),
  timeBadge: $('timeBadge'),
  progressTime: $('progressTime'),
  progressFill: $('progressFill'),
  progressGlow: $('progressGlow'),
  tonearm: $('tonearm')
};

const STATUS_LABELS = {
  playing: 'Gra teraz',
  paused: 'Pauza',
  stopped: 'Stop',
  waiting: 'Czekam na Spotify',
  error: 'Błąd'
};

const POLL_INTERVAL_MS = 5000;
const SSE_STALE_MS = 35000;
const CLOCK_INTERVAL_MS = 1000;

let state = null;
let playbackAnchor = {
  positionMs: 0,
  receivedAt: performance.now(),
  status: 'waiting',
  durationMs: 0
};
let eventSource = null;
let pollingTimer = null;
let watchdogTimer = null;
let clockTimer = null;
let reconnectTimer = null;
let visualFrameId = null;
let lastSseMessageAt = 0;
let lastRenderedRevision = -1;
let lastTrackId = '';
let lastCoverSrc = '';
let lastProgressScale = -1;
let lastArmRotation = Number.NaN;

function number(value, fallback = 0) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function statusLabel(status) {
  return STATUS_LABELS[status] || status || 'Czekam';
}

function formatTime(ms) {
  const seconds = Math.max(0, Math.floor(number(ms) / 1000));
  return `${String(Math.floor(seconds / 60)).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')}`;
}

function normalizedState(payload) {
  const current = payload.current_track || {};
  const playback = payload.playback || {};
  const controls = payload.controls || {};
  const session = payload.session || {};

  return {
    ...payload,
    current_track: {
      id: current.id || payload.track_id || '',
      spotify_url: current.spotify_url || payload.spotify_url || '',
      name: current.name || payload.title || '',
      artist_text: current.artist_text || payload.author || '',
      album: current.album || '',
      duration_ms: number(current.duration_ms || payload.duration_ms),
      cover_url: current.cover_url || payload.thumbnail_url || '',
      cover_local_url: current.cover_local_url || payload.local_thumbnail_url || ''
    },
    pending_track: payload.pending_track || {},
    playback: {
      status: playback.status || payload.event || 'waiting',
      position_ms: number(playback.position_ms ?? payload.position_ms),
      duration_ms: number(playback.duration_ms || current.duration_ms || payload.duration_ms),
      updated_at: playback.updated_at || payload.playback_updated_at || payload.updated_at || ''
    },
    controls: {
      volume: controls.volume ?? payload.volume ?? '',
      shuffle: controls.shuffle ?? payload.shuffle ?? '',
      repeat: controls.repeat ?? payload.repeat ?? '',
      repeat_track: controls.repeat_track ?? ''
    },
    session
  };
}

function setConnection(mode, text) {
  ui.connectionBadge.className = `chip connection ${mode}`;
  ui.connectionBadge.textContent = text;
}

function showError(message = '') {
  ui.error.textContent = message;
  ui.error.style.display = message ? 'block' : 'none';
}

function displayValue(value) {
  return value === '' || value === null || value === undefined ? '—' : String(value);
}

function setCover(track) {
  const src = track.cover_local_url || track.cover_url || '';
  if (src === lastCoverSrc) return;
  lastCoverSrc = src;

  if (!src) {
    ui.cover.replaceChildren(Object.assign(document.createElement('div'), {
      className: 'no-cover',
      textContent: '♪'
    }));
    return;
  }

  const image = new Image();
  image.alt = 'Okładka';
  image.decoding = 'async';
  image.referrerPolicy = 'no-referrer';
  image.addEventListener('load', () => {
    if (src !== lastCoverSrc) return;
    ui.cover.replaceChildren(image);
  }, { once: true });
  image.addEventListener('error', () => {
    if (track.cover_url && src !== track.cover_url) {
      lastCoverSrc = '';
      setCover({ ...track, cover_local_url: '' });
    }
  }, { once: true });
  image.src = src;
}

function preloadPendingCover(payload) {
  const pending = payload.pending_track || {};
  const src = pending.cover_local_url || pending.cover_url;
  if (src) {
    const image = new Image();
    image.decoding = 'async';
    image.src = src;
  }
}

function applyPlaybackAnchor(payload) {
  playbackAnchor = {
    positionMs: number(payload.playback.position_ms),
    durationMs: number(payload.playback.duration_ms || payload.current_track.duration_ms),
    status: payload.playback.status,
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

function renderStatic(payload) {
  const track = payload.current_track;
  const playback = payload.playback;
  const status = playback.status;
  const title = track.name || 'Czekam na utwór...';
  const artist = track.artist_text || 'Spotify Connect';
  const spotifyUrl = track.spotify_url || (track.id ? `https://open.spotify.com/track/${track.id}` : '');

  document.title = track.name ? `${track.name} — ${artist}` : 'Orange Pi Audio';
  ui.title.textContent = title;
  ui.artist.textContent = artist;
  ui.progressTitle.textContent = title;
  ui.progressArtist.textContent = artist;
  ui.trackId.textContent = track.id || '—';
  ui.updatedAt.textContent = `Aktualizacja: ${payload.updated_at || 'Brak danych'}`;
  ui.miniStatus.textContent = statusLabel(status);
  ui.client.textContent = payload.session.client_name || payload.session.user_name || '—';
  ui.shuffle.textContent = displayValue(payload.controls.shuffle);
  ui.repeat.textContent = displayValue(payload.controls.repeat_track || payload.controls.repeat);

  ui.statusBadge.textContent = statusLabel(status);
  ui.statusBadge.className = `chip status ${status}`;
  ui.vinylStage.className = `vinyl-stage ${status}`;

  ui.spotify.href = spotifyUrl || '#';
  ui.spotify.classList.toggle('disabled', !spotifyUrl);
  ui.spotify.setAttribute('aria-disabled', spotifyUrl ? 'false' : 'true');

  setCover(track);
  showError(payload.last_error || '');
}

function renderVisuals() {
  if (!state) return;

  const duration = playbackAnchor.durationMs;
  const position = currentPosition();
  const progress = duration > 0 ? Math.min(1, position / duration) : 0;
  const armRotation = state.playback.status === 'playing' || state.playback.status === 'paused'
    ? 12 + progress * 24
    : 32;

  if (Math.abs(progress - lastProgressScale) > 0.00001) {
    const scale = `scaleX(${progress.toFixed(6)})`;
    ui.progressFill.style.transform = scale;
    ui.progressGlow.style.transform = scale;
    lastProgressScale = progress;
  }

  if (!Number.isFinite(lastArmRotation) || Math.abs(armRotation - lastArmRotation) > 0.001) {
    ui.tonearm.style.transform = `rotate(${armRotation.toFixed(3)}deg)`;
    lastArmRotation = armRotation;
  }
}

function visualLoop() {
  renderVisuals();
  visualFrameId = window.requestAnimationFrame(visualLoop);
}

function startVisualLoop() {
  if (visualFrameId !== null) return;
  visualFrameId = window.requestAnimationFrame(visualLoop);
}

function stopVisualLoop() {
  if (visualFrameId === null) return;
  window.cancelAnimationFrame(visualFrameId);
  visualFrameId = null;
}

function renderClock() {
  const position = currentPosition();
  const duration = playbackAnchor.durationMs;
  const value = `${formatTime(position)} / ${formatTime(duration)}`;
  ui.timeBadge.textContent = value;
  ui.progressTime.textContent = value;
}

function applyState(payload, force = false) {
  const next = normalizedState(payload);
  const revision = number(next.server_revision ?? next.revision, 0);
  if (!force && revision && revision <= lastRenderedRevision) return;

  state = next;
  if (revision) lastRenderedRevision = revision;
  applyPlaybackAnchor(next);
  renderStatic(next);
  renderVisuals();
  renderClock();
  preloadPendingCover(next);

  if (next.current_track.id !== lastTrackId) {
    lastTrackId = next.current_track.id;
    document.body.classList.add('track-changing');
    window.setTimeout(() => document.body.classList.remove('track-changing'), 350);
  }
}

async function fetchState(force = false) {
  try {
    const response = await fetch('/api/state', { cache: 'no-store' });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    applyState(await response.json(), force);
    if (!eventSource || eventSource.readyState !== EventSource.OPEN) {
      setConnection('polling', 'Polling');
    }
  } catch (error) {
    setConnection('offline', 'Rozłączono');
    showError(`Nie udało się pobrać stanu: ${error}`);
  }
}

function startPolling() {
  if (pollingTimer) return;
  fetchState(true);
  pollingTimer = window.setInterval(() => fetchState(false), POLL_INTERVAL_MS);
}

function stopPolling() {
  if (!pollingTimer) return;
  window.clearInterval(pollingTimer);
  pollingTimer = null;
}

function closeEvents() {
  if (eventSource) {
    eventSource.close();
    eventSource = null;
  }
}

function scheduleReconnect() {
  if (reconnectTimer) return;
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
  setConnection('connecting', 'Łączenie...');
  const source = new EventSource('/api/events');
  eventSource = source;

  source.addEventListener('open', () => {
    lastSseMessageAt = Date.now();
    setConnection('live', 'Live');
    stopPolling();
  });

  source.addEventListener('state', (event) => {
    lastSseMessageAt = Date.now();
    setConnection('live', 'Live');
    try {
      applyState(JSON.parse(event.data), false);
    } catch (error) {
      showError(`Nieprawidłowy event realtime: ${error}`);
    }
  });

  source.addEventListener('ping', () => {
    lastSseMessageAt = Date.now();
    setConnection('live', 'Live');
  });

  source.addEventListener('error', () => {
    if (eventSource !== source) return;
    setConnection('polling', 'Polling');
    closeEvents();
    startPolling();
    scheduleReconnect();
  });
}

function startTimers() {
  startVisualLoop();
  clockTimer = window.setInterval(renderClock, CLOCK_INTERVAL_MS);
  watchdogTimer = window.setInterval(() => {
    if (eventSource?.readyState === EventSource.OPEN && Date.now() - lastSseMessageAt > SSE_STALE_MS) {
      closeEvents();
      startPolling();
      scheduleReconnect();
    }
  }, 5000);
}

function handleVisibilityChange() {
  if (document.hidden) {
    closeEvents();
    stopPolling();
    stopVisualLoop();
    return;
  }
  startVisualLoop();
  fetchState(true);
  connectEvents();
}

ui.spotify.addEventListener('click', (event) => {
  if (ui.spotify.getAttribute('aria-disabled') === 'true') event.preventDefault();
});

document.addEventListener('visibilitychange', handleVisibilityChange);
window.addEventListener('online', () => {
  fetchState(true);
  connectEvents();
});
window.addEventListener('offline', () => {
  closeEvents();
  setConnection('offline', 'Brak sieci');
});

fetchState(true);
connectEvents();
startTimers();
