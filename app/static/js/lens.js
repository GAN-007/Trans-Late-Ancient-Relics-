import {post} from './api.js';
import {CameraController} from './camera.js';
import {$,esc,state,toast,hasPermission} from './core.js';
import {speak} from './speech.js';

let camera=null,busy=false,liveTimer=null,liveSocket=null,liveInFlight=false,lastFrameDataUrl=null;

function buttons(on){
  $('#cameraStartBtn').disabled=on;
  $('#cameraCaptureBtn').disabled=!on;
  $('#cameraSwitchBtn').disabled=!on;
  $('#cameraLiveBtn').disabled=!on;
  $('#cameraStopBtn').disabled=!on;
  $('#cameraPlaceholder').hidden=on;
}

function wsUrl(path){return `${location.protocol==='https:'?'wss:':'ws:'}//${location.host}${path}`;}

function stopLive(){
  if(liveTimer)clearTimeout(liveTimer);
  liveTimer=null;liveInFlight=false;
  if(liveSocket){try{liveSocket.close(1000,'paused');}catch{}liveSocket=null;}
  $('#cameraLiveBtn').textContent='Start live scan';
}

function correctionPanel(){
  if(!state.user||!hasPermission('vision_correction:create'))return '';
  return `<div class="feedback-box lens-correction-box">
    <strong>Research correction</strong>
    <p class="microcopy">If a sign or meaning is wrong, submit a correction for human review. The current image is NOT included unless you explicitly opt in below.</p>
    <textarea id="lensCorrectionText" rows="2" placeholder="Example: sign 2 should be N35, not N37; reading direction is right-to-left…"></textarea>
    <label class="check-label"><input id="lensStoreImageConsent" type="checkbox"> Include this captured frame for research if the server permits image collection</label>
    <button id="lensCorrectionBtn" class="secondary">Submit correction for review</button>
    <span id="lensCorrectionStatus" class="microcopy"></span>
  </div>`;
}

function bindCorrection(result){
  const button=$('#lensCorrectionBtn');
  if(!button)return;
  button.addEventListener('click',async()=>{
    const correction=$('#lensCorrectionText')?.value?.trim();
    if(!correction)return toast('Describe the correction first.');
    const consent=Boolean($('#lensStoreImageConsent')?.checked);
    button.disabled=true;
    try{
      const saved=await post('/api/vision/corrections',{
        machine_analysis:result.analysis||{},
        expert_correction:{note:correction},
        context:$('#lensContext').value,
        model_version:result.vision?.local?.model_sha256||result.vision?.ai?.model||result.backend||'',
        image_data_url:consent?lastFrameDataUrl:null,
        consent_store_image:consent,
      });
      $('#lensCorrectionStatus').textContent=saved.image_storage_notice||`Correction ${saved.id} queued for review${saved.image_stored?' with consented image':' without stored image'}.`;
      toast('Correction queued for human review.');
    }catch(error){$('#lensCorrectionStatus').textContent=error.message;}
    finally{button.disabled=false;}
  });
}

function render(result){
  state.lastLens=result;
  if(!result.ok){
    $('#lensResult').innerHTML=`<div class="warning"><strong>Vision analysis is not active.</strong><br>${esc(result.message||'')}<br><span class="microcopy">Configure a reviewed local ONNX detector/class map or a multimodal provider.</span></div>`;
    $('#speakLensBtn').hidden=true;$('#cameraOverlay').classList.remove('show');return;
  }
  const a=result.analysis||{},translations=a.translation_candidates||[],translits=a.transliteration_candidates||[],signs=a.sign_candidates||[];
  const evidence=a.evidence_comparison;
  $('#lensResult').innerHTML=`
    <div class="result-primary"><strong>Backend:</strong> ${esc(result.backend||'unknown')} • <strong>Script:</strong> ${esc(a.script_detected||'uncertain')} ${a.reading_direction?`• ${esc(a.reading_direction)}`:''}</div>
    ${translits.length?`<h3>Transliteration candidates</h3>${translits.map(x=>`<div class="alternative-card"><strong>${esc(x.text)}</strong> <span class="pill">${Math.round((x.confidence||0)*100)}%</span><div>${esc(x.rationale||'')}</div></div>`).join('')}`:''}
    ${translations.length?`<h3>Translation candidates</h3>${translations.map(x=>`<div class="alternative-card"><strong>${esc(x.text)}</strong> <span class="pill">${Math.round((x.confidence||0)*100)}%</span><div>${esc(x.rationale||'')}</div></div>`).join('')}`:''}
    ${signs.length?`<h3>Possible signs</h3><div class="dict-top">${signs.map(x=>`<span class="pill glyph">${esc(x.unicode||'')} ${esc(x.gardiner||'?')} ${esc(x.value||'')}</span>`).join('')}</div>`:''}
    ${evidence?.disagreements?.length?`<div class="warning"><strong>Detector/reviewer disagreement:</strong> ${esc(evidence.disagreements.join(', '))}. Treat the reading as unresolved.</div>`:''}
    ${(a.determinatives||[]).length?`<details><summary>Determinative candidates</summary><pre>${esc(JSON.stringify(a.determinatives,null,2))}</pre></details>`:''}
    ${(a.phonetic_complements||[]).length?`<details><summary>Phonetic complement candidates</summary><pre>${esc(JSON.stringify(a.phonetic_complements,null,2))}</pre></details>`:''}
    ${(a.uncertainties||[]).length?`<div class="warning"><strong>Uncertainties:</strong><br>${a.uncertainties.map(esc).join('<br>')}</div>`:''}
    <div class="microcopy">Overall confidence: ${Math.round((a.overall_confidence||0)*100)}% • ${esc(result.privacy||'')}</div>
    ${correctionPanel()}`;
  $('#speakLensBtn').hidden=!translations.length;
  const overlay=translations[0]?.text||translits[0]?.text||'';
  $('#cameraOverlay').textContent=overlay;
  $('#cameraOverlay').classList.toggle('show',Boolean(overlay));
  bindCorrection(result);
}

async function analyze(image,label='frame'){
  if(busy)return;busy=true;lastFrameDataUrl=image;$('#cameraCaptureBtn').disabled=true;
  try{
    $('#cameraStatus').textContent=`Analyzing ${label}…`;
    const result=await post('/api/vision/analyze',{image_data_url:image,target_language:$('#lensTargetLang').value,context:$('#lensContext').value,detail:$('#lensDetail').value});
    render(result);
    $('#cameraStatus').textContent=result.ok?`${label} analyzed via ${result.backend||'vision'} • ${(result.image.bytes/1024).toFixed(0)} KB • not stored`:result.message;
  }catch(e){$('#cameraStatus').textContent=e.message;$('#lensResult').innerHTML=`<div class="warning">${esc(e.message)}</div>`;}
  finally{busy=false;$('#cameraCaptureBtn').disabled=!camera?.stream;}
}

async function analyzeFrame(){if(!camera?.stream)return;const image=camera.capture({maxWidth:$('#lensDetail').value==='low'?900:1280,quality:.76});await analyze(image,'camera frame');}

function scheduleLive(delay=1500){
  if(!liveSocket||liveSocket.readyState!==WebSocket.OPEN||!camera?.stream)return;
  if(liveTimer)clearTimeout(liveTimer);
  liveTimer=setTimeout(sendLiveFrame,delay);
}

function sendLiveFrame(){
  if(!liveSocket||liveSocket.readyState!==WebSocket.OPEN||liveInFlight||!camera?.stream)return;
  try{
    const image=camera.capture({maxWidth:$('#lensDetail').value==='low'?800:1100,quality:.7});
    lastFrameDataUrl=image;liveInFlight=true;
    liveSocket.send(JSON.stringify({type:'frame',image_data_url:image,target_language:$('#lensTargetLang').value,context:$('#lensContext').value,detail:$('#lensDetail').value}));
    $('#cameraStatus').textContent='Live frame sent. Waiting for analysis before sending the next frame…';
  }catch(error){liveInFlight=false;$('#cameraStatus').textContent=error.message;scheduleLive(2500);}
}

function startLiveSocket(){
  stopLive();
  const socket=new WebSocket(wsUrl('/ws/vision'));liveSocket=socket;
  $('#cameraLiveBtn').textContent='Pause live scan';
  $('#cameraStatus').textContent='Connecting low-latency live analysis…';
  socket.addEventListener('open',()=>{if(liveSocket!==socket)return;$('#cameraStatus').textContent='Live scan connected. Backpressure prevents overlapping frame inference.';sendLiveFrame();});
  socket.addEventListener('message',event=>{
    if(liveSocket!==socket)return;
    liveInFlight=false;
    try{
      const payload=JSON.parse(event.data);
      if(payload.type==='analysis'){
        render(payload.result);$('#cameraStatus').textContent=`Live analysis #${payload.sequence} complete. Frame not stored.`;scheduleLive(1400);
      }else if(payload.type==='error'){
        $('#cameraStatus').textContent=payload.error||'Live analysis error.';scheduleLive(payload.retry?3000:1800);
      }
    }catch(error){$('#cameraStatus').textContent=`Live message error: ${error.message}`;scheduleLive(2500);}
  });
  socket.addEventListener('close',()=>{if(liveSocket!==socket)return;liveSocket=null;liveInFlight=false;if($('#cameraLiveBtn').textContent==='Pause live scan'){$('#cameraStatus').textContent='Live socket closed; switch to capture mode or restart live scan.';$('#cameraLiveBtn').textContent='Start live scan';}});
  socket.addEventListener('error',()=>{$('#cameraStatus').textContent='WebSocket live analysis unavailable. Manual capture remains available.';});
}

export function initLens(){
  camera=new CameraController($('#cameraVideo'),$('#cameraCanvas'));
  $('#cameraStartBtn').addEventListener('click',async()=>{try{if(!window.isSecureContext)throw new Error('Camera access requires HTTPS or localhost.');await camera.start();buttons(true);$('#cameraStatus').textContent='Camera active. Frames are not stored by the app.';$('.camera-card').classList.add('live');}catch(e){$('#cameraStatus').textContent=e.message;toast(e.message);}});
  $('#cameraStopBtn').addEventListener('click',()=>{stopLive();camera.stop();buttons(false);$('.camera-card').classList.remove('live');$('#cameraStatus').textContent='Camera stopped.';});
  $('#cameraCaptureBtn').addEventListener('click',analyzeFrame);
  $('#cameraSwitchBtn').addEventListener('click',async()=>{if(!camera.stream)return;stopLive();try{await camera.switchCamera();$('#cameraStatus').textContent=`Camera switched to ${camera.facingMode==='environment'?'rear/environment':'front/user'} preference.`;}catch(e){$('#cameraStatus').textContent=`Could not switch camera: ${e.message}`;}});
  $('#cameraLiveBtn').addEventListener('click',()=>{if(liveSocket){stopLive();$('#cameraStatus').textContent='Live scan paused.';return;}startLiveSocket();});
  $('#imageUpload').addEventListener('change',event=>{const file=event.target.files?.[0];if(!file)return;if(file.size>5*1024*1024){toast('Image must be 5 MB or smaller.');event.target.value='';return;}const reader=new FileReader();reader.onload=()=>{lastFrameDataUrl=String(reader.result);analyze(lastFrameDataUrl,'uploaded image');};reader.onerror=()=>toast('Could not read the selected image.');reader.readAsDataURL(file);});
  $('#speakLensBtn').addEventListener('click',()=>{const c=state.lastLens?.analysis?.translation_candidates?.[0];if(c)speak(c.text,$('#lensTargetLang').value);});
  document.addEventListener('visibilitychange',()=>{if(document.hidden&&camera?.stream){stopLive();$('#cameraStatus').textContent='Live scan paused while the app is in the background.';}});
}
