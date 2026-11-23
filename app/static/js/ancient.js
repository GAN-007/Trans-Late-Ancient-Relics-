import {get, post} from './api.js';
import {$, esc, setBusy, state as appState, toast} from './core.js';
import {speak} from './speech.js';

const EXAMPLES = [
  ['english', 'The truth, I have put my trust in'],
  ['english', 'The king made a great house'],
  ['english', 'I did not see the king'],
  ['english', 'Is the sun great?'],
  ['swahili', 'Mimi ni mtumishi'],
  ['old_latin', 'ueritatei credidei'],
  ['middle_egyptian', 'n mꜣ nswt jtrw'],
  ['archaic_sumerian', '𒈗𒂊 𒂍 𒃲 𒈬𒌦𒆕'],
  ['english', 'water'],
];

const SCRIPT_LABELS = {
  cuneiform: 'Cuneiform',
  hieroglyphs: 'Hieroglyphs',
  fidel: "Ge'ez fidel",
  archaic_capitals: 'Archaic capitals',
  old_italic: 'Old Italic letters',
  safaitic: 'Safaitic (Ancient North Arabian)',
  early_arabic_rasm: 'Early undotted Arabic (rasm)',
  arabic_unvocalized: 'Arabic script, unvowelled',
};

const STATUS_LABELS = {
  attested: 'Attested word',
  composed: 'Composed sentence',
  reconstructed: 'Reconstructed',
  reconstructed_composition: 'Reconstructed sentence',
  hypothetical: 'Hypothetical',
  not_attested_for_this_structure: 'Not attested this way',
  unavailable: 'No form',
  machine_translation: 'Machine translation',
};

const state = {languages: [], modern: [], mt: false, last: null, quiz: null};

function languageName(id) {
  return state.languages.find(lang => lang.id === id)?.name || state.modern.find(lang => lang.id === id)?.name || id;
}

function fillSelects() {
  const ladder = state.languages.map(lang => `<option value="${esc(lang.id)}">${esc(lang.name)}</option>`).join('');
  const suffix = state.mt ? '' : ' (needs a translator)';
  const modern = state.modern.map(lang => `<option value="${esc(lang.id)}" ${state.mt ? '' : 'disabled'}>${esc(lang.name + suffix)}</option>`).join('');
  const groups = `<optgroup label="Ladder grammar">${ladder}</optgroup><optgroup label="Modern languages (machine translation via English)">${modern}</optgroup>`;
  $('#ladderSource').innerHTML = groups;
  $('#ladderTarget').innerHTML = '<option value="all">Every ancient language</option>' + groups;
  $('#ladderSource').value = 'english';
  $('#ladderQuizLanguage').innerHTML = state.languages.filter(lang => lang.id !== 'english')
    .map(lang => `<option value="${esc(lang.id)}">${esc(lang.name)}</option>`).join('');
  $('#ladderQuizLanguage').value = 'archaic_sumerian';
}

function renderExamples() {
  $('#ladderExamples').innerHTML = EXAMPLES.map(([lang, text], index) =>
    `<button type="button" class="chip" data-example="${index}" title="${esc(languageName(lang))}">${esc(text)}</button>`).join('');
  $('#ladderExamples').addEventListener('click', event => {
    const button = event.target.closest('[data-example]');
    if (!button) return;
    const [lang, text] = EXAMPLES[Number(button.dataset.example)];
    $('#ladderSource').value = lang;
    $('#ladderInput').value = text;
    translate();
  });
}

const PERSON_WORDS = {'1s': 'I', '2ms': 'you', '2fs': 'you (f.)', '3ms': 'he', '3fs': 'she', '1p': 'we', '2p': 'you (pl.)', '3p': 'they'};

function describeMeaning(meaning) {
  if (!meaning) return '';
  const subject = meaning.subject;
  const who = subject?.noun ? `${subject.adj ? subject.adj + ' ' : ''}${subject.noun}` : PERSON_WORDS[subject?.person] || subject?.person;
  const flags = `${meaning.negative ? ' · not' : ''}${meaning.question ? ' · question' : ''}`;
  if (meaning.kind === 'clause') {
    const object = meaning.object ? ` → ${meaning.object.adj ? meaning.object.adj + ' ' : ''}${meaning.object.noun}` : '';
    return `${who} · ${meaning.verb} (${meaning.tense})${object}${flags}`;
  }
  if (meaning.kind === 'identity') {
    const predicate = [meaning.predicate.adj, meaning.predicate.noun].filter(Boolean).join(' ');
    return `${who} = ${predicate}${flags}`;
  }
  if (meaning.kind === 'np') return `${meaning.np.adj ? meaning.np.adj + ' ' : ''}${meaning.np.noun}`;
  return `${meaning.word_kind}: ${meaning.concept}`;
}

function renderMeaning(data) {
  $('#ladderEmpty').hidden = true;
  const box = $('#ladderMeaning');
  box.hidden = false;
  const parse = data.parse || {};
  const list = (title, items) => items?.length ? `<div class="warning"><strong>${esc(title)}</strong> ${esc(items.join(' '))}</div>` : '';
  const bridge = data.bridge ? `<div class="microcopy">${esc(data.bridge.note)} English: “${esc(data.bridge.english)}”</div>` : '';
  const warning = data.warning ? `<div class="warning"><strong>Partly translated.</strong> ${esc(data.warning)}</div>` : '';
  box.innerHTML = data.ok
    ? `${data.meaning ? `<div class="result-primary">${esc(describeMeaning(data.meaning))}</div>` : ''}
       <div class="microcopy">Read from ${esc(languageName(data.source_language))}: “${esc(data.source)}”</div>
       ${bridge}${warning}
       ${list('Ambiguous:', parse.ambiguities)}
       ${parse.notes?.length ? `<p class="microcopy">${esc(parse.notes.join(' '))}</p>` : ''}`
    : `<div class="warning">${esc(data.message || 'No meaning found.')}</div>${list('Not recognized:', parse.unknown_words)}`;
  $('#ladderPolicy').textContent = data.accuracy_policy || '';
}

function scriptBlock(name, value) {
  const rtl = name === 'safaitic' || name.includes('arabic');
  return `<div class="ladder-script">
    <span class="microcopy">${esc(SCRIPT_LABELS[name] || name)}</span>
    <div class="ladder-glyphs script-${esc(name)}" ${rtl ? 'dir="rtl"' : ''}>${esc(value)}</div>
  </div>`;
}

function renderResults(data) {
  const host = $('#ladderResults');
  if (!data.ok) {
    host.innerHTML = '';
    return;
  }
  host.innerHTML = data.targets.map(id => {
    const result = data.results[id];
    const lang = state.languages.find(item => item.id === id) || (result.status === 'machine_translation' || result.via ? {period: 'Modern · machine translation via English', family: ''} : {});
    const scripts = Object.entries(result.scripts || {}).filter(([, value]) => value).map(([name, value]) => scriptBlock(name, value)).join('');
    const gaps = result.gaps?.length ? `<div class="microcopy">No form available for: ${esc(result.gaps.map(gap => gap.concept).join(', '))}</div>` : '';
    const refusal = result.refusal ? `<div class="warning">${esc(result.refusal)}</div>` : '';
    const notes = result.notes?.length ? `<details><summary>Notes</summary><ul>${result.notes.map(note => `<li>${esc(note)}</li>`).join('')}</ul></details>` : '';
    const reusable = result.text && !result.refusal && !result.gaps?.length;
    return `<article class="card ladder-card status-${esc(result.status)}">
      <div class="ladder-card-head">
        <div><h3>${esc(result.language_name)}</h3><div class="microcopy">${esc(lang.period || '')}</div></div>
        <span class="pill ladder-status">${esc(STATUS_LABELS[result.status] || result.status)}</span>
      </div>
      <div class="ladder-text">${esc(result.text || '—')}</div>
      ${scripts}${refusal}${gaps}
      <div class="microcopy">Confidence ${esc(Math.round((result.confidence || 0) * 100))}% · ${esc(lang.family || '')}</div>
      <div class="button-row wrap">
        ${reusable ? `<button type="button" class="secondary" data-reuse="${esc(id)}">Translate from here</button>` : ''}
        ${result.text ? `<button type="button" class="secondary" data-copy="${esc(id)}">Copy</button>` : ''}
        ${(id === 'english' || id === 'swahili') && result.text ? `<button type="button" class="secondary" data-speak="${esc(id)}">Read aloud</button>` : ''}
      </div>
      ${notes}
    </article>`;
  }).join('');
}

async function translate() {
  const text = $('#ladderInput').value.trim();
  if (!text) return toast('Type a sentence or word first.');
  const card = $('#ladderCard');
  setBusy(card, true);
  $('#ladderTranslateBtn').disabled = true;
  try {
    const target = $('#ladderTarget').value;
    const data = await post('/api/ancient/translate', {text, source: $('#ladderSource').value, targets: target === 'all' ? [] : [target]});
    state.last = data;
    renderMeaning(data);
    renderResults(data);
    $('#ladderSwapBtn').disabled = !(data.ok && target !== 'all' && data.results[target]?.text);
  } catch (error) {
    toast(error.message);
  } finally {
    setBusy(card, false);
    $('#ladderTranslateBtn').disabled = false;
  }
}

function reuse(id) {
  const result = state.last?.results?.[id];
  if (!result?.text) return;
  $('#ladderSource').value = id;
  $('#ladderTarget').value = state.last.source_language;
  $('#ladderInput').value = result.text;
  translate();
  $('#ladderInput').scrollIntoView({behavior: 'smooth', block: 'center'});
}

// ------------------------------------------------------------------ quiz
function renderQuestion() {
  const quiz = state.quiz;
  const body = $('#ladderQuizBody');
  if (!quiz) return;
  if (quiz.index >= quiz.questions.length) {
    body.innerHTML = `<div class="quiz-question"><p class="quiz-score">You scored ${quiz.score} of ${quiz.questions.length} in ${esc(quiz.language_name)}.</p>
      <p class="microcopy">${esc(quiz.note || '')}</p><div class="button-row"><button type="button" id="ladderQuizAgain">Another round</button></div></div>`;
    return;
  }
  const q = quiz.questions[quiz.index];
  const ask = {meaning: 'What does this mean?', form: `How do you write this in ${quiz.language_name}?`, sentence: 'What does this sentence say?'}[q.kind];
  const scripts = Object.entries(q.scripts || {}).filter(([, v]) => v).slice(0, 2).map(([name, value]) => scriptBlock(name, value)).join('');
  body.innerHTML = `<div class="quiz-question">
    <div class="microcopy">Question ${quiz.index + 1} of ${quiz.questions.length} · score ${quiz.score}</div>
    <div class="microcopy">${esc(ask)}</div>
    <div class="quiz-prompt" dir="auto">${esc(q.prompt_text)}</div>${scripts}
    <div class="quiz-choices">${q.choices.map((c, i) => `<button type="button" data-choice="${i}" dir="auto">${esc(c)}</button>`).join('')}</div>
    <div class="quiz-feedback microcopy" aria-live="polite"></div></div>`;
}

async function answerQuestion(button) {
  const quiz = state.quiz;
  const q = quiz.questions[quiz.index];
  if (q.answered) return;
  q.answered = true;
  const chosen = q.choices[Number(button.dataset.choice)];
  const right = chosen === q.answer;
  if (right) quiz.score += 1;
  $$q('#ladderQuizBody .quiz-choices button').forEach(b => {
    const text = q.choices[Number(b.dataset.choice)];
    if (text === q.answer) b.classList.add('right'); else if (b === button) b.classList.add('wrong');
    b.disabled = true;
  });
  const notes = (q.notes || []).length ? ` ${q.notes.join(' ')}` : '';
  $('#ladderQuizBody .quiz-feedback').innerHTML = `${right ? 'Correct.' : `Not quite. The answer is “${esc(q.answer)}”.`}${esc(notes)}
    <div class="button-row"><button type="button" id="ladderQuizNext">${quiz.index + 1 < quiz.questions.length ? 'Next question' : 'See my score'}</button></div>`;
  if (appState.user) {
    try { await post('/api/progress', {learner: appState.user.username, item_type: `ladder-quiz-${quiz.language}`, item_id: String(q.id), score: right ? 1 : 0}); } catch { /* progress is optional */ }
  }
}

function $$q(selector) { return Array.from(document.querySelectorAll(selector)); }

async function startQuiz() {
  const params = new URLSearchParams({language: $('#ladderQuizLanguage').value, explain: $('#ladderQuizExplain').value, mode: $('#ladderQuizMode').value, count: '10'});
  try {
    const data = await get(`/api/ancient/quiz?${params}`);
    state.quiz = {...data, index: 0, score: 0};
    renderQuestion();
  } catch (error) {
    toast(error.message);
  }
}

export async function initLadder() {
  try {
    const data = await get('/api/ancient/languages');
    state.languages = data.languages;
    state.modern = data.modern_languages || [];
    state.mt = Boolean(data.machine_translation_available);
    const c = data.coverage.concepts;
    $('#ladderCoverage').textContent = `${c.nouns} nouns, ${c.verbs} verbs and ${c.adjectives} adjectives, each aligned across ${state.languages.length} languages, in past and present tense for every person, positive, negative and as questions.`;
  } catch (error) {
    toast(`Ancient ladder unavailable: ${error.message}`);
    return;
  }
  fillSelects();
  renderExamples();
  $('#ladderTranslateBtn').addEventListener('click', translate);
  $('#ladderInput').addEventListener('keydown', event => {
    if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) translate();
  });
  $('#ladderSwapBtn').addEventListener('click', () => reuse($('#ladderTarget').value));
  $('#ladderQuizStart').addEventListener('click', startQuiz);
  $('#ladderQuizBody').addEventListener('click', event => {
    const button = event.target.closest('button');
    if (!button) return;
    if (button.dataset.choice !== undefined) answerQuestion(button);
    if (button.id === 'ladderQuizNext') { state.quiz.index += 1; renderQuestion(); }
    if (button.id === 'ladderQuizAgain') startQuiz();
  });
  $('#ladderResults').addEventListener('click', async event => {
    const button = event.target.closest('button');
    if (!button) return;
    if (button.dataset.reuse) reuse(button.dataset.reuse);
    if (button.dataset.copy) {
      const result = state.last.results[button.dataset.copy];
      const text = [result.text, ...Object.values(result.scripts || {})].filter(Boolean).join('\n');
      try { await navigator.clipboard.writeText(text); toast('Copied.'); } catch { toast('Copy is not available in this browser.'); }
    }
    if (button.dataset.speak) {
      if (!speak(state.last.results[button.dataset.speak].text, button.dataset.speak)) toast('Speech synthesis is not available on this device.');
    }
  });
}
