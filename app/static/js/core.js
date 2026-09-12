import {get, post} from './api.js';
import {cameraSupported} from './camera.js';
import {speechRecognitionSupported} from './speech.js';

export const $ = selector => document.querySelector(selector);
export const $$ = selector => [...document.querySelectorAll(selector)];
export const esc = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[char]));
export const state = {user:null,capabilities:null,lastTranslation:null,lastLens:null,feedbackRating:0,userHooks:[]};

export function toast(message){const el=$('#toast');if(!el)return;el.textContent=message;el.classList.add('show');clearTimeout(el._timer);el._timer=setTimeout(()=>el.classList.remove('show'),3200);}
export function setBusy(element,busy){if(element)element.setAttribute('aria-busy',busy?'true':'false');}
export function hasPermission(permission){return Boolean(state.user?.permissions?.includes(permission));}
export function onUserChanged(fn){state.userHooks.push(fn);}

export function setTab(id){$$('#tabs button').forEach(b=>b.classList.toggle('active',b.dataset.tab===id));$$('.tab').forEach(s=>s.classList.toggle('active',s.id===id));history.replaceState(null,'',`#${id}`);window.scrollTo({top:0,behavior:'smooth'});}
export function initTabs(){
  $$('#tabs button').forEach(b=>b.addEventListener('click',()=>setTab(b.dataset.tab)));
  const initial=location.hash.replace('#','');if(initial&&document.getElementById(initial))setTab(initial);
}

function updateConnectivity(){const badge=$('#networkBadge');if(!badge)return;badge.textContent=navigator.onLine?'Online':'Offline shell';badge.className=`status-pill ${navigator.onLine?'ok':'warn'}`;}
function renderDeviceCapabilities(){
  const host=$('#deviceCapabilities');if(!host)return;
  const items=[
    ['Camera',cameraSupported(),cameraSupported()?'Live rear/front camera supported':'Use a browser with getUserMedia'],
    ['Speech input',speechRecognitionSupported(),speechRecognitionSupported()?'Browser speech recognition available':'Type or use OS dictation'],
    ['Speech output','speechSynthesis' in window,'Reads translations and classroom pronunciation'],
    ['PWA / offline shell','serviceWorker' in navigator,'Static interface can be cached; server features still require connectivity'],
    ['Secure context',window.isSecureContext,window.isSecureContext?'Camera/mic permissions can be requested':'Use HTTPS or localhost'],
    ['Touch device',navigator.maxTouchPoints>0,navigator.maxTouchPoints>0?`${navigator.maxTouchPoints} touch point(s)`:'Pointer/keyboard interface'],
  ];
  host.innerHTML=items.map(([name,ok,note])=>`<div class="capability"><strong>${ok?'✓':'–'} ${esc(name)}</strong><small>${esc(note)}</small></div>`).join('');
}
export async function loadCapabilities(){
  updateConnectivity();window.addEventListener('online',updateConnectivity);window.addEventListener('offline',updateConnectivity);
  try{state.capabilities=await get('/api/capabilities');const ai=$('#aiBadge');ai.textContent=state.capabilities.ai.configured?`AI ${state.capabilities.ai.model}`:'AI optional';ai.className=`status-pill ${state.capabilities.ai.configured?'ok':'warn'}`;}catch{const ai=$('#aiBadge');ai.textContent='AI status unavailable';ai.className='status-pill bad';}
  const cam=$('#cameraBadge');cam.textContent=cameraSupported()?'Camera ready':'No camera API';cam.className=`status-pill ${cameraSupported()?'ok':'bad'}`;
  const mic=$('#micBadge');mic.textContent=speechRecognitionSupported()?'Speech input ready':'Speech input limited';mic.className=`status-pill ${speechRecognitionSupported()?'ok':'warn'}`;
  renderDeviceCapabilities();
}

export async function refreshUser(){
  const data=await get('/api/auth/me');state.user=data.user;
  const badge=$('#userBadge');if(badge)badge.textContent=state.user?`${state.user.display_name} • ${state.user.role}`:'Guest';
  if($('#signedOutPanel'))$('#signedOutPanel').hidden=Boolean(state.user);
  if($('#signedInPanel'))$('#signedInPanel').hidden=!state.user;
  if($('#accountIdentity'))$('#accountIdentity').textContent=state.user?`${state.user.display_name} (@${state.user.username}) — ${state.user.role}`:'';
  state.userHooks.forEach(fn=>{try{fn(state.user);}catch{}});
  return state.user;
}

export async function runTranslation({text,source,target,context='',register='natural',useAI=true,saveHistory=false}){
  return post('/api/translate/contextual',{text,source,target,context,register,use_ai:useAI,max_alternatives:5,save_history:saveHistory});
}
export function translationSpeakable(result){
  if(!result)return null;
  if(result.target_language==='egyptian'&&result.pronunciation?.classroom_reading)return{text:result.pronunciation.classroom_reading,language:'english'};
  const review=result.ai?.review;if(review?.preferred_interpretation?.text)return{text:review.preferred_interpretation.text,language:result.target_language};
  const d=result.deterministic||result;if(d.literal_gloss)return{text:d.literal_gloss,language:result.target_language};if(d.translations?.length)return{text:d.translations[0],language:result.target_language};if(d.english?.length&&result.target_language==='english')return{text:d.english[0],language:'english'};if(d.swahili?.length&&result.target_language==='swahili')return{text:d.swahili[0],language:'swahili'};return null;
}
