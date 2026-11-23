// Live avatar chat: an OpenAvatarChat-style session in the browser.
// Pipeline per turn (as in OAC): mic -> speech recognition (browser ASR + VAD)
// -> SendHumanText -> server streams EchoAvatarText + AvatarSpeech sentences
// -> speech synthesis (TTS) -> ARKit blendshape motion drives the SVG face.
import {$, esc, state as appState, toast} from './core.js';
import {createRecognizer, speechRecognitionSupported} from './speech.js';

const HEARTBEAT_MS = 10000;
const REDUCED_MOTION = window.matchMedia('(prefers-reduced-motion: reduce)');
const SUGGESTIONS = {
  english: ['Read this to me: 𓋹𓈖𓐍 𓄤𓆑𓂋', 'How do you say “the king made a great house” in Sumerian?', 'What does lugal mean?', 'Read this: ተወከልኩ፡በአማን።'],
  swahili: ['Nisomee: 𓋹𓈖𓐍 𓄤𓆑𓂋', 'Tafsiri “mfalme alipenda mama” kwa Kilatini', 'Maana ya lugal ni nini?', 'Nisomee: ተወከልኩ፡በአማን።'],
};
const STATE_LABELS = {offline: 'Offline', connecting: 'Connecting…', idle: 'Ready', listening: 'Listening…', thinking: 'Thinking…', speaking: 'Speaking'};
const STATUS_LABELS = {attested: 'attested', composed: 'composed', reconstructed: 'reconstructed', reconstructed_composition: 'reconstructed', hypothetical: 'hypothetical', not_attested_for_this_structure: 'not attested', unavailable: 'no form'};

const chat = {
  ws: null, connected: false, persona: null, personas: [], heartbeat: null, retry: 0, reconnectTimer: null,
  speechQueue: [], speaking: false, currentStream: null, muted: false, recognizer: null, listening: false,
  avatarBubble: null, track: null, trackStart: 0, trackOffset: 0, uiState: 'offline', wantListening: false,
  started: false, cameraOn: false, cameraStream: null, liveTimer: null, readingCard: null, pendingImage: null, vision: {},
  languageChosen: false,
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
    const initial = {persona: $('#avatarPersona').value || 'nefer', context: appContext()};
    if (chat.languageChosen) initial.language = $('#avatarLanguage').value;
    send('InitializeAvatarSession', initial);
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
    case 'EchoHumanText':
      if (payload.attachment?.type === 'image') return addImageBubble(chat.pendingImage, payload.text);
      return addBubble('human', payload.text);
    case 'EchoAvatarText': return onAvatarText(payload);
    case 'AvatarSpeech': return enqueueSpeech(payload);
    case 'AvatarCard': return addCard(payload.card);
    case 'AvatarReading': return addReading(payload.reading);
    case 'AvatarLiveStatus': return onLiveStatus(payload.status);
    case 'LanguageChanged':
      chat.persona = payload.persona;
      $('#avatarLanguage').value = payload.language;
      renderSuggestions();
      if (chat.wantListening) startListening();
      return;
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
  $('#avatarLanguage').value = payload.language || chat.persona.language;
  chat.vision = payload.vision || {};
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
    highlightSegment(null);
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
  const startTrack = () => {
    started = true;
    chat.track = item.motion; chat.trackStart = performance.now(); chat.trackOffset = 0;
    if (item.quiz === 'start') { chat.quizzing = true; chat.readingCard?.classList.add('quiz'); }
    if (item.quiz_done) {
      chat.quizzing = false;
      chat.readingCard?.classList.remove('quiz');
      $('#avatarBoard').hidden = true;
    }
    highlightSegment(item.segment, item.correct);
  };
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
const LOOK_QUESTION = /\b(what does (this|it|that) say|what is (this|that)|read (this|it|that)|translate (this|it|that)|what am i looking at|can you see|inasema nini|nisomee|hii ni nini|tafsiri hii|unaona)\b/i;

function sendText(text) {
  const value = String(text || '').trim();
  if (!value) return;
  if (!chat.connected) return toast('The guide is reconnecting. Try again in a moment.');
  if (chat.cameraOn && LOOK_QUESTION.test(value)) return snapAndAsk(value, 'camera');
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

// ---------------------------------------------------------------- reading card (follow along like a book)
const RTL_SCRIPTS = new Set(['arabic', 'old_north_arabian']);
const DIRECTION_ARROWS = {right_to_left: '← read right to left', left_to_right: 'read left to right →', top_to_bottom: 'read top to bottom ↓', as_written: 'read in written order'};
const STATUS_TEXT = {confirmed: 'confirmed', model_reading: 'read from photo', disputed: 'disputed', sign_only: 'sign values only'};

function addReading(reading) {
  if (!reading?.segments?.length) return;
  chat.readingCard?.classList.remove('current');
  const card = document.createElement('div');
  card.className = 'avatar-reading current';
  const dirAttr = RTL_SCRIPTS.has(reading.script) || reading.direction === 'right_to_left' ? 'dir="rtl"' : '';
  card.innerHTML = `
    <div class="avatar-reading-head">
      <div><strong>${esc(reading.script_name || reading.script)}</strong>${reading.language_name ? ` · ${esc(reading.language_name)}` : ''}</div>
      <span class="pill">${esc(DIRECTION_ARROWS[reading.direction] || DIRECTION_ARROWS.as_written)}</span>
    </div>
    ${reading.translation?.[reading.explain_language] || reading.translation?.english ? `<div class="avatar-reading-translation">${esc(reading.translation[reading.explain_language] || reading.translation.english)}</div>` : ''}
    <div class="avatar-reading-words" ${dirAttr}>
      ${reading.segments.map((seg, i) => `
        <button type="button" class="avatar-word status-${esc(seg.status)}" data-segment="${i}" title="Ask about word ${i + 1}">
          <span class="avatar-word-glyphs" dir="auto">${esc(seg.original || seg.transliteration || '…')}</span>
          <span class="avatar-word-translit" dir="ltr">${esc(seg.transliteration || '')}</span>
          <span class="avatar-word-say" dir="ltr">${seg.pronunciation ? `“${esc(seg.pronunciation)}”` : ''}</span>
          <span class="avatar-word-meaning" dir="ltr">${esc(seg.meaning?.[reading.explain_language] || seg.meaning?.english || '—')}</span>
        </button>`).join('')}
    </div>
    <details class="avatar-reading-signs"><summary>Sign by sign</summary>
      ${reading.segments.map((seg, i) => `<div class="avatar-sign-row"><span class="microcopy">Word ${i + 1}</span>${(seg.signs || []).map(sign => `
        <span class="avatar-sign" title="${esc(sign.role_label || sign.role)}"><b dir="auto">${esc(sign.glyph)}</b>${sign.code ? `<small>${esc(sign.code)}</small>` : ''}<small>${esc(sign.value || '')}</small><em>${esc(sign.role_label || sign.role)}</em></span>`).join('')}</div>`).join('')}
    </details>
    ${reading.notes?.length ? `<p class="microcopy">${esc(reading.notes.join(' '))}</p>` : ''}
    <div class="avatar-reading-actions">
      <button type="button" class="chip" data-say="${chat.persona?.language === 'swahili' ? 'nijaribu' : 'quiz me'}">${chat.persona?.language === 'swahili' ? 'Nijaribu' : 'Quiz me'}</button>
      <button type="button" class="chip" data-say="${chat.persona?.language === 'swahili' ? 'soma tena' : 'read it again'}">${chat.persona?.language === 'swahili' ? 'Soma tena' : 'Read it again'}</button>
      <button type="button" class="chip" data-say="${chat.persona?.language === 'swahili' ? 'polepole' : 'slower'}">${chat.persona?.language === 'swahili' ? 'Polepole' : 'Slower'}</button>
    </div>`;
  card.addEventListener('click', event => {
    const word = event.target.closest('[data-segment]');
    if (word) return sendText(`${chat.persona?.language === 'swahili' ? 'neno la' : 'word'} ${Number(word.dataset.segment) + 1}`);
    const say = event.target.closest('[data-say]');
    if (say) sendText(say.dataset.say);
  });
  chat.readingCard = card;
  chat.reading = reading;
  chat.quizzing = false;
  $('#avatarRecords').appendChild(card);
  $('#avatarRecords').scrollTop = $('#avatarRecords').scrollHeight;
}

function showBoard(index, correct) {
  const board = $('#avatarBoard');
  const segment = chat.reading?.segments?.[index];
  if (index === null || index === undefined || !segment || !$('#avatarFollowAlong').checked) {
    if (!chat.quizzing) board.hidden = true;
    return;
  }
  const lang = chat.reading.explain_language;
  board.hidden = false;
  board.classList.remove('right', 'wrong');
  if (correct === true || correct === false) board.classList.add(correct ? 'right' : 'wrong');
  $('#avatarBoardGlyphs').textContent = segment.original || segment.transliteration;
  const hide = chat.quizzing && correct === undefined;
  $('#avatarBoardTranslit').textContent = hide ? '?' : `${segment.transliteration}${segment.pronunciation && segment.pronunciation !== segment.transliteration ? ` · “${segment.pronunciation}”` : ''}`;
  $('#avatarBoardHint').textContent = chat.quizzing ? '' : (segment.meaning?.[lang] || segment.meaning?.english || '');
}

function highlightSegment(index, correct) {
  const card = chat.readingCard;
  showBoard(index, correct);
  if (!card) return;
  card.querySelectorAll('.avatar-word.active').forEach(el => el.classList.remove('active'));
  if (index === null || index === undefined || !$('#avatarFollowAlong').checked) return;
  const word = card.querySelector(`.avatar-word[data-segment="${index}"]`);
  if (!word) return;
  word.classList.add('active');
  if (correct === true || correct === false) {
    word.classList.remove('right', 'wrong');
    word.classList.add(correct ? 'right' : 'wrong');
    setTimeout(() => word.classList.remove('right', 'wrong'), 1600);
  }
  word.scrollIntoView({block: 'nearest', inline: 'nearest', behavior: REDUCED_MOTION.matches ? 'auto' : 'smooth'});
}

// ---------------------------------------------------------------- seeing: photos, camera, live reading
const MAX_SIDE = 1280;

function frameToDataUrl(source, width, height) {
  const scale = Math.min(1, MAX_SIDE / Math.max(width, height));
  const canvas = $('#avatarCanvas');
  canvas.width = Math.round(width * scale);
  canvas.height = Math.round(height * scale);
  canvas.getContext('2d').drawImage(source, 0, 0, canvas.width, canvas.height);
  return canvas.toDataURL('image/jpeg', 0.82);
}

function sendImage(dataUrl, question, source) {
  if (!chat.connected) return toast('The guide is reconnecting. Try again in a moment.');
  if (source !== 'live') {
    chat.pendingImage = dataUrl;
    if (chat.speaking) stopVoice();
    setUiState('thinking');
  }
  send('SendHumanImage', {image: dataUrl, text: question || '', source});
}

async function shareFile(file) {
  if (!file || !/^image\/(png|jpeg|webp)$/.test(file.type)) return toast('Share a PNG, JPEG or WebP photo.');
  if (file.size > 25 * 1024 * 1024) return toast('That photo is too large.');
  try {
    const bitmap = await createImageBitmap(file);
    const dataUrl = frameToDataUrl(bitmap, bitmap.width, bitmap.height);
    bitmap.close?.();
    const question = $('#avatarInput').value.trim();
    $('#avatarInput').value = '';
    sendImage(dataUrl, question, 'upload');
  } catch {
    toast('Could not open that image.');
  }
}

function addImageBubble(dataUrl, text) {
  const bubble = addBubble('human', text || '');
  if (dataUrl) {
    const img = document.createElement('img');
    img.src = dataUrl;
    img.alt = 'Shared image';
    img.className = 'avatar-bubble-image';
    bubble.insertBefore(img, bubble.querySelector('.avatar-bubble-text'));
  }
  chat.pendingImage = null;
  $('#avatarRecords').scrollTop = $('#avatarRecords').scrollHeight;
}

async function toggleCamera() {
  if (chat.cameraOn) return stopCamera();
  if (!navigator.mediaDevices?.getUserMedia) return toast('This browser cannot open the camera.');
  try {
    chat.cameraStream = await navigator.mediaDevices.getUserMedia({video: {facingMode: {ideal: 'environment'}, width: {ideal: 1280}, height: {ideal: 720}}, audio: false});
  } catch {
    return toast('Camera permission was denied or no camera is available.');
  }
  const video = $('#avatarVideo');
  video.srcObject = chat.cameraStream;
  $('#avatarCameraBox').hidden = false;
  chat.cameraOn = true;
  $('#avatarCameraBtn').setAttribute('aria-pressed', 'true');
  $('#avatarSnapBtn').disabled = false;
  $('#avatarLiveBtn').disabled = false;
  if (!chat.vision?.vision_model && !chat.vision?.on_device_detector) {
    addNotice('The camera works, but no vision model is connected, so the guide cannot read images yet. You can paste signs as text instead.');
  }
}

function stopCamera() {
  stopLive();
  chat.cameraStream?.getTracks().forEach(track => track.stop());
  chat.cameraStream = null;
  chat.cameraOn = false;
  $('#avatarVideo').srcObject = null;
  $('#avatarCameraBox').hidden = true;
  $('#avatarCameraBtn').setAttribute('aria-pressed', 'false');
  $('#avatarSnapBtn').disabled = true;
  $('#avatarLiveBtn').disabled = true;
}

function snapAndAsk(question, source = 'camera') {
  const video = $('#avatarVideo');
  if (!chat.cameraOn || !video.videoWidth) return toast('The camera is still starting.');
  sendImage(frameToDataUrl(video, video.videoWidth, video.videoHeight), question, source);
}

// Live reading: sample a tiny greyscale frame, wait for the view to change and then hold still,
// and only then send it, so the guide reads new things without being flooded.
function sampleSignature() {
  const video = $('#avatarVideo');
  if (!video.videoWidth) return null;
  const canvas = chat.sampleCanvas || (chat.sampleCanvas = document.createElement('canvas'));
  canvas.width = 32; canvas.height = 24;
  const ctx = canvas.getContext('2d', {willReadFrequently: true});
  ctx.drawImage(video, 0, 0, 32, 24);
  const data = ctx.getImageData(0, 0, 32, 24).data;
  const grey = new Uint8Array(32 * 24);
  for (let i = 0; i < grey.length; i += 1) grey[i] = (data[i * 4] * 0.3 + data[i * 4 + 1] * 0.59 + data[i * 4 + 2] * 0.11) | 0;
  return grey;
}

function difference(a, b) {
  if (!a || !b) return 255;
  let total = 0;
  for (let i = 0; i < a.length; i += 1) total += Math.abs(a[i] - b[i]);
  return total / a.length;
}

function liveTick() {
  const current = sampleSignature();
  const sinceSent = difference(current, chat.liveSent);
  const motion = difference(current, chat.livePrev);
  chat.livePrev = current;
  const steady = motion < 6;
  chat.liveSteady = steady ? (chat.liveSteady || 0) + 1 : 0;
  const busy = chat.speaking || chat.uiState === 'thinking';
  const cooled = performance.now() - (chat.liveLastSend || 0) > 5000;
  if (current && sinceSent > 14 && chat.liveSteady >= 2 && !busy && cooled) {
    chat.liveSent = current;
    chat.liveLastSend = performance.now();
    const video = $('#avatarVideo');
    sendImage(frameToDataUrl(video, video.videoWidth, video.videoHeight), '', 'live');
  }
}

function startLive() {
  if (!chat.cameraOn) return;
  chat.liveTimer = setInterval(liveTick, 700);
  chat.liveSent = null;
  $('#avatarLiveDot').hidden = false;
  $('#avatarLiveBtn').setAttribute('aria-pressed', 'true');
  $('#avatarStatus').textContent = 'Live reading is on: point at writing and hold still. The guide reads new text as it comes into view.';
}

function stopLive() {
  clearInterval(chat.liveTimer);
  chat.liveTimer = null;
  $('#avatarLiveDot').hidden = true;
  $('#avatarLiveBtn').setAttribute('aria-pressed', 'false');
}

function onLiveStatus(status) {
  if (status === 'live_unavailable') {
    stopLive();
    addNotice('Live reading needs a vision model or the on-device sign detector.');
  }
  if (chat.uiState === 'thinking' && !chat.speaking) setUiState(chat.listening ? 'listening' : 'idle');
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
  $('#avatarCameraBtn').addEventListener('click', toggleCamera);
  $('#avatarSnapBtn').addEventListener('click', () => {
    const question = $('#avatarInput').value.trim();
    $('#avatarInput').value = '';
    snapAndAsk(question, 'camera');
  });
  $('#avatarLiveBtn').addEventListener('click', () => (chat.liveTimer ? stopLive() : startLive()));
  $('#avatarFile').addEventListener('change', event => { shareFile(event.target.files?.[0]); event.target.value = ''; });
  $('#avatarInput').addEventListener('paste', event => {
    const file = [...(event.clipboardData?.files || [])].find(f => f.type.startsWith('image/'));
    if (file) { event.preventDefault(); shareFile(file); }
  });
  const chatCard = document.querySelector('.avatar-chat-card');
  chatCard.addEventListener('dragover', event => { event.preventDefault(); chatCard.classList.add('dropping'); });
  chatCard.addEventListener('dragleave', () => chatCard.classList.remove('dropping'));
  chatCard.addEventListener('drop', event => {
    event.preventDefault();
    chatCard.classList.remove('dropping');
    shareFile([...(event.dataTransfer?.files || [])].find(f => f.type.startsWith('image/')));
  });
  $('#avatarLanguage').addEventListener('change', event => {
    stopVoice();
    chat.languageChosen = true;
    send('SetLanguage', {language: event.target.value});
  });
  window.addEventListener('pagehide', stopCamera);
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
    send('SetPersona', {persona: event.target.value, language: $('#avatarLanguage').value});
  });
  $('#avatarSubtitles').addEventListener('change', () => { if (!$('#avatarSubtitles').checked) $('#avatarSubtitle').textContent = ''; });
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden && chat.started && (!chat.ws || chat.ws.readyState === WebSocket.CLOSED)) connect();
  });
  if ('speechSynthesis' in window) window.speechSynthesis.onvoiceschanged = () => {};
}
