from pathlib import Path
import json
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .models import ESHBEncodeRequest, TextRequest, TranslationRequest, ProgressRequest
from .eshb import encode, decode, encode_ipa, decode_ipa, codebook_rows
from .egyptian import search_dictionary, hieroglyphize_phrase, parse_uniliterals, uniliteral_table, mdc_to_transliteration, transliteration_to_mdc
from .translator import translate_word, translate_phrase, egyptian_to_modern
from .pedagogy import lessons, get_lesson, random_vocab_quiz, save_progress, get_progress

BASE = Path(__file__).parent
STATIC = BASE / "static"
DATA = BASE / "data"

app = FastAPI(title="ESHB Ancient Egyptian Tutor",version="1.0.0",description="Middle Egyptian learning + reversible English/Swahili/IPA ESHB bridge.")
app.mount("/static", StaticFiles(directory=STATIC), name="static")

@app.get("/")
def home(): return FileResponse(STATIC / "index.html")

@app.get("/api/health")
def health(): return {"ok":True,"service":"ESHB Ancient Egyptian Tutor","version":"1.0.0"}

@app.get("/api/eshb/codebook")
def eshb_codebook(): return codebook_rows()

@app.post("/api/eshb/encode")
def eshb_encode(req: ESHBEncodeRequest): return encode(req.text, req.language).__dict__

@app.post("/api/eshb/decode")
def eshb_decode(req: TextRequest): return {"source":req.text,"decoded":decode(req.text),"warning":"Strict ESHB separators are required for guaranteed reversibility."}

@app.post("/api/eshb/ipa/encode")
def ipa_encode(req: TextRequest): return encode_ipa(req.text).__dict__

@app.post("/api/eshb/ipa/decode")
def ipa_decode(req: TextRequest): return {"source":req.text,"ipa":decode_ipa(req.text)}

@app.get("/api/egyptian/uniliterals")
def egyptian_uniliterals(): return uniliteral_table()

@app.post("/api/egyptian/hieroglyphize")
def egyptian_hieroglyphize(req: TextRequest): return hieroglyphize_phrase(req.text)

@app.post("/api/egyptian/parse-uniliterals")
def egyptian_parse(req: TextRequest): return parse_uniliterals(req.text)

@app.post("/api/egyptian/mdc-to-transliteration")
def mdc_to_trans(req: TextRequest): return {"source":req.text,"transliteration":mdc_to_transliteration(req.text)}

@app.post("/api/egyptian/transliteration-to-mdc")
def trans_to_mdc(req: TextRequest): return {"source":req.text,"mdc":transliteration_to_mdc(req.text)}

@app.get("/api/dictionary")
def dictionary(q: str="", language: str="all", pos: str|None=None, limit: int=50): return {"query":q,"results":search_dictionary(q, language, pos, limit)}

@app.post("/api/translate")
def translate(req: TranslationRequest):
    if req.source == "egyptian":
        if req.target == "egyptian": return hieroglyphize_phrase(req.text)
        return egyptian_to_modern(req.text, req.target)
    if req.target != "egyptian":
        first = translate_word(req.text, req.source, "egyptian")
        if not first.get("ok"): return first
        translations = first.get(req.target, [])
        return {"ok":True,"source":req.text,"target_language":req.target,"translations":translations,"pivot":first}
    exact = translate_word(req.text, req.source, "egyptian")
    if exact.get("ok"): return exact
    return translate_phrase(req.text, req.source)

@app.get("/api/lessons")
def all_lessons(): return lessons()

@app.get("/api/lessons/{lesson_id}")
def lesson(lesson_id: int):
    item=get_lesson(lesson_id)
    if not item: raise HTTPException(404,"Lesson not found")
    return item

@app.get("/api/quiz/vocabulary")
def quiz(language: str="english", count: int=10):
    if language not in ("english","swahili"): raise HTTPException(400,"language must be english or swahili")
    return random_vocab_quiz(language, max(1,min(count,50)))

@app.post("/api/progress")
def update_progress(req: ProgressRequest): return save_progress(req.learner,req.item_type,req.item_id,req.score)

@app.get("/api/progress/{learner}")
def progress(learner: str): return get_progress(learner)

@app.get("/api/references")
def references(): return json.loads((DATA / "references.json").read_text(encoding="utf-8"))
