import {get, post} from './api.js';
import {$, toast} from './core.js';

let lastOutput = '';

function text(id, value) {
  $(id).textContent = value;
}

async function refreshProviderStatus() {
  try {
    const caps = await get('/api/universal/capabilities');
    const providers = caps.providers || {};
    const available = Object.entries(providers)
      .filter(([, config]) => config.configured)
      .map(([name]) => name);
    text('#universalProviderStatus',
      available.length
        ? 'Configured engines: ' + available.join(', ') + '. Unconfigured engines are not simulated.'
        : 'No modern-language inference engine configured. The Ancient Egyptian tools above still work.');
  } catch (error) {
    text('#universalProviderStatus', 'Could not load provider status: ' + error.message);
  }
}

export function initUniversal() {
  const button = $('#universalTranslateBtn');
  const output = $('#universalOutput');
  const copy = $('#universalCopyBtn');
  button.addEventListener('click', async () => {
    button.disabled = true;
    copy.disabled = true;
    lastOutput = '';
    text('#universalMeta', 'Translating…');
    output.textContent = '';
    try {
      const rawGlossary = $('#universalGlossary').value.trim();
      let glossary = {};
      if (rawGlossary) {
        glossary = JSON.parse(rawGlossary);
        if (!glossary || Array.isArray(glossary) || typeof glossary !== 'object') {
          throw new Error('Glossary must be a JSON object of terms.');
        }
      }
      const result = await post('/api/universal/translate', {
        text: $('#universalInput').value,
        source_language: $('#universalSource').value.trim(),
        target_language: $('#universalTarget').value.trim(),
        provider: $('#universalProvider').value,
        format: $('#universalFormat').value,
        context: $('#universalContext').value,
        glossary,
      });
      lastOutput = result.translation;
      output.textContent = lastOutput;
      text('#universalMeta',
        result.source_language + ' → ' + result.target_language +
        ' • ' + result.provider + ' • ' + result.segments + ' segment(s)');
      copy.disabled = !lastOutput;
    } catch (error) {
      output.textContent = error.message;
      text('#universalMeta', 'Translation unavailable or failed integrity checks.');
      toast(error.message);
    } finally {
      button.disabled = false;
    }
  });
  copy.addEventListener('click', async () => {
    if (!lastOutput) return;
    try {
      await navigator.clipboard.writeText(lastOutput);
      toast('Translation copied.');
    } catch {
      toast('Copy requires clipboard access. Select the output text to copy manually.');
    }
  });
  refreshProviderStatus();
}
