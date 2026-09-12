import {$,esc,runTranslation,toast,translationSpeakable} from './core.js';
import {createRecognizer,speak} from './speech.js';

let recognizer=null,listening=false,finalSpeech='',conversationSocket=null,pendingUtterances=[];

function wsUrl(path){return `${location.protocol==='https:'?'wss:':'ws:'}//${location.host}${path}`;}

function render(result){
  const d=result.deterministic||result,g=d.hieroglyphs||'',preferred=result.ai?.review?.preferred_interpretation?.text||d.literal_gloss||d.translations?.[0]||d.transliteration||d.message||'No secure result.';
  const questions=result.clarification_questions||[];
  $('#speechResult').innerHTML=`${g?`<div class="glyph hero-glyph">${esc(g)}</div>`:''}<div class="result-primary">${esc(preferred)}</div>${result.pronunciation?`<div class="pronunciation-box">Classroom reading: ${esc(result.pronunciation.classroom_reading)}${result.pronunciation.classroom_ipa?` • IPA of classroom reading: /${esc(result.pronunciation.classroom_ipa)}/`:''}</div>`:''}${questions.length?`<div class="warning"><strong>Meaning still needs context:</strong><br>${questions.map(esc).join('<br>')}</div>`:''}`;
}

function afterResult(result,live=false){
  render(result);
  if($('#autoSpeak').checked){const item=translationSpeakable(result);if(item)speak(item.text,item.language);}
  if(live)$('#speechStatus').textContent='Live translation complete. Listening continues with short-term conversation context.';
}

async function translateHttp(text,live=false){
  if(!text?.trim())return;$('#speechTranslateBtn').disabled=true;if(live)$('#speechStatus').textContent='Live translating completed utterance…';
  try{const result=await runTranslation({text:text.trim(),source:$('#speechSource').value,target:$('#speechTarget').value,context:$('#speechContext').value,register:'natural',useAI:true});afterResult(result,live);}
  catch(e){toast(e.message);}finally{$('#speechTranslateBtn').disabled=false;}
}

function closeConversationSocket(){if(conversationSocket){try{conversationSocket.close(1000,'reset');}catch{}conversationSocket=null;}pendingUtterances=[];}

function connectConversation(){
  if(conversationSocket&&[WebSocket.OPEN,WebSocket.CONNECTING].includes(conversationSocket.readyState))return conversationSocket;
  const socket=new WebSocket(wsUrl('/ws/conversation'));conversationSocket=socket;
  socket.addEventListener('open',()=>{
    if(conversationSocket!==socket)return;
    $('#speechStatus').textContent='Live conversation channel connected.';
    for(const message of pendingUtterances.splice(0))socket.send(JSON.stringify(message));
  });
  socket.addEventListener('message',event=>{
    if(conversationSocket!==socket)return;
    try{const payload=JSON.parse(event.data);if(payload.type==='translation')afterResult(payload.result,true);else if(payload.type==='error')$('#speechStatus').textContent=payload.error||'Conversation translation error.';}
    catch(error){$('#speechStatus').textContent=`Conversation message error: ${error.message}`;}
  });
  socket.addEventListener('close',()=>{if(conversationSocket===socket){conversationSocket=null;$('#speechStatus').textContent='Live conversation channel closed. HTTP translation remains available.';}});
  socket.addEventListener('error',()=>{$('#speechStatus').textContent='Live conversation WebSocket unavailable; using request/response fallback.';});
  return socket;
}

function liveTranslate(text){
  const message={type:'utterance',text:text.trim(),source:$('#speechSource').value,target:$('#speechTarget').value,context:$('#speechContext').value,register:'natural',use_ai:true,max_alternatives:5};
  const socket=connectConversation();
  if(socket.readyState===WebSocket.OPEN){socket.send(JSON.stringify(message));$('#speechStatus').textContent='Utterance sent over live conversation channel…';}
  else{pendingUtterances.push(message);setTimeout(()=>{if(!conversationSocket||conversationSocket.readyState!==WebSocket.OPEN){const pending=pendingUtterances.splice(0);for(const item of pending)translateHttp(item.text,true);}},1500);}
}

function configure(){
  if(recognizer&&listening){try{recognizer.stop();}catch{}}
  closeConversationSocket();
  recognizer=createRecognizer({language:$('#speechSource').value,onInterim:t=>$('#speechStatus').textContent=`Hearing: ${t}`,onFinal:t=>{finalSpeech=`${finalSpeech} ${t}`.trim();$('#speechTranscript').value=finalSpeech;$('#speechStatus').textContent='Speech captured. Continue speaking or translate.';if($('#liveSpeechTranslate').checked&&t.trim())liveTranslate(t.trim());},onStatus:s=>$('#speechStatus').textContent=s,onError:()=>stopUI(),onEnd:()=>{if(listening)setTimeout(()=>{if(!listening||!recognizer)return;try{recognizer.start();}catch{stopUI();}},250);}});
}

function stopUI(){listening=false;$('#listenBtn').classList.remove('listening');$('#listenBtn').setAttribute('aria-pressed','false');$('#listenBtn span').textContent='Start listening';}

export function initTalk(){
  configure();
  $('#speechSource').addEventListener('change',configure);
  $('#speechTarget').addEventListener('change',closeConversationSocket);
  $('#listenBtn').addEventListener('click',()=>{if(!recognizer)return toast('Live browser speech recognition is unavailable. Use OS dictation or type the transcript.');if(listening){recognizer.stop();stopUI();return;}finalSpeech=$('#speechTranscript').value.trim();try{recognizer.start();listening=true;$('#listenBtn').classList.add('listening');$('#listenBtn').setAttribute('aria-pressed','true');$('#listenBtn span').textContent='Stop listening';}catch(e){toast(e.message);}});
  $('#speechTranslateBtn').addEventListener('click',()=>{const text=$('#speechTranscript').value.trim();if(!text)return toast('Say or type something first.');translateHttp(text,false);});
  $('#liveSpeechTranslate').addEventListener('change',event=>{if(!event.target.checked)closeConversationSocket();});
  window.addEventListener('beforeunload',closeConversationSocket);
}
