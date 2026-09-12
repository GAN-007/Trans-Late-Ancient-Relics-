import {post} from './api.js';
import {CameraController} from './camera.js';
import {$,esc,state,toast} from './core.js';
import {speak} from './speech.js';

let camera=null,busy=false,liveTimer=null;
function buttons(on){$('#cameraStartBtn').disabled=on;$('#cameraCaptureBtn').disabled=!on;$('#cameraSwitchBtn').disabled=!on;$('#cameraLiveBtn').disabled=!on;$('#cameraStopBtn').disabled=!on;$('#cameraPlaceholder').hidden=on;}
function stopLive(){if(liveTimer)clearInterval(liveTimer);liveTimer=null;$('#cameraLiveBtn').textContent='Start live scan';}
function render(result){
  state.lastLens=result;
  if(!result.ok){$('#lensResult').innerHTML=`<div class="warning"><strong>Vision AI not active.</strong><br>${esc(result.message||'')}<br><span class="microcopy">The camera transport is ready; configure a multimodal provider for inscription recognition.</span></div>`;$('#speakLensBtn').hidden=true;$('#cameraOverlay').classList.remove('show');return;}
  const a=result.analysis||{},translations=a.translation_candidates||[],translits=a.transliteration_candidates||[],signs=a.sign_candidates||[];
  $('#lensResult').innerHTML=`<div class="result-primary"><strong>Script:</strong> ${esc(a.script_detected||'uncertain')} ${a.reading_direction?`• ${esc(a.reading_direction)}`:''}</div>${translits.length?`<h3>Transliteration candidates</h3>${translits.map(x=>`<div class="alternative-card"><strong>${esc(x.text)}</strong> <span class="pill">${Math.round((x.confidence||0)*100)}%</span><div>${esc(x.rationale||'')}</div></div>`).join('')}`:''}${translations.length?`<h3>Translation candidates</h3>${translations.map(x=>`<div class="alternative-card"><strong>${esc(x.text)}</strong> <span class="pill">${Math.round((x.confidence||0)*100)}%</span><div>${esc(x.rationale||'')}</div></div>`).join('')}`:''}${signs.length?`<h3>Possible signs</h3><div class="dict-top">${signs.map(x=>`<span class="pill glyph">${esc(x.unicode||'')} ${esc(x.gardiner||'?')} ${esc(x.value||'')}</span>`).join('')}</div>`:''}${(a.uncertainties||[]).length?`<div class="warning"><strong>Uncertainties:</strong><br>${a.uncertainties.map(esc).join('<br>')}</div>`:''}<div class="microcopy">Overall confidence: ${Math.round((a.overall_confidence||0)*100)}% • ${esc(result.privacy||'')}</div>`;
  $('#speakLensBtn').hidden=!translations.length;const overlay=translations[0]?.text||translits[0]?.text||'';$('#cameraOverlay').textContent=overlay;$('#cameraOverlay').classList.toggle('show',Boolean(overlay));
}
async function analyze(image,label='frame'){if(busy)return;busy=true;$('#cameraCaptureBtn').disabled=true;try{$('#cameraStatus').textContent=`Analyzing ${label}…`;const result=await post('/api/vision/analyze',{image_data_url:image,target_language:$('#lensTargetLang').value,context:$('#lensContext').value,detail:$('#lensDetail').value});render(result);$('#cameraStatus').textContent=result.ok?`${label} analyzed • ${(result.image.bytes/1024).toFixed(0)} KB • not stored`:result.message;}catch(e){$('#cameraStatus').textContent=e.message;$('#lensResult').innerHTML=`<div class="warning">${esc(e.message)}</div>`;}finally{busy=false;$('#cameraCaptureBtn').disabled=!camera?.stream;}}
async function analyzeFrame(){if(!camera?.stream)return;const image=camera.capture({maxWidth:$('#lensDetail').value==='low'?900:1280,quality:.76});await analyze(image,'camera frame');}
export function initLens(){
  camera=new CameraController($('#cameraVideo'),$('#cameraCanvas'));
  $('#cameraStartBtn').addEventListener('click',async()=>{try{if(!window.isSecureContext)throw new Error('Camera access requires HTTPS or localhost.');await camera.start();buttons(true);$('#cameraStatus').textContent='Camera active. Frames are not stored by the app.';$('.camera-card').classList.add('live');}catch(e){$('#cameraStatus').textContent=e.message;toast(e.message);}});
  $('#cameraStopBtn').addEventListener('click',()=>{stopLive();camera.stop();buttons(false);$('.camera-card').classList.remove('live');$('#cameraStatus').textContent='Camera stopped.';});
  $('#cameraCaptureBtn').addEventListener('click',analyzeFrame);
  $('#cameraSwitchBtn').addEventListener('click',async()=>{if(!camera.stream)return;stopLive();try{await camera.switchCamera();$('#cameraStatus').textContent=`Camera switched to ${camera.facingMode==='environment'?'rear/environment':'front/user'} preference.`;}catch(e){$('#cameraStatus').textContent=`Could not switch camera: ${e.message}`;}});
  $('#cameraLiveBtn').addEventListener('click',()=>{if(liveTimer){stopLive();$('#cameraStatus').textContent='Live scan paused.';return;}$('#cameraLiveBtn').textContent='Pause live scan';analyzeFrame();liveTimer=setInterval(analyzeFrame,2600);$('#cameraStatus').textContent='Live scan active. One frame is analyzed about every 2.6 seconds.';});
  $('#imageUpload').addEventListener('change',event=>{const file=event.target.files?.[0];if(!file)return;if(file.size>5*1024*1024){toast('Image must be 5 MB or smaller.');event.target.value='';return;}const reader=new FileReader();reader.onload=()=>analyze(String(reader.result),'uploaded image');reader.onerror=()=>toast('Could not read the selected image.');reader.readAsDataURL(file);});
  $('#speakLensBtn').addEventListener('click',()=>{const c=state.lastLens?.analysis?.translation_candidates?.[0];if(c)speak(c.text,$('#lensTargetLang').value);});
  document.addEventListener('visibilitychange',()=>{if(document.hidden&&camera?.stream){stopLive();$('#cameraStatus').textContent='Live scan paused while the app is in the background.';}});
}
