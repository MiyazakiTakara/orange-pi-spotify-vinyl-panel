let sourceState = null;
let displayState = null;
let pendingState = null;
let pendingSince = 0;
let latestFetchAt = Date.now();

const $ = (id) => document.getElementById(id);
const TRACK_SWITCH_GUARD_MS = 2500;
const FALLBACK_PENDING_DELAY_MS = 1800;

function parseNum(value) {
  if (value === null || value === undefined || value === '') return 0;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

function normalizeStatus(raw, title, trackId) {
  const value = String(raw || '').toLowerCase();
  if (['playing', 'paused', 'stopped', 'waiting', 'error'].includes(value)) return value;
  if ((value === 'unavailable' || value === 'unknown') && (title || trackId)) return 'playing';
  if (!title && !trackId) return 'waiting';
  return value || 'waiting';
}

function statusLabel(status) {
  return {
    playing: 'Gra teraz',
    paused: 'Pauza',
    stopped: 'Stop',
    waiting: 'Czekam na Spotify',
    error: 'Błąd'
  }[status] || status;
}

function formatTime(ms) {
  const safeMs = Math.max(0, parseNum(ms));
  const totalSec = Math.floor(safeMs / 1000);
  const min = Math.floor(totalSec / 60);
  const sec = totalSec % 60;
  return `${String(min).padStart(2, '0')}:${String(sec).padStart(2, '0')}`;
}

function computePosition(data, status) {
  const base = parseNum(data.position_ms);
  const duration = parseNum(data.duration_ms);
  if (duration <= 0) return { position: base, duration };

  let position = base;
  if (status === 'playing') {
    const updatedAt = Date.parse(data.updated_at || '');
    position += Number.isNaN(updatedAt) ? Date.now() - latestFetchAt : Date.now() - updatedAt;
  }

  return { position: Math.max(0, Math.min(duration, position)), duration };
}

function remainingMs(data) {
  const status = normalizeStatus(data.event, data.title, data.track_id);
  const { position, duration } = computePosition(data, status);
  if (duration <= 0) return 0;
  return Math.max(0, duration - position);
}

function shouldDelayTrackSwitch(nextState) {
  if (!displayState || !nextState) return false;
  if (!displayState.track_id || !nextState.track_id) return false;
  if (displayState.track_id === nextState.track_id) return false;

  const oldStatus = normalizeStatus(displayState.event, displayState.title, displayState.track_id);
  if (oldStatus !== 'playing' && oldStatus !== 'paused') return false;

  const oldDuration = parseNum(displayState.duration_ms);
  if (oldDuration <= 0) {
    return Date.now() - pendingSince < FALLBACK_PENDING_DELAY_MS;
  }

  return remainingMs(displayState) > TRACK_SWITCH_GUARD_MS;
}

function chooseDisplayState(nextState) {
  sourceState = nextState;

  if (!displayState) {
    displayState = nextState;
    pendingState = null;
    pendingSince = 0;
    return displayState;
  }

  if (displayState.track_id !== nextState.track_id && shouldDelayTrackSwitch(nextState)) {
    pendingState = nextState;
    if (!pendingSince) pendingSince = Date.now();
    return displayState;
  }

  displayState = nextState;
  pendingState = null;
  pendingSince = 0;
  return displayState;
}

function maybeCommitPending() {
  if (!pendingState || !displayState) return;

  const duration = parseNum(displayState.duration_ms);
  const elapsedPending = Date.now() - pendingSince;

  if (duration <= 0 && elapsedPending >= FALLBACK_PENDING_DELAY_MS) {
    displayState = pendingState;
    pendingState = null;
    pendingSince = 0;
    renderStatic(displayState);
    return;
  }

  if (remainingMs(displayState) <= TRACK_SWITCH_GUARD_MS) {
    displayState = pendingState;
    pendingState = null;
    pendingSince = 0;
    renderStatic(displayState);
  }
}

function setCover(src) {
  const holder = $('coverHolder');
  const current = holder.dataset.currentSrc || '';
  if (src && current !== src) {
    holder.innerHTML = `<img src="${src}" alt="Okładka" referrerpolicy="no-referrer">`;
    holder.dataset.currentSrc = src;
  } else if (!src && current !== '__empty__') {
    holder.innerHTML = '<div class="no-cover">♪</div>';
    holder.dataset.currentSrc = '__empty__';
  }
}

function clearOldManualRotation() {
  const record = document.querySelector('.record.spin');
  const cover = document.querySelector('.label-cover.spin');
  if (record) {
    record.style.animation = '';
    record.style.transform = '';
  }
  if (cover) {
    cover.style.animation = '';
    cover.style.transform = '';
  }
}

function renderStatic(data) {
  const title = data.title || 'Czekam na utwór...';
  const author = data.author || 'Spotify Connect';
  const trackId = data.track_id || '—';
  const status = normalizeStatus(data.event, data.title, data.track_id);
  const thumb = data.local_thumbnail_url || data.thumbnail_url || '';
  const error = data.oembed_error || data.error || '';

  $('title').textContent = title;
  $('artist').textContent = author;
  $('progressTitle').textContent = title;
  $('progressArtist').textContent = author;
  $('trackIdBox').textContent = trackId;
  $('spotifyBtn').href = data.spotify_url || '#';
  $('updatedAt').textContent = `Aktualizacja: ${data.updated_at || 'Brak danych'}`;
  $('miniStatus').textContent = statusLabel(status);
  $('shuffleValue').textContent = data.shuffle === '' || data.shuffle === undefined ? '—' : String(data.shuffle);
  $('repeatValue').textContent = data.repeat === '' || data.repeat === undefined ? '—' : String(data.repeat);

  const badge = $('statusBadge');
  badge.textContent = statusLabel(status);
  badge.className = `chip status ${status}`;
  $('vinylStage').className = `vinyl-stage ${status}`;
  setCover(thumb);
  clearOldManualRotation();

  const errorBox = $('errorBox');
  if (error) {
    errorBox.style.display = 'block';
    errorBox.textContent = error;
  } else {
    errorBox.style.display = 'none';
    errorBox.textContent = '';
  }
}

function renderDynamic(data) {
  const status = normalizeStatus(data.event, data.title, data.track_id);
  const { position, duration } = computePosition(data, status);
  const progress = duration > 0 ? Math.max(0, Math.min(1, position / duration)) : 0;

  document.documentElement.style.setProperty('--progress', `${(progress * 100).toFixed(2)}%`);
  $('timeBadge').textContent = `${formatTime(position)} / ${formatTime(duration)}`;
  $('progressTime').textContent = `${formatTime(position)} / ${formatTime(duration)}`;

  let armRotation = 32;
  if (status === 'playing' || status === 'paused') {
    armRotation = 32 - progress * 22;
  }
  document.documentElement.style.setProperty('--arm-rotation', `${armRotation.toFixed(2)}deg`);
}

async function loadState() {
  try {
    const response = await fetch(`/api/state?ts=${Date.now()}`, { cache: 'no-store' });
    const data = await response.json();
    latestFetchAt = Date.now();
    const chosen = chooseDisplayState(data);
    renderStatic(chosen);
    renderDynamic(chosen);
  } catch (error) {
    const errorBox = $('errorBox');
    errorBox.style.display = 'block';
    errorBox.textContent = `Nie udało się pobrać stanu panelu: ${error}`;
  }
}

function animationLoop() {
  maybeCommitPending();
  if (displayState) {
    renderDynamic(displayState);
  }
  window.requestAnimationFrame(animationLoop);
}

loadState();
window.requestAnimationFrame(animationLoop);
setInterval(loadState, 5000);
