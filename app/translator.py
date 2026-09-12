from __future__ import annotations
import re
import unicodedata
from .egyptian import LEXICON, search_dictionary, hieroglyphize_phrase

def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", text.strip().lower()))

def _index(language: str):
    idx = {}
    for e in LEXICON:
        for gloss in e.get(language, []):
            idx.setdefault(_normalize(gloss), []).append(e)
    return idx

EN = _index("english")
SW = _index("swahili")

PHRASE_TEMPLATES = [
    {
        "name":"identity_i_am",
        "english":re.compile(r"^i am (?:a |an )?(.+)$", re.I),
        "swahili":re.compile(r"^(?:mimi )?ni (.+)$", re.I),
        "builder":lambda x: f"jnk {x}",
        "explanation":"Independent pronoun jnk followed by a nominal predicate.",
    },
    {
        "name":"my_name",
        "english":re.compile(r"^my name is (.+)$", re.I),
        "swahili":re.compile(r"^jina langu ni (.+)$", re.I),
        "builder":lambda x: f"rn.j pw {x}",
        "explanation":"Pedagogical nominal pattern using rn.j 'my name' and pw. Proper names are preserved for separate name transcription.",
    },
    {
        "name":"house_is_good",
        "english":re.compile(r"^the house is (good|beautiful)$", re.I),
        "swahili":re.compile(r"^nyumba ni (nzuri|rembo)$", re.I),
        "builder":lambda x: "nfr pr",
        "explanation":"Illustrative adjectival-predicate pattern. Exact syntax must be checked against period and discourse context.",
    },
    {
        "name":"in_the_house",
        "english":re.compile(r"^in the house$", re.I),
        "swahili":re.compile(r"^(?:ndani ya|katika) nyumba$", re.I),
        "builder":lambda x: "m pr",
        "explanation":"Preposition m + noun pr.",
    },
    {
        "name":"to_the_town",
        "english":re.compile(r"^(?:to|toward) the (?:town|city)$", re.I),
        "swahili":re.compile(r"^kuelekea (?:mjini|mji|jijini|jiji)$", re.I),
        "builder":lambda x: "r njwt",
        "explanation":"Preposition r + noun njwt.",
    },
]

def _best_lexeme(term: str, language: str):
    q = _normalize(term)
    idx = EN if language == "english" else SW
    if q in idx:
        return idx[q][0]
    candidates = search_dictionary(term, language=language, limit=10)
    return candidates[0] if candidates else None

def translate_word(text: str, source: str, target: str="egyptian") -> dict:
    entry = _best_lexeme(text, source)
    if not entry:
        return {"ok":False,"source":text,"source_language":source,"target_language":target,"message":"No secure lexicon entry found. The system refuses to invent an Ancient Egyptian word.","confidence":0.0}
    if target == "egyptian":
        rendered = hieroglyphize_phrase(entry["transliteration"])
        return {"ok":True,"source":text,"source_language":source,"target_language":"middle_egyptian","transliteration":entry["transliteration"],"hieroglyphs":rendered["hieroglyphs"],"english":entry.get("english",[]),"swahili":entry.get("swahili",[]),"pos":entry.get("pos"),"notes":entry.get("notes"),"confidence":0.95 if entry.get("confidence")=="high" else 0.75,"mode":"dictionary"}
    values = entry.get(target, [])
    return {"ok":True,"source":text,"target_language":target,"translations":values,"entry":entry,"confidence":0.9}

def translate_phrase(text: str, source: str) -> dict:
    normalized = _normalize(text)
    for template in PHRASE_TEMPLATES:
        rx = template.get(source)
        if rx:
            m = rx.match(normalized)
            if m:
                captured = m.group(1) if m.groups() else ""
                if template["name"] == "identity_i_am":
                    lexical = _best_lexeme(captured, source)
                    if not lexical:
                        return {"ok":False,"source":text,"message":f"The predicate '{captured}' is not in the curated lexicon, so the historical translation is not guessed.","confidence":0.0}
                    translit = template["builder"](lexical["transliteration"])
                else:
                    translit = template["builder"](captured)
                rendered = hieroglyphize_phrase(translit)
                return {"ok":True,"source":text,"source_language":source,"transliteration":translit,"hieroglyphs":rendered["hieroglyphs"],"analysis":template["explanation"],"mode":"grammar_template","confidence":0.75,"warning":"Pedagogical translation, not a claim that every discourse context would use exactly this construction."}
    tokens = re.findall(r"[\wꜣꜥḥḫẖšṯḏ'-]+", normalized, flags=re.UNICODE)
    resolved = []
    unresolved = []
    for tok in tokens:
        e = _best_lexeme(tok, source)
        if e:
            resolved.append({"source":tok,"transliteration":e["transliteration"],"entry":e})
        else:
            unresolved.append(tok)
    return {"ok":False,"source":text,"source_language":source,"mode":"analysis_only","resolved":resolved,"unresolved":unresolved,"message":"The sentence does not match a verified grammar template. Lexical candidates are shown, but the system will not pretend that word substitution is an authentic Egyptian translation.","confidence":0.0}

def egyptian_to_modern(transliteration: str, target: str="english") -> dict:
    words = [w for w in re.split(r"\s+", transliteration.strip()) if w]
    output = []
    ambiguity = []
    for word in words:
        base = word.split(".")[0]
        matches = [e for e in LEXICON if e["transliteration"].lower() == base.lower()]
        if not matches:
            output.append(f"[{word}]")
            continue
        senses = []
        for e in matches:
            senses += e.get(target, [])
        senses = list(dict.fromkeys(senses))
        output.append(senses[0] if senses else f"[{word}]")
        if len(senses)>1:
            ambiguity.append({"word":word,"senses":senses})
    return {"source":transliteration,"target_language":target,"literal_gloss":" ".join(output),"ambiguity":ambiguity,"warning":"This is a lexical gloss. A proper historical translation requires morphological and syntactic parsing before choosing final English/Swahili wording."}
