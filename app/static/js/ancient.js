import {get, post} from './api.js';
import {$, esc, setBusy, toast} from './core.js';
import {speak} from './speech.js';

const EXAMPLES = [
  ['english', 'The truth, I have put my trust in'],
  ['english', 'The king made a great house'],
  ['swahili', 'Mimi ni mtumishi'],
  ['old_latin', 'ueritatei credidei'],
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
};

const state = {languages: [], last: null};

function languageName(id) {
  return state.languages.find(lang => lang.id === id)?.name || id;
}

function fillSelects() {
  const options = state.languages.map(lang => `<option value="${esc(lang.id)}">${esc(lang.name)}</option>`).join('');
  $('#ladderSource').innerHTML = options;
  $('#ladderTarget').innerHTML = '<option value="all">Every language</option>' + options;
  $('#ladderSource').value = 'english';
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
  if (meaning.kind === 'clause') {
    const object = meaning.object ? ` → ${meaning.object.adj ? meaning.object.adj + ' ' : ''}${meaning.object.noun}` : '';
    return `${who} · ${meaning.verb} (${meaning.tense})${object}`;
  }
  if (meaning.kind === 'identity') return `${who} = ${meaning.predicate.adj ? meaning.predicate.adj + ' ' : ''}${meaning.predicate.noun}`;
  if (meaning.kind === 'np') return `${meaning.np.adj ? meaning.np.adj + ' ' : ''}${meaning.np.noun}`;
  return `${meaning.word_kind}: ${meaning.concept}`;
}

function renderMeaning(data) {
  $('#ladderEmpty').hidden = true;
  const box = $('#ladderMeaning');
  box.hidden = false;
  const parse = data.parse || {};
  const list = (title, items) => items?.length ? `<div class="warning"><strong>${esc(title)}</strong> ${esc(items.join(' '))}</div>` : '';
  box.innerHTML = data.ok
    ? `<div class="result-primary">${esc(describeMeaning(data.meaning))}</div>
       <div class="microcopy">Read from ${esc(languageName(data.source_language))}: “${esc(data.source)}”</div>
       ${list('Not recognized:', parse.unknown_words)}
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
    const lang = state.languages.find(item => item.id === id) || {};
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

export async function initLadder() {
  try {
    const data = await get('/api/ancient/languages');
    state.languages = data.languages;
    const c = data.coverage.concepts;
    $('#ladderCoverage').textContent = `${c.nouns} nouns, ${c.verbs} verbs and ${c.adjectives} adjectives, each aligned across ${state.languages.length} languages, in past and present tense for every person.`;
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
