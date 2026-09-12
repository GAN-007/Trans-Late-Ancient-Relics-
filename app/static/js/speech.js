export const SpeechRecognitionCtor = window.SpeechRecognition || window.webkitSpeechRecognition || null;

export function speechRecognitionSupported() {
  return Boolean(SpeechRecognitionCtor);
}

export function createRecognizer({language='english', onInterim, onFinal, onStatus, onError, onEnd}) {
  if (!SpeechRecognitionCtor) return null;
  const recognition = new SpeechRecognitionCtor();
  recognition.lang = language === 'swahili' ? 'sw-KE' : 'en-US';
  recognition.continuous = true;
  recognition.interimResults = true;
  recognition.maxAlternatives = 3;
  recognition.onstart = () => onStatus?.('Listening…');
  recognition.onspeechstart = () => onStatus?.('Speech detected…');
  recognition.onend = () => { onStatus?.('Microphone stopped.'); onEnd?.(); };
  recognition.onerror = event => {
    onStatus?.(`Speech recognition: ${event.error}`);
    onError?.(event);
  };
  recognition.onresult = event => {
    let interim = '';
    let finalText = '';
    for (let i = event.resultIndex; i < event.results.length; i += 1) {
      const transcript = event.results[i][0].transcript;
      if (event.results[i].isFinal) finalText += transcript + ' ';
      else interim += transcript;
    }
    if (interim) onInterim?.(interim.trim());
    if (finalText) onFinal?.(finalText.trim());
  };
  return recognition;
}

function languageCode(language) {
  if (language === 'swahili') return 'sw-KE';
  return 'en-US';
}

export function speak(text, language='english') {
  if (!('speechSynthesis' in window) || !text?.trim()) return false;
  window.speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(text.trim());
  utterance.lang = languageCode(language);
  const voices = window.speechSynthesis.getVoices();
  const base = utterance.lang.split('-')[0].toLowerCase();
  const voice = voices.find(v => v.lang.toLowerCase() === utterance.lang.toLowerCase()) ||
                voices.find(v => v.lang.toLowerCase().startsWith(base));
  if (voice) utterance.voice = voice;
  utterance.rate = 0.92;
  window.speechSynthesis.speak(utterance);
  return true;
}

export function stopSpeaking() {
  if ('speechSynthesis' in window) window.speechSynthesis.cancel();
}
