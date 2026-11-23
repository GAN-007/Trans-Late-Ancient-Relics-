// Live avatar chat: an OpenAvatarChat-style session in the browser.
// Pipeline per turn (as in OAC): mic -> speech recognition (browser ASR + VAD)
// -> SendHumanText -> server streams EchoAvatarText + AvatarSpeech sentences
// -> speech synthesis (TTS) -> ARKit blendshape motion drives the SVG face.
import {$, esc, state as appState, toast} from './core.js';
import {createRecognizer, speechRecognitionSupported} from './speech.js';

const HEARTBEAT_MS = 10000;
const REDUCED_MOTION = window.matchMedia('(prefers-reduced-motion: reduce)');
const SUGGESTIONS = {
  english: ['How do you say “the king made a great house” in Sumerian?', 'What does lugal mean?', 'Translate water into every language', 'Which languages do you know?'],
  swahili: ['Tafsiri “mfalme alipenda mama” kwa Kilatini', 'Maana ya lugal ni nini?', 'Tafsiri maji kwa lugha zote', 'Unajua lugha gani?'],
};
const STATE_LABELS = {offline: 'Offline', connecting: 'Connecting…', idle: 'Ready', listening: 'Listening…', thinking: 'Thinking…', speaking: 'Speaking'};
const STATUS_LABELS = {attested: 'attested', composed: 'composed', reconstructed: 'reconstructed', reconstructed_composition: 'reconstructed', hypothetical: 'hypothetical', not_attested_for_this_structure: 'not attested', unavailable: 'no form'};

const chat = {
  ws: null, connected: false, persona: null, personas: [], heartbeat: null, retry: 0, reconnectTimer: null,
  speechQueue: [], speaking: false, currentStream: null, muted: false, recognizer: null, listening: false,
  avatarBubble: null, track: null, trackStart: 0, trackOffset: 0, uiState: 'offline', wantListening: false,
  started: false,
};

// ---------------------------------------------------------------- avatar renderer
const face = {weights: {}, target: {}, blink: 0, nextBlink: performance.now() + 2500, gaze: {x: 0, y: 0}, raf: 0};
const CH = ['jawOpen', 'mouthClose', 'mouthFunnel', 'mouthPucker', 'mouthSmileLeft', 'mouthSmileRight', 'mouthStretchLeft', 'mouthStretchRight',
  'mouthPressLeft', 'mouthPressRight', 'mouthLowerDownLeft', 'mouthLowerDownRight', 'tongueOut'];
CH.forEach(name => { face.weights[name] = 0; face.target[name] = 0; });

function headwearPath(kind) {
  if (kind === 'nemes') return 'M92 176 C96 96 150 60 200 60 C250 60 304 96 308 176 L330 300 C300 290 286 250 288 200 C270 150 240 126 200 126 C160 126 130 150 112 200 C114 250 100 290 70 300 Z';
  if (kind === 'kitabu' || kind === 'kitambaa') return 'M104 150 C112 82 162 50 206 52 C262 54 300 92 300 150 C272 122 240 108 200 108 C160 108 130 122 104 150 Z M206 52 C236 30 270 34 282 58 C256 50 232 52 206 52 Z';
  return '';
}

function applyLook(persona) {
  const look = persona?.look || {};
  const stage = $('#avatarStage');
  stage.style.setProperty('--avatar-skin', look.skin || '#a8693f');
  stage.style.setProperty('--avatar-hair', look.hair || '#1d1a1a');
  stage.style.setProperty('--avatar-accent', look.accent || '#c79a2c');
  stage.style.setProperty('--avatar-eyes', look.eyes || '#2b1b10');
  $('#avatarHeadwear').setAttribute('d', headwearPath(look.headwear));
  $('#avatarSvgTitle').textContent = persona ? `${persona.name}, ${persona.title}` : 'Animated guide';
}

function mouthPaths(w) {
  const cx = 200, cy = 258;
  const smile = (w.mouthSmileLeft + w.mouthSmileRight) / 2;
  const stretch = (w.mouthStretchLeft + w.mouthStretchRight) / 2;
  const press = (w.mouthPressLeft + w.mouthPressRight) / 2;
  const round = Math.max(w.mouthFunnel, w.mouthPucker);
  const open = Math.max(0, w.jawOpen * 34 + (w.mouthLowerDownLeft + w.mouthLowerDownRight) * 4 - w.mouthClose * 10 - press * 6);
  const half = 30 + stretch * 10 + smile * 6 - round * 13 - w.mouthPucker * 4;
  const corner = cy - smile * 7 + stretch * 1.5;
  const upper = cy - 3 - round * 2 - open * 0.18;
  const lower = cy + 2 + open;
  const l = cx - half, r = cx + half;
  const upperLip = `M${l} ${corner} C${cx - half * .5} ${upper - 6} ${cx - 6} ${upper - 7} ${cx} ${upper - 3} C${cx + 6} ${upper - 7} ${cx + half * .5} ${upper - 6} ${r} ${corner} C${cx + half * .5} ${upper + 3} ${cx - half * .5} ${upper + 3} ${l} ${corner} Z`;
  const lowerLip = `M${l} ${corner} C${cx - half * .45} ${lower - 1} ${cx + half * .45} ${lower - 1} ${r} ${corner} C${cx + half * .5} ${lower + 9 - round * 2} ${cx - half * .5} ${lower + 9 - round * 2} ${l} ${corner} Z`;
  const inner = `M${l + 2} ${corner} C${cx - half * .5} ${upper + 2} ${cx + half * .5} ${upper + 2} ${r - 2} ${corner} C${cx + half * .45} ${lower} ${cx - half * .45} ${lower} ${l + 2} ${corner} Z`;
  const teethY = upper + 2;
  const teeth = open > 4 ? `M${cx - half * .6} ${teethY} L${cx + half * .6} ${teethY} L${cx + half * .55} ${teethY + Math.min(6, open * .35)} L${cx - half * .55} ${teethY + Math.min(6, open * .35)} Z` : '';
  const tongue = w.tongueOut > .05 && open > 3 ? `M${cx - 12} ${lower - 2} Q${cx} ${lower - 4 - w.tongueOut * 10} ${cx + 12} ${lower - 2} Z` : '';
  return {upperLip, lowerLip, inner, teeth, tongue};
}

function trackWeights(now) {
  const track = chat.track;
  if (!track) return null;
  const t = (now - chat.trackStart) / 1000 + chat.trackOffset;
  const frames = track.frames;
  if (t > track.duration + 0.25) return null;
  let index = 0;
  while (index < frames.length - 1 && frames[index + 1].t <= t) index += 1;
  const a = frames[index], b = frames[Math.min(index + 1, frames.length - 1)];
  const span = Math.max(0.001, b.t - a.t);
  const k = Math.min(1, Math.max(0, (t - a.t) / span));
  const out = {};
  CH.forEach(name => { out[name] = (a.w[name] || 0) * (1 - k) + (b.w[name] || 0) * k; });
  return out;
}

function renderFace(now) {
  const fromTrack = chat.speaking ? trackWeights(now) : null;
  CH.forEach(name => {
    const target = fromTrack ? fromTrack[name] : (name === 'mouthSmileLeft' || name === 'mouthSmileRight' ? (chat.uiState === 'listening' ? .25 : .12) : 0);
    face.weights[name] += (target - face.weights[name]) * (fromTrack ? 0.45 : 0.15);
  });
  const paths = mouthPaths(face.weights);
  $('#avatarLipUpper').setAttribute('d', paths.upperLip);
  $('#avatarLipLower').setAttribute('d', paths.lowerLip);
  $('#avatarMouthInner').setAttribute('d', paths.inner);
  $('#avatarTeeth').setAttribute('d', paths.teeth);
  $('#avatarTongue').setAttribute('d', paths.tongue);

  // eyeBlinkLeft/Right
  if (now > face.nextBlink) { face.blink = 1; face.nextBlink = now + 2200 + Math.random() * 3200; }
  face.blink = Math.max(0, face.blink - 0.12);
  const lid = face.blink > 0 ? 1 - Math.abs(face.blink * 2 - 1) : 0;
  const open = 1 - lid * 0.92;
  ['#avatarEyeL', '#avatarEyeR'].forEach(id => $(id).setAttribute('transform', `translate(0 186) scale(1 ${open}) translate(0 -186)`));

  // eyeLook*, browInnerUp and head motion by state
  const thinking = chat.uiState === 'thinking';
  const gx = thinking ? 4 : Math.sin(now / 2300) * 1.6;
  const gy = thinking ? -4 : Math.sin(now / 3100) * 1;
  face.gaze.x += (gx - face.gaze.x) * 0.08;
  face.gaze.y += (gy - face.gaze.y) * 0.08;
  document.querySelectorAll('.avatar-iris, .avatar-glint').forEach(el => el.setAttribute('transform', `translate(${face.gaze.x} ${face.gaze.y})`));
  const browUp = chat.uiState === 'listening' ? -5 : thinking ? -3 : chat.speaking ? -1.5 - face.weights.jawOpen * 3 : 0;
  $('#avatarBrows').setAttribute('transform', `translate(0 ${browUp})`);
  const calm = REDUCED_MOTION.matches ? 0 : 1;
  const breathe = Math.sin(now / 1400) * 1.4 * calm;
  const tilt = chat.uiState === 'listening' ? 3 : thinking ? -2 : chat.speaking ? Math.sin(now / 520) * 1.2 : Math.sin(now / 4000) * 0.8;
  const nod = chat.speaking ? face.weights.jawOpen * 2.5 : 0;
  $('#avatarHead').setAttribute('transform', `rotate(${tilt * calm} 200 300) translate(0 ${breathe * 0.6 + nod * calm})`);
  $('#avatarBody').setAttribute('transform', `translate(0 ${breathe})`);
  face.raf = requestAnimationFrame(renderFace);
}

function setUiState(next) {
  chat.uiState = next;
  const stage = $('#avatarStage');
  stage.dataset.state = next;
  $('#avatarStateBadge').textContent = chat.persona && next !== 'offline' && next !== 'connecting' ? `${chat.persona.name} · ${STATE_LABELS[next]}` : STATE_LABELS[next];
  $('#avatarInterruptBtn').disabled = !(next === 'speaking' || next === 'thinking');
}

// ---------------------------------------------------------------- protocol
function rid() { return Math.random().toString(36).slice(2, 14); }
function send(name, payload) {
  if (!chat.ws || chat.ws.readyState !== WebSocket.OPEN) return false;
  chat.ws.send(JSON.stringify({header: {name, request_id: rid()}, payload: payload || {}}));
  return true;
}

function socketUrl() {
  const scheme = location.protocol === 'https:' ? 'wss' : 'ws';
  return `${scheme}://${location.host}/ws/avatar`;
}

function connect() {
  clearTimeout(chat.reconnectTimer);
  setUiState('connecting');
  const ws = new WebSocket(socketUrl());
  chat.ws = ws;
  ws.addEventListener('open', () => {
    chat.retry = 0;
    send('InitializeAvatarSession', {persona: $('#avatarPersona').value || 'nefer', context: appContext()});
    clearInterval(chat.heartbeat);
    chat.heartbeat = setInterval(() => send('TriggerHeartbeat'), HEARTBEAT_MS);
  });
  ws.addEventListener('message', event => {
    let message;
    try { message = JSON.parse(event.data); } catch { return; }
    handle(message.header?.name, message.payload || {});
  });
  ws.addEventListener('close', () => {
    chat.connected = false;
    clearInterval(chat.heartbeat);
    stopVoice();
    setUiState('offline');
    $('#avatarSendBtn').disabled = true;
    $('#avatarMicBtn').disabled = true;
    if (!document.hidden && chat.started) {
      const delay = Math.min(15000, 1000 * 2 ** chat.retry++);
      $('#avatarStatus').textContent = `Disconnected. Reconnecting in ${Math.round(delay / 1000)}s…`;
      chat.reconnectTimer = setTimeout(connect, delay);
    }
  });
}

function handle(name, payload) {
  switch (name) {
    case 'AvatarSessionInitialized': return onInitialized(payload);
    case 'EchoHumanText': return addBubble('human', payload.text);
    case 'EchoAvatarText': return onAvatarText(payload);
    case 'AvatarSpeech': return enqueueSpeech(payload);
    case 'AvatarCard': return addCard(payload.card);
    case 'AvatarNotice': return addNotice(payload.text);
    case 'ChatSignal':
      if (payload.type === 'stream_begin' && payload.stream_type === 'avatar_text') { chat.currentStream = payload.stream_key; chat.avatarBubble = null; if (!chat.speaking) setUiState('thinking'); }
      if (payload.type === 'stream_cancel' && payload.stream_key === chat.currentStream) stopVoice();
      return;
    case 'InterruptAccepted':
    case 'InterruptNotification':
      stopVoice();
      if (chat.avatarBubble) chat.avatarBubble.classList.add('interrupted');
      return setUiState(chat.listening ? 'listening' : 'idle');
    case 'Error':
      addNotice(payload.message || 'Something went wrong.');
      if (payload.code === 'RATE_LIMIT') toast(payload.message);
      return;
    default: return;
  }
}

function onInitialized(payload) {
  chat.connected = true;
  chat.persona = payload.persona;
  chat.personas = payload.personas || [];
  const select = $('#avatarPersona');
  if (!select.options.length) {
    select.innerHTML = chat.personas.map(p => `<option value="${esc(p.id)}">${esc(p.name)} — ${esc(p.title)}</option>`).join('');
  }
  select.value = chat.persona.id;
  applyLook(chat.persona);
  renderSuggestions();
  $('#avatarSendBtn').disabled = false;
  $('#avatarMicBtn').disabled = !speechRecognitionSupported();
  $('#avatarModelNote').textContent = payload.llm?.configured
    ? `Conversation by ${payload.llm.model}; translations come from the verified ancient-language ladder.`
    : 'No language model is connected, so the guide answers translations and word meanings from the built-in ladder. Set OPENAI_API_KEY (or an OpenAI-compatible endpoint) for open conversation.';
  $('#avatarStatus').textContent = speechRecognitionSupported()
    ? 'Press Start talking and speak, or type below. Your browser does the speech recognition and the voice.'
    : 'Voice input is not supported in this browser; type below. The guide still speaks if your browser has voices.';
  setUiState(chat.listening ? 'listening' : 'idle');
  if (chat.wantListening) startListening();
}

// ---------------------------------------------------------------- records
function addBubble(role, text) {
  const records = $('#avatarRecords');
  const bubble = document.createElement('div');
  bubble.className = `avatar-bubble ${role}`;
  bubble.innerHTML = `<span class="avatar-bubble-who">${role === 'human' ? 'You' : esc(chat.persona?.name || 'Guide')}</span><div class="avatar-bubble-text"></div>`;
  bubble.querySelector('.avatar-bubble-text').textContent = text || '';
  records.appendChild(bubble);
  records.scrollTop = records.scrollHeight;
  return bubble;
}

function onAvatarText(payload) {
  if (payload.mode === 'full_text') {
    chat.avatarBubble = addBubble('avatar', payload.text);
    return;
  }
  if (!chat.avatarBubble && payload.text) chat.avatarBubble = addBubble('avatar', '');
  if (chat.avatarBubble && payload.text) {
    chat.avatarBubble.querySelector('.avatar-bubble-text').textContent += payload.text;
    $('#avatarRecords').scrollTop = $('#avatarRecords').scrollHeight;
  }
  if (payload.end_of_speech) chat.avatarBubble = null;
}

function addCard(card) {
  if (!card?.rows?.length) return;
  const host = document.createElement('div');
  host.className = 'avatar-card';
  host.innerHTML = `<div class="microcopy">${card.type === 'concept' ? `Word: ${esc(card.concept)}` : `“${esc(card.source)}”`}</div>` + card.rows.map(row => {
    const scripts = Object.entries(row.scripts || {}).filter(([, v]) => v).slice(0, 2).map(([k, v]) => `<span class="avatar-card-script" ${k.includes('arabic') || k === 'safaitic' ? 'dir="rtl"' : ''}>${esc(v)}</span>`).join('');
    return `<div class="avatar-card-row"><span class="avatar-card-lang">${esc(row.name)}</span><span class="avatar-card-text">${esc(row.text || '—')}</span>${scripts}<span class="pill">${esc(STATUS_LABELS[row.status] || row.status)}</span></div>`;
  }).join('');
  $('#avatarRecords').appendChild(host);
  $('#avatarRecords').scrollTop = $('#avatarRecords').scrollHeight;
}

function addNotice(text) {
  const el = document.createElement('div');
  el.className = 'avatar-notice';
  el.textContent = text;
  $('#avatarRecords').appendChild(el);
}

function renderSuggestions() {
  const list = SUGGESTIONS[chat.persona?.language] || SUGGESTIONS.english;
  $('#avatarSuggestions').innerHTML = list.map((text, i) => `<button type="button" class="chip" data-suggest="${i}">${esc(text)}</button>`).join('');
}

// ---------------------------------------------------------------- voice out (TTS) + lip sync
function enqueueSpeech(payload) {
  if (payload.stream_key !== chat.currentStream && payload.stream_key) chat.currentStream = payload.stream_key;
  chat.speechQueue.push(payload);
  if (!chat.speaking) playNext();
}

function pickVoice(lang) {  // best voice for the persona; the browser default is used if none matches
  const voices = window.speechSynthesis?.getVoices?.() || [];
  const lower = (lang || 'en-US').toLowerCase();
  return voices.find(v => v.lang.toLowerCase() === lower) || voices.find(v => v.lang.toLowerCase().startsWith(lower.split('-')[0]));
}

function playNext() {
  const item = chat.speechQueue.shift();
  if (!item) {
    chat.speaking = false;
    chat.track = null;
    $('#avatarSubtitle').textContent = '';
    if (chat.uiState === 'speaking') setUiState(chat.listening ? 'listening' : 'idle');
    return;
  }
  if (!item.text) {
    if (item.end_of_speech) send('EndSpeech', {stream_key: item.stream_key});
    return playNext();
  }
  chat.speaking = true;
  setUiState('speaking');
  $('#avatarSubtitle').textContent = $('#avatarSubtitles').checked ? item.text : '';
  let started = false;
  let done = false;
  const startTrack = () => { started = true; chat.track = item.motion; chat.trackStart = performance.now(); chat.trackOffset = 0; };
  const finish = () => {
    if (done) return;
    done = true;
    clearTimeout(chat.silentTimer);
    if (item.end_of_speech) send('EndSpeech', {stream_key: item.stream_key});
    playNext();
  };
  const silent = () => {
    // No usable voice (muted, unsupported or blocked): animate with subtitles at speaking pace.
    startTrack();
    chat.silentTimer = setTimeout(finish, Math.max(900, (item.motion?.duration || 1) * 1000 + 250));
  };
  if (!('speechSynthesis' in window) || chat.muted) return silent();
  const utterance = new SpeechSynthesisUtterance(item.text);
  utterance.lang = item.voice?.lang || 'en-US';
  utterance.voice = pickVoice(utterance.lang) || null;
  utterance.rate = item.voice?.rate || 0.95;
  utterance.pitch = item.voice?.pitch || 1;
  utterance.onstart = startTrack;
  utterance.onboundary = event => {
    // Re-time the motion track against the real voice (keeps lips in step).
    if (!item.motion || !item.text.length || event.name !== 'word') return;
    const expected = (event.charIndex / item.text.length) * item.motion.duration;
    const actual = (performance.now() - chat.trackStart) / 1000;
    chat.trackOffset = expected - actual;
  };
  utterance.onend = finish;
  utterance.onerror = () => { if (!started) silent(); else finish(); };
  window.speechSynthesis.speak(utterance);
  // Some browsers never start speaking until a user gesture; fall back to silent lip-sync.
  chat.silentTimer = setTimeout(() => {
    if (started || done) return;
    window.speechSynthesis.cancel();
    silent();
  }, 2500);
}

function stopVoice() {
  chat.speechQueue = [];
  clearTimeout(chat.silentTimer);
  if ('speechSynthesis' in window) window.speechSynthesis.cancel();
  chat.speaking = false;
  chat.track = null;
  $('#avatarSubtitle').textContent = '';
}

function interrupt() {
  if (!chat.connected) return;
  stopVoice();
  send('Interrupt');
}

// ---------------------------------------------------------------- voice in (ASR)
function startListening() {
  if (!speechRecognitionSupported() || !chat.connected) return;
  chat.wantListening = true;
  chat.recognizer?.abort?.();
  chat.recognizer = createRecognizer({
    language: chat.persona?.language || 'english',
    onInterim: text => {
      $('#avatarInput').value = text;
      // Full-duplex barge-in, like OAC's duplex VAD: speaking over the guide interrupts it.
      if ($('#avatarBargeIn').checked && chat.speaking && text.split(/\s+/).length >= 3) interrupt();
    },
    onFinal: text => {
      $('#avatarInput').value = '';
      sendText(text);
    },
    onStatus: () => {},
    onError: event => {
      if (event.error === 'not-allowed' || event.error === 'service-not-allowed') {
        chat.wantListening = false;
        toast('Microphone permission was denied.');
      }
    },
    onEnd: () => {
      chat.listening = false;
      if (chat.wantListening && chat.connected) setTimeout(startListening, 250);
      else updateMicButton();
    },
  });
  try {
    chat.recognizer.start();
    chat.listening = true;
  } catch {
    chat.listening = false;
  }
  updateMicButton();
  if (!chat.speaking) setUiState('listening');
}

function stopListening() {
  chat.wantListening = false;
  chat.listening = false;
  chat.recognizer?.stop?.();
  updateMicButton();
  if (!chat.speaking && chat.uiState === 'listening') setUiState('idle');
}

function updateMicButton() {
  const on = chat.wantListening;
  $('#avatarMicBtn').setAttribute('aria-pressed', on ? 'true' : 'false');
  $('#avatarMicLabel').textContent = on ? 'Stop talking' : 'Start talking';
}

// ---------------------------------------------------------------- text in
function sendText(text) {
  const value = String(text || '').trim();
  if (!value) return;
  if (!chat.connected) return toast('The guide is reconnecting. Try again in a moment.');
  if (chat.speaking) stopVoice();
  send('UpdateContext', appContext());
  send('SendHumanText', {stream_key: `stream_client_${rid()}`, mode: 'full_text', text: value, end_of_speech: true});
  setUiState('thinking');
}

function appContext() {
  const active = document.querySelector('#tabs button.active')?.dataset.tab || 'avatar';
  const last = appState.lastTranslation;
  return {
    active_tab: active,
    last_translation_source: last?.source_text || last?.source || '',
    last_translation_target: last?.target_language || '',
  };
}

// ---------------------------------------------------------------- init
export function initAvatarChat() {
  if (!$('#avatar')) return;
  applyLook(null);
  face.raf = requestAnimationFrame(renderFace);
  const begin = () => {
    if (chat.started) return;
    chat.started = true;
    connect();
  };
  // Connect when the tab is first opened, so the greeting is heard rather than missed.
  const tabButton = document.querySelector('#tabs button[data-tab="avatar"]');
  tabButton?.addEventListener('click', begin);
  if (location.hash === '#avatar') begin();

  $('#avatarForm').addEventListener('submit', event => {
    event.preventDefault();
    sendText($('#avatarInput').value);
    $('#avatarInput').value = '';
  });
  $('#avatarInput').addEventListener('keydown', event => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      $('#avatarForm').requestSubmit();
    }
  });
  $('#avatarSuggestions').addEventListener('click', event => {
    const button = event.target.closest('[data-suggest]');
    if (!button) return;
    const list = SUGGESTIONS[chat.persona?.language] || SUGGESTIONS.english;
    sendText(list[Number(button.dataset.suggest)]);
  });
  $('#avatarMicBtn').addEventListener('click', () => (chat.wantListening ? stopListening() : startListening()));
  $('#avatarInterruptBtn').addEventListener('click', interrupt);
  $('#avatarMuteBtn').addEventListener('click', () => {
    chat.muted = !chat.muted;
    $('#avatarMuteBtn').setAttribute('aria-pressed', chat.muted ? 'true' : 'false');
    $('#avatarMuteBtn').textContent = chat.muted ? 'Unmute voice' : 'Mute voice';
    if (chat.muted && 'speechSynthesis' in window) window.speechSynthesis.cancel();
  });
  $('#avatarPersona').addEventListener('change', event => {
    stopVoice();
    stopListening();
    $('#avatarRecords').innerHTML = '';
    send('SetPersona', {persona: event.target.value});
  });
  $('#avatarSubtitles').addEventListener('change', () => { if (!$('#avatarSubtitles').checked) $('#avatarSubtitle').textContent = ''; });
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden && chat.started && (!chat.ws || chat.ws.readyState === WebSocket.CLOSED)) connect();
  });
  if ('speechSynthesis' in window) window.speechSynthesis.onvoiceschanged = () => {};
}
