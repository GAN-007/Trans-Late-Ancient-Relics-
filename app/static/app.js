const $ = s => document.querySelector(s);
const $$ = s => [...document.querySelectorAll(s)];
const post = async (url, body) => {
  const r = await fetch(url,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});
  if(!r.ok) throw new Error(await r.text());
  return r.json();
};
const get = async url => {
  const r=await fetch(url); if(!r.ok) throw new Error(await r.text()); return r.json();
};
const esc = s => String(s ?? "").replace(/[&<>"']/g,m=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"}[m]));

$$('#tabs button').forEach(b=>b.onclick=()=>{
  $$('#tabs button').forEach(x=>x.classList.remove('active')); b.classList.add('active');
  $$('.tab').forEach(x=>x.classList.remove('active')); $('#'+b.dataset.tab).classList.add('active');
});

$('#encodeBtn').onclick=async()=>{
  const d=await post('/api/eshb/encode',{text:$('#bridgeInput').value,language:$('#bridgeLang').value});
  $('#bridgeStrict').value=d.strict; $('#bridgeDisplay').textContent=d.display; $('#decodeInput').value=d.strict;
};
$('#decodeBtn').onclick=async()=>{
  const d=await post('/api/eshb/decode',{text:$('#decodeInput').value}); $('#decodeOutput').textContent=d.decoded;
};
$('#ipaEncodeBtn').onclick=async()=>{
  const d=await post('/api/eshb/ipa/encode',{text:$('#ipaInput').value}); $('#ipaStrict').value=d.strict; $('#ipaOutput').textContent=d.display;
};
$('#ipaDecodeBtn').onclick=async()=>{
  const d=await post('/api/eshb/ipa/decode',{text:$('#ipaStrict').value}); $('#ipaOutput').textContent=d.ipa;
};
$('#hieroglyphizeBtn').onclick=async()=>{
  const d=await post('/api/egyptian/hieroglyphize',{text:$('#translitInput').value});
  $('#hieroOutput').textContent=d.hieroglyphs; $('#hieroAnalysis').textContent=JSON.stringify(d,null,2);
};
$('#parseGlyphBtn').onclick=async()=>{
  const d=await post('/api/egyptian/parse-uniliterals',{text:$('#glyphInput').value});
  $('#glyphOutput').textContent=d.transliteration+"\n"+d.warning;
};
$('#mdcBtn').onclick=async()=>{
  const d=await post('/api/egyptian/mdc-to-transliteration',{text:$('#mdcInput').value}); $('#mdcOutput').textContent=d.transliteration;
};
$('#translateBtn').onclick=async()=>{
  const d=await post('/api/translate',{text:$('#translateInput').value,source:$('#sourceLang').value,target:$('#targetLang').value});
  $('#translationGlyphs').textContent=d.hieroglyphs||"";
  $('#translationOutput').textContent=JSON.stringify(d,null,2);
};
async function searchDict(){
  const q=encodeURIComponent($('#dictQuery').value), lang=encodeURIComponent($('#dictLang').value);
  const d=await get(`/api/dictionary?q=${q}&language=${lang}&limit=100`);
  $('#dictResults').innerHTML=d.results.map(e=>`
    <div class="dict-entry">
      <div class="dict-top"><span class="dict-trans">${esc(e.transliteration)}</span>
      ${e.hieroglyphs?`<span class="glyph big">${esc(e.hieroglyphs)}</span>`:""}
      <span class="pill">${esc(e.pos)}</span><span class="pill">confidence: ${esc(e.confidence)}</span></div>
      <div><strong>EN:</strong> ${esc((e.english||[]).join("; "))}</div>
      <div><strong>SW:</strong> ${esc((e.swahili||[]).join("; "))}</div>
      <div class="muted">${esc(e.notes||"")}</div>
    </div>`).join("") || "<p>No result.</p>";
}
$('#dictBtn').onclick=searchDict; $('#dictQuery').addEventListener('keydown',e=>{if(e.key==="Enter")searchDict()});

async function loadLessons(){
  const data=await get('/api/lessons');
  $('#lessonList').innerHTML=data.map(l=>`<button class="lesson-btn" data-id="${l.id}">${l.id}. ${esc(l.title)}</button>`).join("");
  $$('.lesson-btn').forEach(b=>b.onclick=()=>showLesson(data.find(x=>x.id===Number(b.dataset.id))));
}
function showLesson(l){
  $('#lessonPane').innerHTML=`
    <div class="eyebrow">${esc(l.level)}</div><h2>${l.id}. ${esc(l.title)}</h2>
    <h3>Objectives</h3><ul>${l.objectives.map(x=>`<li>${esc(x)}</li>`).join("")}</ul>
    <p>${esc(l.content)}</p>
    <h3>Examples</h3>${l.examples.map(x=>`<div class="example">${x.egyptian?`<div class="glyph big">${esc(x.egyptian)}</div>`:""}
      ${x.transliteration?`<div><strong>${esc(x.transliteration)}</strong></div>`:""}
      ${x.mdc?`<div>MdC: ${esc(x.mdc)}</div>`:""}${x.classroom?`<div>Classroom reading: ${esc(x.classroom)}</div>`:""}
      <div>English: ${esc(x.english||"")}</div><div>Swahili: ${esc(x.swahili||"")}</div></div>`).join("")}
    <h3>Check yourself</h3>${l.quiz.map((q,i)=>`<div class="example"><strong>${esc(q.q)}</strong><div>${q.choices.map(c=>`<button class="quiz-choice" data-answer="${esc(q.answer)}" data-choice="${esc(c)}">${esc(c)}</button>`).join(" ")}</div><div class="quiz-feedback"></div></div>`).join("")}`;
  $$('.quiz-choice').forEach(btn=>btn.onclick=()=>{
    const ok=btn.dataset.answer===btn.dataset.choice;
    btn.parentElement.nextElementSibling.textContent=ok?"Correct.":"Not quite. Correct answer: "+btn.dataset.answer;
  });
}
async function loadSigns(){
  const d=await get('/api/egyptian/uniliterals');
  $('#signTable').innerHTML=`<table><thead><tr><th>Glyph</th><th>Value</th><th>Gardiner</th><th>MdC</th><th>Description</th></tr></thead><tbody>
  ${d.map(x=>`<tr><td class="glyph big">${esc(x.glyph)}</td><td>${esc(x.value)}</td><td>${esc(x.gardiner)}</td><td>${esc(x.mdc)}</td><td>${esc(x.name)}</td></tr>`).join("")}</tbody></table>`;
}
async function loadReferences(){
  const d=await get('/api/references');
  $('#references').innerHTML=d.map(r=>`<div class="dict-entry"><a href="${esc(r.url)}" target="_blank" rel="noreferrer"><strong>${esc(r.title)}</strong></a><div class="muted">${esc(r.note)}</div></div>`).join("");
}
loadLessons(); loadSigns(); loadReferences(); searchDict(); $('#encodeBtn').click();
