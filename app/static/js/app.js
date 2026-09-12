import {initTabs,loadCapabilities,refreshUser,toast} from './core.js';
import {initTranslate,syncTranslateAuth} from './translate.js';
import {initLens} from './lens.js';
import {initTalk} from './talk.js';
import {initLearn} from './learn.js';
import {initAccount} from './account.js';
import {onUserChanged} from './core.js';

async function boot(){
  try{
    initTabs();initTranslate();initLens();initTalk();initAccount();onUserChanged(syncTranslateAuth);
    await Promise.all([loadCapabilities(),refreshUser(),initLearn()]);
  }catch(error){toast(`Startup warning: ${error.message}`);}
  if('serviceWorker' in navigator){try{await navigator.serviceWorker.register('/service-worker.js');}catch{}}
}
boot();
