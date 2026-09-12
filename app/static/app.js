const $ = s => document.querySelector(s);
const $$ = s => [...document.querySelectorAll(s)];
const state = {
  user: null,
  roleOrder: {guest:0,learner:10,contributor:20,reviewer:30,admin:40},
  health: null,
  lastTranslation: null,
  lastSpokenText: '',
  cameraStream: null,
  autoScanTimer: null,
  scanning: false,
  recognition: null,
  deferredInstall: null,
  lessons: [],
  progress: new Map(),
};

const esc = s => String(s ?? '').replace(/[&<>"']/g, m => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[m]));
const fmtPct = n => Number.isFinite(Number(n)) ? `${Math.round(Number(n)*100)}%` : '—';

async function api(url, options={}) {
  const opts={credentials:'same-origin',...options};
  opts.headers={...(options.headers||{})};
  if(options.body && typeof options.body !== 'string') {
    opts.headers['Content-Type']='application/json';
    opts.body=JSON.stringify(options.body);
  }
  const r=await fetch(url,opts);
  let data;
  const ct=r.headers.get('content-type')||'';
  if(ct.includes('application/json')) data=await r.json(); else data={message:await r.text()};
  if(!r.ok) throw new Error(data.detail || data.message || `Request failed (${r.status})`);
  return data;
}
const get=url=>api(url);
const post=(url,body)=>api(url,{method:'POST',body});
const patch=(url,body)=>api(url,{method:'PATCH',body});

function toast(message,type='info',timeout=4200){
  const el=document.createElement('div');el.className=`toast ${type}`;el.textContent=message;$('#toastRegion').appendChild(el);setTimeout(()=>el.remove(),timeout);
}
function setStatus(el,text,kind=''){if(!el)return;el.textContent=text;el.className=`status-pill ${kind}`.trim();}
function roleAtLeast(role){const current=state.user?.role||'guest';return (state.roleOrder[current]??0)>=(state.roleOrder[role]??999);}

function activateTab(id){
  $$('#tabs button').forEach(b=>b.classList.toggle('active',b.dataset.tab===id));
  $$('.tab').forEach(x=>x.classList.toggle('active',x.id===id));
  window.scrollTo({top:0,behavior:'smooth'});
}
$$('#tabs button').forEach(b=>b.addEventListener('click',()=>activateTab(b.dataset.tab)));
$$('.nav-jump').forEach(b=>b.addEventListener('click',()=>activateTab(b.dataset.target)));
$('#accountQuickBtn').addEventListener('click',()=>activateTab('account'));

function candidateCard(c,index=0){
  const score=Number(c.confidence||0);
  const ambiguities=(c.ambiguities||[]).map(a=>`<li>${esc(JSON.stringify(a))}</li>`).join('');
  const assumptions=(c.assumptions||[]).map(a=>`<li>${esc(a)}</li>`).join('');
  const provenance=(c.provenance||[]).map(p=>`<li>${esc(p.type||'source')}${p.transliteration?` • ${esc(p.transliteration)}`:''}</li>`).join('');
  return `<article class="candidate-card ${index===0?'best':''}">
    <div class="candidate-head"><strong>${index===0?'Best supported candidate':`Alternative ${index+1}`}</strong><span class="pill">${esc(c.confidence_label||fmtPct(score))}</span></div>
    ${c.hieroglyphs?`<div class="candidate-glyphs">${esc(c.hieroglyphs)}</div>`:''}
    ${c.transliteration?`<div><strong>Transliteration:</strong> ${esc(c.transliteration)}</div>`:''}
    ${c.literal_translation?`<div><strong>Literal:</strong> ${esc(c.literal_translation)}</div>`:''}
    ${c.natural_translation?`<div><strong>Natural:</strong> ${esc(c.natural_translation)}</div>`:''}
    ${c.rationale?`<p>${esc(c.rationale)}</p>`:''}
    <div class="confidence-bar" title="Confidence ${fmtPct(score)}"><span style="width:${Math.max(0,Math.min(100,score*100))}%"></span></div>
    ${assumptions?`<details><summary>Assumptions</summary><ul class="meta-list">${assumptions}</ul></details>`:''}
    ${ambiguities?`<details><summary>Ambiguities</summary><ul class="meta-list">${ambiguities}</ul></details>`:''}
    ${provenance?`<details><summary>Provenance</summary><ul class="meta-list">${provenance}</ul></details>`:''}
  </article>`;
}

function renderTranslation(result,targetEl='#translationCandidates'){
  const el=$(targetEl);if(!el)return;
  const candidates=result.candidates||[];
  if(candidates.length) el.innerHTML=candidates.map(candidateCard).join('');
  else if(result.literal_gloss) el.innerHTML=`<article class="candidate-card best"><strong>Lexical gloss</strong><p>${esc(result.literal_gloss)}</p>${(result.ambiguity||[]).length?`<details><summary>Ambiguities</summary><pre>${esc(JSON.stringify(result.ambiguity,null,2))}</pre></details>`:''}</article>`;
  else if(result.translations?.length) el.innerHTML=result.translations.map((t,i)=>`<article class="candidate-card ${i===0?'best':''}"><strong>${esc(t)}</strong></article>`).join('');
  else el.innerHTML=`<article class="candidate-card"><strong>Analysis only</strong><p>${esc(result.message||'No secure translation candidate.')}</p>${result.unresolved?.length?`<p><strong>Unknown:</strong> ${esc(result.unresolved.join(', '))}</p>`:''}</article>`;
  const speak = candidates[0]?.natural_translation || candidates[0]?.transliteration || result.natural_translation || result.literal_gloss || result.translations?.[0] || result.transliteration || '';
  state.lastSpokenText=speak;
}

function speak(text,lang='en-US'){
  if(!('speechSynthesis' in window)){toast('Speech synthesis is not available on this device.','error');return;}
  if(!text){toast('There is no result to read aloud yet.','error');return;}
  speechSynthesis.cancel();
  const utter=new SpeechSynthesisUtterance(text);utter.lang=lang;utter.rate=0.92;speechSynthesis.speak(utter);
}

async function loadHealth(){
  try{state.health=await get('/api/health');const ai=state.health.ai||{};setStatus($('#aiStatus'),ai.vision_ai_configured||ai.text_ai_configured?'AI connected':'local engine','good');}
  catch(e){setStatus($('#aiStatus'),'service unavailable','bad');}
}

async function loadAuth(){
  try{const d=await get('/api/auth/me');state.user=d.user;state.roleOrder=d.role_order||state.roleOrder;renderAccount();}
  catch(e){state.user=null;renderAccount();}
}
function renderAccount(){
  const u=state.user;
  $('#accountQuickBtn').textContent=u?`${u.display_name} · ${u.role}`:'Guest';
  setStatus($('#communityRole'),u?.role||'guest',u?'good':'');
  if(u){
    $('#accountSummary').innerHTML=`<h3>${esc(u.display_name)}</h3><p>${esc(u.email)}</p><span class="pill">${esc(u.role)}</span>`;
    $('#logoutBtn').classList.remove('hidden');
    $('#loginForm').classList.add('hidden');$('#registerForm').classList.add('hidden');
    setStatus($('#progressStatus'),'progress sync on','good');
    loadProgress();
  } else {
    $('#accountSummary').innerHTML='<p>You are using guest mode. Translation works, but synchronized learning progress, history, cloud vision and contribution permissions require an account.</p>';
    $('#logoutBtn').classList.add('hidden');
    $('#loginForm').classList.remove('hidden');$('#registerForm').classList.remove('hidden');
    setStatus($('#progressStatus'),'sign in to sync progress','warn');
  }
  const canContribute=roleAtLeast('contributor'), canReview=roleAtLeast('reviewer');
  [...$('#proposalForm').elements].forEach(x=>x.disabled=!canContribute);
  $('#refreshReviewBtn').disabled=!canReview;$('#loadInsightsBtn').disabled=!canReview;$('#runAiResearchBtn').disabled=!canReview;
  if(!canReview) $('#reviewQueue').innerHTML='<p class="muted">Reviewer role required.</p>';
}

$('#loginForm').addEventListener('submit',async e=>{e.preventDefault();try{const d=await post('/api/auth/login',{email:$('#loginEmail').value,password:$('#loginPassword').value});state.user=d.user;$('#loginMessage').textContent='Signed in.';renderAccount();toast('Signed in.','success');}catch(err){$('#loginMessage').textContent=err.message;}});
$('#registerForm').addEventListener('submit',async e=>{e.preventDefault();try{const d=await post('/api/auth/register',{display_name:$('#registerName').value,email:$('#registerEmail').value,password:$('#registerPassword').value});state.user=d.user;$('#registerMessage').textContent='Account created.';renderAccount();toast('Learner account created.','success');}catch(err){$('#registerMessage').textContent=err.message;}});
$('#logoutBtn').addEventListener('click',async()=>{try{await post('/api/auth/logout',{});}catch{}state.user=null;renderAccount();toast('Signed out.');});

async function translateFromForm(){
  setStatus($('#translationConfidence'),'working…','warn');
  try{
    const body={text:$('#translateInput').value,source:$('#sourceLang').value,target:$('#targetLang').value,context:$('#translateContext').value,intent:$('#translateIntent').value,mode:$('#translateMode').value,use_ai:$('#useAiToggle').checked};
    const d=await post('/api/translate',body);state.lastTranslation=d;$('#translationGlyphs').textContent=d.hieroglyphs||d.candidates?.[0]?.hieroglyphs||'';$('#translationOutput').textContent=JSON.stringify(d,null,2);renderTranslation(d);
    setStatus($('#translationConfidence'),`confidence ${fmtPct(d.confidence??d.candidates?.[0]?.confidence??0)}`,d.ok?'good':'warn');$('#feedbackPanel').classList.remove('hidden');
  }catch(e){setStatus($('#translationConfidence'),'failed','bad');toast(e.message,'error');}
}
$('#translateBtn').addEventListener('click',translateFromForm);
$('#speakTranslateBtn').addEventListener('click',async()=>{
  if($('#targetLang').value==='egyptian' && state.lastTranslation){
    const translit=state.lastTranslation.candidates?.[0]?.transliteration||state.lastTranslation.transliteration;
    if(translit){try{const p=await post('/api/egyptian/pronunciation',{text:translit});speak(p.classroom_reading,'en-US');toast('Read aloud uses an Egyptological classroom convention, not exact ancient vowels.');return;}catch(e){toast(e.message,'error');}}
  }
  speak(state.lastSpokenText,$('#targetLang').value==='swahili'?'sw-KE':'en-US');
});
$$('.feedback-btn').forEach(b=>b.addEventListener('click',async()=>{if(!state.lastTranslation)return;try{await post('/api/feedback',{translation_id:state.lastTranslation.translation_id,rating:b.dataset.rating,context:$('#translateContext').value||null});toast('Feedback recorded for the learning loop.','success');}catch(e){toast(e.message,'error');}}));

// ESHB and IPA
$('#encodeBtn').addEventListener('click',async()=>{try{const d=await post('/api/eshb/encode',{text:$('#bridgeInput').value,language:$('#bridgeLang').value});$('#bridgeStrict').value=d.strict;$('#bridgeDisplay').textContent=d.display;$('#decodeInput').value=d.strict;}catch(e){toast(e.message,'error');}});
$('#decodeBtn').addEventListener('click',async()=>{try{const d=await post('/api/eshb/decode',{text:$('#decodeInput').value});$('#decodeOutput').textContent=d.decoded;}catch(e){toast(e.message,'error');}});
$('#ipaEncodeBtn').addEventListener('click',async()=>{try{const d=await post('/api/eshb/ipa/encode',{text:$('#ipaInput').value});$('#ipaStrict').value=d.strict;$('#ipaOutput').textContent=d.display;}catch(e){toast(e.message,'error');}});
$('#ipaDecodeBtn').addEventListener('click',async()=>{try{const d=await post('/api/eshb/ipa/decode',{text:$('#ipaStrict').value});$('#ipaOutput').textContent=d.ipa;}catch(e){toast(e.message,'error');}});
$('#speakBridgeBtn').addEventListener('click',()=>speak($('#bridgeInput').value,$('#bridgeLang').value==='swahili'?'sw-KE':'en-US'));

// Script tools
$('#hieroglyphizeBtn').addEventListener('click',async()=>{try{const d=await post('/api/egyptian/hieroglyphize',{text:$('#translitInput').value});$('#hieroOutput').textContent=d.hieroglyphs;$('#hieroAnalysis').textContent=JSON.stringify(d,null,2);}catch(e){toast(e.message,'error');}});
$('#parseGlyphBtn').addEventListener('click',async()=>{try{const d=await post('/api/egyptian/parse-uniliterals',{text:$('#glyphInput').value});$('#glyphOutput').textContent=`${d.transliteration}\n${d.warning}`;}catch(e){toast(e.message,'error');}});
$('#mdcBtn').addEventListener('click',async()=>{try{const d=await post('/api/egyptian/mdc-to-transliteration',{text:$('#mdcInput').value});$('#mdcOutput').textContent=d.transliteration;}catch(e){toast(e.message,'error');}});

// Dictionary
async function searchDict(){try{const q=encodeURIComponent($('#dictQuery').value),lang=encodeURIComponent($('#dictLang').value);const d=await get(`/api/dictionary?q=${q}&language=${lang}&limit=100`);$('#dictResults').innerHTML=d.results.map(e=>`<div class="dict-entry"><div class="dict-top"><span class="dict-trans">${esc(e.transliteration)}</span>${e.hieroglyphs?`<span class="glyph big">${esc(e.hieroglyphs)}</span>`:''}<span class="pill">${esc(e.pos)}</span><span class="pill">${esc(e.confidence||'unrated')}</span></div><div><strong>EN:</strong> ${esc((e.english||[]).join('; '))}</div><div><strong>SW:</strong> ${esc((e.swahili||[]).join('; '))}</div><div class="muted">${esc(e.notes||'')}</div></div>`).join('')||'<p>No result.</p>';}catch(e){toast(e.message,'error');}}
$('#dictBtn').addEventListener('click',searchDict);$('#dictQuery').addEventListener('keydown',e=>{if(e.key==='Enter')searchDict();});

// Lessons and progress
async function loadLessons(){try{state.lessons=await get('/api/lessons');$('#lessonCount').textContent=`${state.lessons.length} lessons`;renderLessonList();}catch(e){toast(e.message,'error');}}
function renderLessonList(){$('#lessonList').innerHTML=state.lessons.map(l=>`<button class="lesson-btn ${state.progress.has(`lesson:${l.id}`)?'done':''}" data-id="${l.id}">${l.id}. ${esc(l.title)}</button>`).join('');$$('.lesson-btn').forEach(b=>b.addEventListener('click',()=>showLesson(state.lessons.find(x=>x.id===Number(b.dataset.id)))));}
function showLesson(l){$('#lessonPane').innerHTML=`<div class="eyebrow">${esc(l.level)}</div><h2>${l.id}. ${esc(l.title)}</h2><h3>Objectives</h3><ul>${l.objectives.map(x=>`<li>${esc(x)}</li>`).join('')}</ul><p>${esc(l.content)}</p><h3>Examples</h3>${l.examples.map(x=>`<div class="example">${x.egyptian?`<div class="glyph big">${esc(x.egyptian)}</div>`:''}${x.transliteration?`<div><strong>${esc(x.transliteration)}</strong></div>`:''}${x.mdc?`<div>MdC: ${esc(x.mdc)}</div>`:''}${x.classroom?`<div>Classroom reading: ${esc(x.classroom)}</div>`:''}<div>English: ${esc(x.english||'')}</div><div>Swahili: ${esc(x.swahili||'')}</div></div>`).join('')}<h3>Check yourself</h3>${l.quiz.map(q=>`<div class="example quiz-block" data-lesson="${l.id}"><strong>${esc(q.q)}</strong><div>${q.choices.map(c=>`<button class="quiz-choice" data-answer="${esc(q.answer)}" data-choice="${esc(c)}">${esc(c)}</button>`).join(' ')}</div><div class="quiz-feedback"></div></div>`).join('')}`;$$('.quiz-choice').forEach(btn=>btn.addEventListener('click',async()=>{const ok=btn.dataset.answer===btn.dataset.choice;btn.parentElement.nextElementSibling.textContent=ok?'Correct.':'Not quite. Correct answer: '+btn.dataset.answer;if(ok)await recordLessonProgress(l.id);}));}
async function recordLessonProgress(id){state.progress.set(`lesson:${id}`,true);renderLessonList();if(state.user){try{await post('/api/progress',{item_type:'lesson',item_id:String(id),score:1});}catch(e){toast('Progress could not sync: '+e.message,'error');}}else localStorage.setItem(`eshb.progress.lesson.${id}`,'1');}
async function loadProgress(){state.progress=new Map();if(state.user){try{const rows=await get('/api/progress');rows.forEach(r=>state.progress.set(`${r.item_type}:${r.item_id}`,true));}catch{}}else{for(const k of Object.keys(localStorage))if(k.startsWith('eshb.progress.lesson.'))state.progress.set(`lesson:${k.split('.').pop()}`,true);}renderLessonList();}

// Signs
async function loadSigns(){try{const d=await get('/api/egyptian/uniliterals');$('#signTable').innerHTML=`<table><thead><tr><th>Glyph</th><th>Value</th><th>Gardiner</th><th>MdC</th><th>Description</th></tr></thead><tbody>${d.map(x=>`<tr><td class="glyph big">${esc(x.glyph)}</td><td>${esc(x.value)}</td><td>${esc(x.gardiner)}</td><td>${esc(x.mdc)}</td><td>${esc(x.name)}</td></tr>`).join('')}</tbody></table>`;}catch(e){toast(e.message,'error');}}

// Camera live lens
async function startCamera(){
  if(!navigator.mediaDevices?.getUserMedia){toast('Camera API is unavailable in this browser.','error');return;}
  try{
    state.cameraStream=await navigator.mediaDevices.getUserMedia({video:{facingMode:{ideal:'environment'},width:{ideal:1920},height:{ideal:1080}},audio:false});
    $('#cameraVideo').srcObject=state.cameraStream;$('#cameraPlaceholder').classList.add('hidden');$('#startCameraBtn').disabled=true;$('#stopCameraBtn').disabled=false;$('#scanFrameBtn').disabled=false;$('#autoScanToggle').disabled=false;setStatus($('#cameraStatus'),'camera ready','good');setStatus($('#liveSessionStatus'),'camera active','good');
  }catch(e){setStatus($('#cameraStatus'),'permission denied','bad');toast(`Camera could not start: ${e.message}`,'error');}
}
function stopCamera(){if(state.autoScanTimer){clearInterval(state.autoScanTimer);state.autoScanTimer=null;}$('#autoScanToggle').checked=false;state.cameraStream?.getTracks().forEach(t=>t.stop());state.cameraStream=null;$('#cameraVideo').srcObject=null;$('#cameraPlaceholder').classList.remove('hidden');$('#startCameraBtn').disabled=false;$('#stopCameraBtn').disabled=true;$('#scanFrameBtn').disabled=true;$('#autoScanToggle').disabled=true;setStatus($('#cameraStatus'),'camera off');setStatus($('#liveSessionStatus'),'idle');}
async function scanFrame(){if(!state.cameraStream||state.scanning)return;state.scanning=true;try{const video=$('#cameraVideo'),canvas=$('#cameraCanvas');const w=Math.min(1280,video.videoWidth||1280);const ratio=(video.videoHeight||960)/(video.videoWidth||1280);canvas.width=w;canvas.height=Math.round(w*ratio);canvas.getContext('2d').drawImage(video,0,0,canvas.width,canvas.height);const image_data_url=canvas.toDataURL('image/jpeg',0.82);$('#visionOverlay').textContent='Analyzing current frame…';const d=await post('/api/live/vision/analyze',{image_data_url,target_language:$('#visionTarget').value,context:$('#visionContext').value,session_id:'browser-live'});renderVision(d);$('#visionOverlay').textContent=d.ok?'Analysis updated':d.message||d.status;}catch(e){$('#visionOverlay').textContent=e.message;toast(e.message,'error');}finally{state.scanning=false;}}
function renderVision(d){if(!d.ok){$('#visionResults').innerHTML=`<article class="candidate-card"><strong>${esc(d.status||'Vision unavailable')}</strong><p>${esc(d.message||'')}</p></article>`;return;}const a=d.analysis||{};let html=`<article class="candidate-card best"><div class="candidate-head"><strong>Frame analysis</strong><span class="pill">${esc(a.reading_direction||'direction uncertain')}</span></div>`;if(a.hieroglyphs)html+=`<div class="candidate-glyphs">${esc(a.hieroglyphs)}</div>`;if(a.transliteration)html+=`<p><strong>Transliteration:</strong> ${esc(a.transliteration)}</p>`;if(a.notes)html+=`<p>${esc(a.notes)}</p>`;html+=`<details><summary>Full provider analysis</summary><pre>${esc(JSON.stringify(a,null,2))}</pre></details></article>`;$('#visionResults').innerHTML=html;}
$('#startCameraBtn').addEventListener('click',startCamera);$('#stopCameraBtn').addEventListener('click',stopCamera);$('#scanFrameBtn').addEventListener('click',scanFrame);$('#autoScanToggle').addEventListener('change',e=>{if(state.autoScanTimer){clearInterval(state.autoScanTimer);state.autoScanTimer=null;}if(e.target.checked)state.autoScanTimer=setInterval(scanFrame,Math.max(1200,state.health?.live_frame_interval_ms||1800));});$('#clearLiveBtn').addEventListener('click',()=>{$('#visionResults').innerHTML='<p class="muted">No frame analyzed yet.</p>';$('#visionOverlay').textContent='';});

// Speech recognition and read-aloud
const SpeechRecognition=window.SpeechRecognition||window.webkitSpeechRecognition;
if(SpeechRecognition){state.recognition=new SpeechRecognition();state.recognition.continuous=true;state.recognition.interimResults=true;state.recognition.onresult=e=>{let final='',interim='';for(let i=e.resultIndex;i<e.results.length;i++){const t=e.results[i][0].transcript;if(e.results[i].isFinal)final+=t+' ';else interim+=t;}if(final)$('#speechTranscript').value=($('#speechTranscript').value+' '+final).trim();setStatus($('#speechStatus'),interim?`hearing: ${interim.slice(0,26)}`:'listening…','good');};state.recognition.onerror=e=>{setStatus($('#speechStatus'),e.error,'bad');};state.recognition.onend=()=>{$('#startMicBtn').disabled=false;$('#stopMicBtn').disabled=true;setStatus($('#speechStatus'),'mic idle');};$('#speechSupport').textContent='Device speech recognition is available. Recognition quality depends on the browser and installed language model/service.';}else{$('#startMicBtn').disabled=true;$('#speechSupport').textContent='This browser does not expose Web Speech Recognition. You can still type the transcript and use read-aloud.';}
$('#startMicBtn').addEventListener('click',()=>{if(!state.recognition)return;try{state.recognition.lang=$('#speechSource').value==='swahili'?'sw-KE':'en-US';state.recognition.start();$('#startMicBtn').disabled=true;$('#stopMicBtn').disabled=false;setStatus($('#speechStatus'),'listening…','good');}catch(e){toast(e.message,'error');}});$('#stopMicBtn').addEventListener('click',()=>state.recognition?.stop());
async function translateSpeech(){const text=$('#speechTranscript').value.trim();if(!text){toast('Speak or type a transcript first.','error');return;}try{const d=await post('/api/translate',{text,source:$('#speechSource').value,target:$('#speechTarget').value,context:'Live spoken conversation',intent:'conversation',mode:'natural',use_ai:true});renderTranslation(d,'#liveTranslation');state.lastTranslation=d;}catch(e){toast(e.message,'error');}}
$('#translateSpeechBtn').addEventListener('click',translateSpeech);$('#speakResultBtn').addEventListener('click',async()=>{
  if($('#speechTarget').value==='egyptian' && state.lastTranslation){const translit=state.lastTranslation.candidates?.[0]?.transliteration||state.lastTranslation.transliteration;if(translit){try{const p=await post('/api/egyptian/pronunciation',{text:translit});speak(p.classroom_reading,'en-US');toast('Egyptian audio is a classroom reading convention.');return;}catch(e){toast(e.message,'error');}}}
  speak(state.lastSpokenText,$('#speechTarget').value==='swahili'?'sw-KE':'en-US');
});

// Contribution and review
$('#proposalForm').addEventListener('submit',async e=>{e.preventDefault();try{const d=await post('/api/contributions/lexicon',{transliteration:$('#proposalTranslit').value,english:$('#proposalEnglish').value.split(',').map(x=>x.trim()).filter(Boolean),swahili:$('#proposalSwahili').value.split(',').map(x=>x.trim()).filter(Boolean),pos:$('#proposalPos').value,hieroglyphs:$('#proposalGlyphs').value||null,gardiner:$('#proposalGardiner').value.split(',').map(x=>x.trim()).filter(Boolean),mdc:null,notes:null,evidence:$('#proposalEvidence').value||null,confidence:'proposed'});$('#proposalMessage').textContent=`Proposal #${d.proposal.id} submitted for review.`;toast('Proposal submitted.','success');e.target.reset();}catch(err){$('#proposalMessage').textContent=err.message;}});
async function loadReviewQueue(){try{const d=await get('/api/review/lexicon?status=pending');$('#reviewQueue').innerHTML=d.proposals.length?d.proposals.map(p=>`<article class="candidate-card" data-proposal="${p.id}"><div class="candidate-head"><strong>#${p.id} ${esc(p.transliteration)}</strong><span class="pill">${p.ai_generated?'AI proposed':'human proposed'}</span></div>${p.hieroglyphs?`<div class="candidate-glyphs">${esc(p.hieroglyphs)}</div>`:''}<p><strong>EN:</strong> ${esc(p.english.join('; '))}<br><strong>SW:</strong> ${esc(p.swahili.join('; '))}<br><strong>POS:</strong> ${esc(p.pos)}</p><p class="muted">Evidence: ${esc(p.evidence||'none supplied')}</p><div class="row wrap"><button class="approve-proposal" data-id="${p.id}">Approve</button><button class="reject-proposal danger" data-id="${p.id}">Reject</button></div></article>`).join(''):'<p>No pending proposals.</p>';$$('.approve-proposal').forEach(b=>b.addEventListener('click',()=>decideProposal(b.dataset.id,'approved')));$$('.reject-proposal').forEach(b=>b.addEventListener('click',()=>decideProposal(b.dataset.id,'rejected')));}catch(e){$('#reviewQueue').innerHTML=`<p>${esc(e.message)}</p>`;}}
async function decideProposal(id,decision){try{await post(`/api/review/lexicon/${id}`,{decision,notes:null});toast(`Proposal ${decision}.`,'success');loadReviewQueue();}catch(e){toast(e.message,'error');}}
$('#refreshReviewBtn').addEventListener('click',loadReviewQueue);$('#loadInsightsBtn').addEventListener('click',async()=>{try{$('#learningInsights').textContent=JSON.stringify(await get('/api/admin/learning/insights'),null,2);}catch(e){$('#learningInsights').textContent=e.message;}});$('#runAiResearchBtn').addEventListener('click',async()=>{try{const d=await post('/api/admin/learning/propose',{min_frequency:3,limit:20});$('#learningInsights').textContent=JSON.stringify(d,null,2);if(d.created?.length)loadReviewQueue();}catch(e){$('#learningInsights').textContent=e.message;}});

// History
$('#loadHistoryBtn').addEventListener('click',async()=>{try{const d=await get('/api/history?limit=50');$('#historyResults').innerHTML=d.history.map(h=>`<div class="dict-entry"><strong>${esc(h.source_text)}</strong><div class="muted">${esc(h.source_language)} → ${esc(h.target_language)} • ${esc(h.created_at)}</div></div>`).join('')||'<p>No history yet.</p>';}catch(e){$('#historyResults').innerHTML=`<p>${esc(e.message)}</p>`;}});

// References and capabilities
async function loadReferences(){try{const d=await get('/api/references');$('#references').innerHTML=d.map(r=>`<div class="dict-entry"><a href="${esc(r.url)}" target="_blank" rel="noreferrer"><strong>${esc(r.title)}</strong></a><div class="muted">${esc(r.note)}</div></div>`).join('');}catch(e){$('#references').textContent=e.message;}}
function renderCapabilities(){const caps=[['Camera',!!navigator.mediaDevices?.getUserMedia],['Speech recognition',!!SpeechRecognition],['Speech synthesis','speechSynthesis' in window],['WebSocket','WebSocket' in window],['Service worker','serviceWorker' in navigator],['PWA install',matchMedia('(display-mode: standalone)').matches||!!state.deferredInstall],['Secure context',window.isSecureContext],['Offline storage','localStorage' in window]];$('#capabilityReport').innerHTML=`<table><tbody>${caps.map(([n,v])=>`<tr><td>${esc(n)}</td><td><span class="pill">${v?'available':'unavailable'}</span></td></tr>`).join('')}</tbody></table>`;}

// Network + PWA
function updateNetwork(){setStatus($('#networkStatus'),navigator.onLine?'● online':'● offline',navigator.onLine?'good':'warn');}
window.addEventListener('online',updateNetwork);window.addEventListener('offline',updateNetwork);updateNetwork();
window.addEventListener('beforeinstallprompt',e=>{e.preventDefault();state.deferredInstall=e;$('#installBtn').classList.remove('hidden');renderCapabilities();});$('#installBtn').addEventListener('click',async()=>{if(!state.deferredInstall)return;state.deferredInstall.prompt();await state.deferredInstall.userChoice;state.deferredInstall=null;$('#installBtn').classList.add('hidden');});
if('serviceWorker' in navigator)window.addEventListener('load',()=>navigator.serviceWorker.register('/service-worker.js').catch(()=>{}));

async function init(){await loadHealth();await loadAuth();renderCapabilities();await Promise.all([loadLessons(),loadSigns(),loadReferences()]);await searchDict();await loadProgress();$('#encodeBtn').click();}
init();
