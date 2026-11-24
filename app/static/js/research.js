import {$, esc, toast} from './core.js';
import {get} from './api.js';

const q = (url, params) => `${url}?${new URLSearchParams(params)}`;

function safeSvg(markup) {
  const doc = new DOMParser().parseFromString(markup, 'image/svg+xml');
  const svg = doc.documentElement;
  if (svg.nodeName !== 'svg') return null;
  for (const el of svg.querySelectorAll('script,foreignObject')) el.remove();
  for (const el of [svg, ...svg.querySelectorAll('*')]) {
    for (const attr of [...el.attributes]) if (/^on/i.test(attr.name) || /javascript:/i.test(attr.value)) el.removeAttribute(attr.name);
  }
  return document.importNode(svg, true);
}

function signCard(s) {
  const values = (s.values || []).join(', ') || '—';
  const roles = (s.functions || []).map(f => f.role + (f.detail ? ` (${f.detail})` : '')).join('; ') || '—';
  return `<div><span class="glyph big">${esc(s.glyph)}</span> <strong>${esc(s.gardiner || s.unikemet_code)}</strong> · ${esc(s.unicode_name)}</div>
    <div>${esc(s.description || '')}</div><div><strong>Values:</strong> ${esc(values)}</div><div><strong>Functions:</strong> ${esc(roles)}</div>
    <div class="muted">${esc(s.catalog || '')} · Unikemet ${esc(s.unikemet_code || '')}${s.hieroglyphica ? ' · HG ' + esc(s.hieroglyphica) : ''}</div>`;
}

async function lookupSign() {
  const out = $('#signResult');
  try {
    const r = await get(q('/api/signs/lookup', {q: $('#signQuery').value.trim()}));
    if (r.sign) {
      const variants = r.variants.length ? `<div><strong>Variants:</strong> <span class="glyph">${r.variants.map(v => esc(v.glyph)).join(' ')}</span></div>` : '';
      out.innerHTML = signCard(r.sign) + variants;
    } else if (r.by_value.length || r.search.length) {
      const list = [...r.by_value, ...r.search].slice(0, 24);
      out.innerHTML = `<div>${list.length} signs:</div><div>${list.map(s => `<span title="${esc(s.description || '')}"><span class="glyph">${esc(s.glyph)}</span> ${esc(s.gardiner || s.unikemet_code)}</span>`).join(' · ')}</div>`;
    } else out.textContent = 'No sign found in the Unikemet catalog.';
  } catch (e) { out.textContent = e.message; }
}

async function renderQuadrat() {
  const box = $('#quadratSvg'), info = $('#quadratInfo');
  try {
    const r = await get(q('/api/quadrat', {text: $('#quadratInput').value, direction: $('#quadratDir').value, size: 56}));
    box.replaceChildren();
    const svg = safeSvg(r.svg);
    if (svg) box.append(svg);
    const missing = r.signs_without_font_glyph?.length ? `\nNo font glyph (Extended-A): ${r.signs_without_font_glyph.join(' ')}` : '';
    info.innerHTML = `<div>${r.sign_count} signs · Unicode: <span class="glyph">${esc(r.unicode)}</span></div><div>MdC: ${esc(r.mdc)}</div>${missing ? `<div>${esc(missing.trim())}</div>` : ''}`;
  } catch (e) { box.replaceChildren(); info.textContent = e.message; }
}

function pron(p) { return p ? `${esc(p.ipa)} (say “${esc(p.say)}”)` : ''; }

async function readCoptic() {
  const out = $('#copticOutput');
  try {
    const r = await get(q('/api/coptic/read', {text: $('#copticInput').value}));
    out.innerHTML = (r.words || []).map(w => `<div><strong>${esc(w.written)}</strong> · ${esc(w.transliteration)} · ${pron(w.pronunciation)}<br>
      ${w.analysis?.prefix ? `<em>${esc(w.analysis.prefix)}</em> = ${esc(w.analysis.prefix_gloss)} + ` : ''}${esc(w.gloss || (w.known ? '' : 'not in the lexicon'))}</div>`).join('') || 'No Coptic text.';
  } catch (e) { out.textContent = e.message; }
}

async function vocalize() {
  const out = $('#copticOutput');
  try {
    const r = await get(q('/api/coptic/vocalization', {egyptian: $('#vocalInput').value.trim()}));
    if (!r.result) { out.textContent = r.message; return; }
    const c = r.result.coptic;
    out.innerHTML = `<div><strong>${esc(r.result.egyptian)}</strong> “${esc(r.result.meaning)}” → <strong>${esc(c.lemma)}</strong> ${esc(c.transliteration)} · ${pron(c.pronunciation)}</div>
      <div class="muted">Confidence: ${esc(r.result.confidence)} · ${esc(c.senses?.[0]?.bibl || '')}</div><div class="muted">${esc(r.result.note)}</div>`;
  } catch (e) { out.textContent = e.message; }
}

async function restore() {
  const out = $('#restoreOutput');
  try {
    const r = await get(q('/api/restoration', {text: $('#restoreInput').value}));
    if (!r.gaps?.length) { out.textContent = 'No gaps marked. Use [...] for a lost passage.'; return; }
    out.innerHTML = r.gaps.map((g, i) => `<div><strong>Gap ${i + 1}</strong> (${esc(g.kind)}, entropy ${g.entropy_bits} bits)</div>
      <div>${g.candidates.map(c => `${esc(c.text)} <strong>${Math.round(c.probability * 100)}%</strong> <span class="muted">${esc(c.evidence)}</span>`).join('<br>')}<br><span class="muted">anything else: ${Math.round((g.other || 0) * 100)}%</span></div>`).join('')
      + (r.note ? `<div class="muted">${esc(r.note)}</div>` : '');
  } catch (e) { out.textContent = e.message; }
}

async function checkPeriod() {
  const out = $('#periodOutput');
  const params = {text: $('#periodInput').value};
  if ($('#periodStage').value) params.period = $('#periodStage').value;
  try {
    const r = await get(q('/api/grammar/periods', params));
    const feats = r.features.map(f => `<div>• ${esc(f.label)}: <em>${esc(f.matches.join(', '))}</em><br><span class="muted">${esc(f.reference)}</span></div>`).join('') || '<div>No period-diagnostic features found.</div>';
    const anach = (r.anachronisms || []).map(a => `<div><strong>Anachronism:</strong> ${esc(a.label)} belongs to ${esc(a.belongs_to.join(', '))}</div>`).join('');
    out.innerHTML = feats + `<div><strong>Consistent with:</strong> ${esc((r.consistent_stage_names || []).join('; ') || 'any stage')}</div>` + anach;
  } catch (e) { out.textContent = e.message; }
}

async function searchCorpus() {
  const out = $('#corpusOutput');
  try {
    const r = await get(q('/api/corpus/search', {q: $('#corpusQuery').value, limit: 12}));
    out.innerHTML = r.results.map(l => `<div><strong>${esc(l.lemma)}</strong> <span class="muted">${esc(l.stage || '')} · ${esc(l.pos || '')} · ${esc(l.source)} (${esc(l.status)})${l.dates?.label ? ' · ' + esc(l.dates.label) : ''}</span><br>
      ${esc((l.glosses?.en || []).slice(0, 4).join('; '))}</div>`).join('') || 'No lemma found.';
  } catch (e) { out.textContent = e.message; }
}

export function initResearch() {
  const bind = (id, fn) => $(id)?.addEventListener('click', () => fn().catch(e => toast(e.message)));
  bind('#signLookupBtn', lookupSign);
  bind('#quadratBtn', renderQuadrat);
  bind('#copticBtn', readCoptic);
  bind('#vocalBtn', vocalize);
  bind('#restoreBtn', restore);
  bind('#periodBtn', checkPeriod);
  bind('#corpusBtn', searchCorpus);
}
