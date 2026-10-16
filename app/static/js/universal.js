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
  const speechButton = $('#universalSpeakBtn');
  const downloadButton = $('#universalDownloadBtn');
  const micButton = $('#universalMicBtn');
  button.addEventListener('click', async () => {
    button.disabled = true;
    copy.disabled = true;
    speechButton.disabled = true;
    downloadButton.disabled = true;
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
      speechButton.disabled = !lastOutput || !('speechSynthesis' in window);
      downloadButton.disabled = !lastOutput;
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
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  micButton.disabled = !SpeechRecognition;
  micButton.title = SpeechRecognition
    ? 'Browser dictation; language availability depends on browser and device'
    : 'Speech recognition is not supported by this browser';
  if (SpeechRecognition) {
    micButton.addEventListener('click', () => {
      const recorder = new SpeechRecognition();
      recorder.lang = $('#universalSource').value.trim() === 'auto'
        ? navigator.language : $('#universalSource').value.trim();
      recorder.interimResults = false;
      recorder.maxAlternatives = 1;
      recorder.onstart = () => { micButton.disabled = true; micButton.textContent = 'Listening…'; };
      recorder.onresult = event => {
        const words = event.results[0][0].transcript;
        const input = $('#universalInput');
        input.value = input.value.trim() ? input.value.trimEnd() + '\n' + words : words;
      };
      recorder.onerror = event => toast('Dictation failed: ' + event.error);
      recorder.onend = () => { micButton.disabled = false; micButton.textContent = 'Dictate'; };
      try { recorder.start(); } catch (error) { micButton.disabled = false; toast(error.message); }
    });
  }
  speechButton.addEventListener('click', () => {
    if (!lastOutput || !('speechSynthesis' in window)) return;
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(lastOutput);
    utterance.lang = $('#universalTarget').value.trim();
    window.speechSynthesis.speak(utterance);
  });
  downloadButton.addEventListener('click', () => {
    if (!lastOutput) return;
    const format = $('#universalFormat').value;
    const mime = format === 'json' ? 'application/json;charset=utf-8'
      : 'text/plain;charset=utf-8';
    const extension = format === 'json' ? 'json' : format === 'srt' ? 'srt' : 'txt';
    const blob = new Blob([lastOutput], {type: mime});
    const url = URL.createObjectURL(blob);
    const element = document.createElement('a');
    element.href = url;
    element.download = 'translated-content.' + extension;
    document.body.appendChild(element);
    element.click();
    element.remove();
    URL.revokeObjectURL(url);
  });
  refreshProviderStatus();
}
