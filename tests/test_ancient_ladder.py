"""Ancient Language Ladder: data integrity, scripts, grammar, any-to-any round trips and API."""
from __future__ import annotations

import unicodedata

import pytest
from fastapi.testclient import TestClient

from app.ancient import scripts
from app.ancient.engine import LADDER_ORDER, LadderError, concept_table, language_id, languages, translate
from app.ancient.grammar import REALIZERS
from app.ancient.lexicon import PERSONS, adjectives, nouns, verbs
from app.ancient.parsing import parse

SENTENCE_LANGUAGES = [lang for lang in LADDER_ORDER if lang not in {"proto_world", "archaic_hieroglyphic"}]
# Scripts that write no vowels cannot distinguish person or tense; they are checked for verb and object only.
CONSONANTAL_SCRIPTS = {"safaitic", "early_arabic_rasm", "arabic_unvocalized"}


@pytest.fixture(autouse=True)
def env(monkeypatch, tmp_path):
    monkeypatch.setenv("ESHB_RUNTIME_DIR", str(tmp_path))
    monkeypatch.setenv("ESHB_DB_PATH", str(tmp_path / "test.sqlite3"))
    monkeypatch.setenv("ESHB_AI_PROVIDER", "disabled")


# ------------------------------------------------------------------ data integrity
def test_every_cuneiform_and_hieroglyph_name_exists_in_unicode():
    for concept, item in {**nouns(), **adjectives()}.items():
        if item.get("sux"):
            assert scripts.cuneiform(item["sux"]["signs"]), concept
        if item.get("egy", {}).get("gl"):
            assert scripts.hieroglyphs(item["egy"]["gl"]), concept
    for concept, item in verbs().items():
        sux = item.get("sux")
        if sux:
            scripts.cuneiform(sux["signs"] + sux.get("pre_signs", []) + sux.get("maru_signs", []))
        if item["egy"].get("gl"):
            assert scripts.hieroglyphs(item["egy"]["gl"]), concept
    for name in scripts.SUMERIAN_AFFIX_SIGNS.values():
        scripts.cuneiform_sign(name)


def test_every_concept_has_english_swahili_and_core_ancient_forms():
    for concept, item in nouns().items():
        assert item["en"] and item["sw"]["f"], concept
        for code in ("sux", "la", "ar", "gez", "am"):
            assert item.get(code), (concept, code)
    for concept, item in verbs().items():
        for code in ("la", "ar", "gez", "am", "sem", "egy"):
            assert item.get(code), (concept, code)
        assert len(item["la"]["pres"]) == len(item["la"]["perf"]) == 6
        assert len(item["am"]["perf"]) == 8


def test_registry_lists_all_requested_languages():
    ids = {lang["id"] for lang in languages()}
    assert {"english", "swahili", "archaic_sumerian", "old_latin", "old_arabic", "geez", "old_amharic",
            "proto_semitic", "proto_world", "archaic_hieroglyphic", "old_egyptian", "middle_egyptian"} <= ids
    statuses = {lang["id"]: lang["status"] for lang in languages()}
    assert statuses["proto_semitic"] == "reconstructed"
    assert statuses["proto_world"] == "hypothetical"


def test_language_aliases():
    assert language_id("sw") == "swahili"
    assert language_id("Latin") == "old_latin"
    assert language_id("ge'ez") == "geez"
    assert language_id("proto-semitic") == "proto_semitic"
    with pytest.raises(LadderError):
        language_id("klingon")


# ------------------------------------------------------------------ scripts
def test_ethiopic_fidel_conversion():
    assert scripts.ethiopic_word("ʾamān") == "አማን"
    assert scripts.ethiopic_word("ʾamanku") == "አመንኩ"
    assert scripts.ethiopic_word("nəguś") == "ንጉሥ"
    assert scripts.ethiopic_word("ʾəwnät", amharic=True) == "እውነት"
    assert scripts.ethiopic_word("sämmahu", amharic=True) == "ሰማሁ"


def test_arabic_and_safaitic_skeletons():
    tokens = [{"text": "tawakkaltu"}, {"text": "ʿalā"}, {"text": "l-ḥaqqi"}]
    assert scripts.arabic_dotted(tokens) == "توكلت على الحق"
    assert scripts.arabic_rasm(tokens) == "ٮوكلٮ على الحٯ"
    safaitic = scripts.safaitic(tokens)
    assert all(unicodedata.name(ch).startswith("OLD NORTH ARABIAN") for ch in safaitic.replace(" ", ""))
    assert safaitic.split()[-1][0] == unicodedata.lookup("OLD NORTH ARABIAN LETTER HEH")  # h- article
    assert scripts.arabic_dotted([{"text": "al-marʾatu", "fem_noun": True}]) == "المرأة"


def test_old_italic_rendering():
    rendered = scripts.old_italic("credidei")
    assert all(unicodedata.name(ch).startswith("OLD ITALIC LETTER") for ch in rendered)


# ------------------------------------------------------------------ the user's sentence
def test_trust_sentence_across_every_language():
    result = translate("The truth, I have put my trust in", "english")
    assert result["meaning"] == {"kind": "clause", "subject": {"person": "1s"}, "verb": "trust", "tense": "past",
                                 "object": {"noun": "truth", "adj": None, "definite": True}}
    text = {lang: r["text"] for lang, r in result["results"].items()}
    assert text["old_latin"] == "ueritatei credidei"
    assert text["old_arabic"] == "tawakkaltu ʿalā l-ḥaqqi"
    assert text["geez"] == "tawakkalku ba-ʾamān"
    assert text["old_amharic"] == "bä-ʾəwnät ʾammänku"
    assert text["archaic_sumerian"] == "niĝ-gi-na-še3 šag4 mu-ĝal2"
    assert text["proto_semitic"] == "*ʔaminku *bi-ʔamāni"
    assert text["old_egyptian"] == "mḥ.n.j jb.j m mꜣꜥt"
    assert text["swahili"] == "Niliamini ukweli"
    assert result["results"]["archaic_sumerian"]["scripts"]["cuneiform"].startswith("𒃻𒄀𒈾")
    assert result["results"]["geez"]["scripts"]["fidel"] == "ተወከልኩ፡በአማን።"
    assert result["results"]["proto_world"]["ok"] is False and "refusal" in result["results"]["proto_world"]
    assert result["results"]["archaic_hieroglyphic"]["refusal"]
    assert result["results"]["proto_semitic"]["status"] == "reconstructed_composition"


def test_grammar_highlights():
    king_made = translate("The king made a great house", "english")["results"]
    assert king_made["archaic_sumerian"]["text"] == "lugal-e e2 gal mu-un-du3"   # ergative -e, mu-n- agent
    assert king_made["old_latin"]["text"].endswith("feced")                     # attested archaic perfect
    assert king_made["old_arabic"]["text"].startswith("ṣanaʿa al-maliku")        # VSO
    assert king_made["old_amharic"]["text"].endswith("särra")                   # SOV
    identity = translate("I am a king", "english")["results"]
    assert identity["archaic_sumerian"]["text"] == "lugal-me-en"
    assert identity["old_egyptian"]["text"] == "jnk nswt"
    assert identity["old_latin"]["text"] == "rex esom"
    assert identity["old_amharic"]["text"] == "ʾəne nəgus nəññ"
    sun = translate("The sun", "english")["results"]
    assert sun["old_arabic"]["text"] == "aš-šamsu"                             # sun-letter assimilation


def test_middle_egyptian_applies_z_to_s_merger():
    old = translate("I wrote", "english")["results"]
    assert old["old_egyptian"]["text"] == "zẖꜣ.n.j"
    assert old["middle_egyptian"]["text"] == "sẖꜣ.n.j"


def test_proto_world_gives_roots_only():
    water = translate("water", "english")["results"]["proto_world"]
    assert water["text"] == "*AKWA" and water["status"] == "hypothetical" and water["confidence"] <= 0.15
    assert translate("truth", "english")["results"]["proto_world"]["ok"] is False


# ------------------------------------------------------------------ parsing
@pytest.mark.parametrize("text,expected", [
    ("I trusted the truth", {"verb": "trust", "person": "1s", "tense": "past", "obj": "truth"}),
    ("She loves the king", {"verb": "love", "person": "3fs", "tense": "present", "obj": "king"}),
    ("We have seen the great mountain", {"verb": "see", "person": "1p", "tense": "past", "obj": "mountain"}),
    ("They went to the city", {"verb": "go", "person": "3p", "tense": "past", "obj": "city"}),
])
def test_english_parser(text, expected):
    frame = parse(text, "english")["frame"]
    assert frame["verb"] == expected["verb"] and frame["subject"]["person"] == expected["person"]
    assert frame["tense"] == expected["tense"] and frame["object"]["noun"] == expected["obj"]


def test_swahili_parser():
    frame = parse("Mfalme alipenda mwanamke mzuri", "swahili")["frame"]
    assert frame["subject"]["noun"] == "king" and frame["verb"] == "love" and frame["tense"] == "past"
    assert frame["object"] == {"noun": "woman", "adj": "good", "definite": True}
    assert parse("Tulikunywa maji", "swahili")["frame"]["subject"]["person"] == "1p"
    assert parse("Mimi ni mtumishi", "swahili")["frame"]["kind"] == "identity"


def test_unknown_input_is_reported_not_invented():
    result = translate("The spaceship hummed", "english")
    assert result["ok"] is False and "spaceship" in result["parse"]["unknown_words"]
    assert result["results"] == {}


def _frames():
    frames = []
    for verb in verbs():
        for person in PERSONS:
            for tense in ("past", "present"):
                frames.append({"kind": "clause", "subject": {"person": person}, "verb": verb, "tense": tense,
                               "object": {"noun": "house", "adj": None, "definite": True}})
    for noun in nouns():
        for adj in (None, *adjectives()):
            frames.append({"kind": "clause", "subject": {"person": "3fs" if noun in {"woman", "mother"} else "3ms", "noun": noun, "adj": adj},
                           "verb": "see", "tense": "past", "object": {"noun": "water", "adj": None, "definite": True}})
            frames.append({"kind": "identity", "subject": {"person": "2p"}, "predicate": {"noun": noun, "adj": adj}})
    return frames


@pytest.mark.parametrize("lang", SENTENCE_LANGUAGES)
def test_every_output_reads_back_to_the_same_sentence(lang):
    """Whatever a language writes, in transliteration or native script, it can read back.

    Equality is checked on the regenerated sentence, so genuine homographs (Latin 2nd-person
    forms without gender, Egyptian jr.n 'we make' / 'made by NOUN') count as correct when
    they denote the same written sentence. Logographic sign homographs (Sumerian AN = an / diĝir)
    are excluded from the strict check and reported as ambiguities instead.
    """
    realizer = REALIZERS[lang]
    failures = []
    for frame in _frames():
        out = realizer.realize(frame)
        if not out["ok"]:
            continue
        for label, written in [("text", out["text"]), *out["scripts"].items()]:
            parsed = parse(written, lang)
            back = parsed["frame"]
            if back is not None and realizer.realize(back)["text"] == out["text"]:
                continue
            if label in CONSONANTAL_SCRIPTS and back and back.get("kind") == frame["kind"]:
                continue
            if parsed["ambiguities"]:
                continue
            failures.append((label, written, frame, back))
    assert not failures, failures[:5]


@pytest.mark.parametrize("source", SENTENCE_LANGUAGES)
def test_any_to_any_through_every_pair(source):
    """Translate a sentence into the source language, then from it into every other language."""
    meaning = {"kind": "clause", "subject": {"person": "3ms", "noun": "king", "adj": None}, "verb": "love",
               "tense": "past", "object": {"noun": "mother", "adj": "good", "definite": True}}
    written = REALIZERS[source].realize(meaning)["text"]
    result = translate(written, source)
    assert result["meaning"] == meaning, (source, written, result["meaning"])
    for target, out in result["results"].items():
        if target in SENTENCE_LANGUAGES:
            assert out["ok"], (source, target, out)
            assert out["text"] == REALIZERS[target].realize(meaning)["text"]


def test_concept_table():
    table = concept_table("king")
    assert table["results"]["old_latin"]["text"] == "rex"
    assert table["results"]["archaic_sumerian"]["scripts"]["cuneiform"] == "𒈗"
    with pytest.raises(LadderError):
        concept_table("spaceship")


# ------------------------------------------------------------------ API
def test_api_endpoints():
    from app.main import app
    with TestClient(app) as client:
        _check_api(client)


def _check_api(client):
    langs = client.get("/api/ancient/languages").json()
    assert len(langs["languages"]) == len(LADDER_ORDER) == 13 and langs["coverage"]["concepts"]["verbs"] == len(verbs())
    response = client.post("/api/ancient/translate", json={"text": "ተወከልኩ፡በአማን።", "source": "geez", "targets": ["english", "sw"]})
    assert response.status_code == 200
    body = response.json()
    assert body["results"]["english"]["text"] == "I trusted in the truth"
    assert body["results"]["swahili"]["text"] == "Niliamini ukweli"
    assert client.post("/api/ancient/translate", json={"text": "hello", "source": "klingon"}).status_code == 422
    assert client.get("/api/ancient/concepts/water").json()["results"]["proto_world"]["text"] == "*AKWA"
    assert client.get("/api/capabilities").json()["features"]["ancient_language_ladder"] is True
