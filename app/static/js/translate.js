import {post} from './api.js';
import {$,esc,runTranslation,setBusy,state,toast,translationSpeakable} from './core.js';
import {speak} from './speech.js';

function render(result){
  $('#translationEmpty').hidden=true;$('#translationResult').hidden=false;$('#translationRaw').textContent=JSON.stringify(result,null,2);
  const d=result.deterministic||result,glyphs=d.hieroglyphs||d.orthography?.hieroglyphs||'',trans=d.transliteration||'',preferred=result.ai?.review?.preferred_interpretation;
  const primary=preferred?.text||d.literal_gloss||d.translations?.join(' / ')||(result.ok&&trans?trans:d.message||result.message||'No secure full translation is available yet.');
  $('#translationGlyphs').textContent=glyphs;$('#translationPrimary').innerHTML=`${trans?`<div><strong>Transliteration:</strong> ${esc(trans)}</div>`:''}<div><strong>Primary reading:</strong> ${esc(primary)}</div><div class="microcopy">Mode: ${esc(d.mode||'contextual')} • Confidence: ${esc(d.confidence??'context dependent')}</div>`;
  $('#translationPronunciation').innerHTML=result.pronunciation?`<strong>Classroom reading:</strong> ${esc(result.pronunciation.classroom_reading)}<div class="microcopy">${esc(result.pronunciation.warning)}</div>`:'';
  const lexical=result.lexical_alternatives||[], aiAlt=result.ai?.review?.alternatives||[], ambiguity=result.ai?.review?.ambiguity_notes||d.ambiguity||[];
  $('#translationAlternatives').innerHTML=`${(lexical.length||aiAlt.length)?'<h3>Alternative interpretations</h3>':''}${lexical.map(i=>`<div class="alternative-card"><strong>${esc(i.transliteration)}</strong> — ${esc((i.english||[]).join(', '))} / ${esc((i.swahili||[]).join(', '))}<div class="microcopy">${esc(i.pos||'')} • ${esc(i.confidence||'')}</div></div>`).join('')}${aiAlt.map(i=>`<div class="alternative-card"><strong>${esc(i.text||'')}</strong><div>${esc(i.rationale||'')}</div><div class="microcopy">AI confidence: ${esc(i.confidence??'')}</div></div>`).join('')}${Array.isArray(ambiguity)&&ambiguity.length?`<div class="warning"><strong>Ambiguity:</strong> ${esc(ambiguity.map(x=>typeof x==='string'?x:JSON.stringify(x)).join(' • '))}</div>`:''}`;
  $('#speakTranslationBtn').disabled=!translationSpeakable(result);$('#translationFeedback').hidden=!state.user;state.feedbackRating=0;$('#feedbackCorrection').value='';$('#feedbackStatus').textContent='';
}
export function initTranslate(){
  $('#translateBtn').addEventListener('click',async()=>{const card=$('#translationCard');setBusy(card,true);$('#translateBtn').disabled=true;try{const result=await runTranslation({text:$('#translateInput').value,source:$('#sourceLang').value,target:$('#targetLang').value,context:$('#translateContext').value,register:$('#translateRegister').value,useAI:$('#useAi').checked});state.lastTranslation=result;render(result);}catch(e){toast(e.message);}finally{setBusy(card,false);$('#translateBtn').disabled=false;}});
  $('#speakTranslationBtn').addEventListener('click',()=>{const item=translationSpeakable(state.lastTranslation);if(!item||!speak(item.text,item.language))toast('Speech synthesis is not available on this device.');});
  $('#feedbackHelpfulBtn').addEventListener('click',()=>{state.feedbackRating=1;$('#feedbackStatus').textContent='Marked helpful. Save to submit.';});
  $('#feedbackCorrectionBtn').addEventListener('click',()=>{state.feedbackRating=-1;$('#feedbackStatus').textContent='Marked as needing correction. Add the missing nuance if you can.';$('#feedbackCorrection').focus();});
  $('#feedbackSaveBtn').addEventListener('click',async()=>{if(!state.user||!state.lastTranslation)return toast('Sign in to submit feedback.');try{await post('/api/feedback',{kind:'translation',source_text:state.lastTranslation.source||$('#translateInput').value,source_language:state.lastTranslation.source_language||$('#sourceLang').value,target_language:state.lastTranslation.target_language||$('#targetLang').value,rating:state.feedbackRating,correction:$('#feedbackCorrection').value,context:$('#translateContext').value,note:'Submitted from contextual translator'});$('#feedbackStatus').textContent='Feedback saved for human review.';}catch(e){$('#feedbackStatus').textContent=e.message;}});
}
export function syncTranslateAuth(){if(!$('#translationResult').hidden)$('#translationFeedback').hidden=!state.user;}
