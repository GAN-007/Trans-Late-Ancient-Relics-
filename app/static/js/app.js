import {initTabs,loadCapabilities,refreshUser,toast} from './core.js';
import {initTranslate,syncTranslateAuth} from './translate.js';
import {initLens} from './lens.js';
import {initTalk} from './talk.js';
import {initLearn} from './learn.js';
import {initAccount} from './account.js';
import {onUserChanged} from './core.js';

function markV3(){
  const footer=document.querySelector('footer');
  if(footer){const spans=footer.querySelectorAll('span');if(spans[0])spans[0].textContent='Trans-Late Ancient Relics v3';if(spans[1])spans[1].textContent='Middle Egyptian • English • Swahili • ESHB • Voice • Streaming Vision • Research Review';}
  const lensIntro=document.querySelector('#lensTitle')?.nextElementSibling;
  if(lensIntro)lensIntro.textContent='Point the camera at an inscription. Ordinary capture/live-analysis frames are transient. Research image retention is a separate signed-in correction workflow that requires explicit consent and must also be enabled by the server.';
  for(const li of document.querySelectorAll('#about li')){
    if(li.textContent.trim()==='Camera frames are not stored by the application.')li.textContent='Ordinary camera-analysis frames are not stored. A research correction can include a frame only with explicit user consent and only when server-side research image collection is enabled.';
  }
}

async function boot(){
  try{
    markV3();initTabs();initTranslate();initLens();initTalk();initAccount();onUserChanged(syncTranslateAuth);
    await Promise.all([loadCapabilities(),refreshUser(),initLearn()]);
  }catch(error){toast(`Startup warning: ${error.message}`);}
  if('serviceWorker' in navigator){try{await navigator.serviceWorker.register('/service-worker.js');}catch{}}
}
boot();
