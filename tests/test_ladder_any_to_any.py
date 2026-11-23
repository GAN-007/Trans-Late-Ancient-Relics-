"""Any language to any language: negation, questions, 'X is Y' sentences, honest gaps,
the modern-language bridge and quizzes on every rung."""
from __future__ import annotations

import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from app.ancient import bridge
from app.ancient.engine import LADDER_ORDER, LadderError, translate
from app.ancient.grammar import REALIZERS
from app.ancient.parsing import parse
from app.ancient.quiz import make_quiz, quiz_languages

SENTENCE_LANGUAGES = [lang for lang in LADDER_ORDER if lang not in {"proto_world", "archaic_hieroglyphic"}]
CONSONANTAL = {"safaitic", "early_arabic_rasm", "arabic_unvocalized"}


@pytest.fixture(autouse=True)
def env(monkeypatch, tmp_path):
    monkeypatch.setenv("ESHB_RUNTIME_DIR", str(tmp_path))
    monkeypatch.setenv("ESHB_DB_PATH", str(tmp_path / "test.sqlite3"))
    monkeypatch.setenv("ESHB_WARMUP", "false")
    for name in ("UNIVERSAL_MT_BASE_URL", "GOOGLE_CLOUD_TRANSLATE_API_KEY"):
        monkeypatch.delenv(name, raising=False)


def norm(frame):
    if not frame:
        return None
    frame = json.loads(json.dumps(frame))
    for np in (frame.get("object"), frame.get("np")):
        if isinstance(np, dict):
            np.pop("definite", None)
    for key in ("negative", "question"):
        if not frame.get(key):
            frame.pop(key, None)
    if frame.get("kind") == "identity":
        frame["subject"].pop("adj", None)
    return frame


def sentence_frames():
    frames = []
    for flags in ({}, {"negative": True}, {"question": True}, {"negative": True, "question": True}):
        for tense in ("past", "present"):
            for person in ("1s", "2ms", "3fs", "1p", "3p"):
                frames.append({"kind": "clause", "subject": {"person": person}, "verb": "see", "tense": tense,
                               "object": {"noun": "temple", "adj": None, "definite": True}, **flags})
            frames.append({"kind": "clause", "subject": {"person": "3ms", "noun": "scribe", "adj": None}, "verb": "write", "tense": tense,
                           "object": {"noun": "name", "adj": "great", "definite": True}, **flags})
            frames.append({"kind": "clause", "subject": {"person": "3fs", "noun": "woman", "adj": None}, "verb": "build", "tense": tense,
                           "object": {"noun": "house", "adj": None, "definite": True}, **flags})
        frames.append({"kind": "identity", "subject": {"person": "3ms", "noun": "king"}, "predicate": {"noun": "servant", "adj": None}, **flags})
        frames.append({"kind": "identity", "subject": {"person": "3ms", "noun": "sun"}, "predicate": {"noun": None, "adj": "great"}, **flags})
        frames.append({"kind": "identity", "subject": {"person": "1s"}, "predicate": {"noun": None, "adj": "good"}, **flags})
        frames.append({"kind": "identity", "subject": {"person": "2p"}, "predicate": {"noun": "scribe", "adj": None}, **flags})
    return frames


@pytest.mark.parametrize("lang", SENTENCE_LANGUAGES)
def test_every_sentence_type_reads_back_in_every_script(lang):
    """Whatever a language writes (transliteration or native script) reads back to the same meaning,
    so every language translates into every other through the shared meaning."""
    realizer = REALIZERS[lang]
    failures, checked = [], 0
    for frame in sentence_frames():
        out = realizer.realize(frame)
        if not out["ok"]:
            assert out["text"] == "" or out.get("refusal") or out["gaps"], (lang, frame, out["text"])
            continue
        for label, written in [("text", out["text"]), *out["scripts"].items()]:
            checked += 1
            parsed = parse(written, lang)
            if norm(parsed["frame"]) == norm(frame):
                continue
            if parsed["frame"] and realizer.realize(parsed["frame"])["text"] == out["text"]:
                continue  # a genuine homograph that writes the same sentence
            if label in CONSONANTAL and parsed["frame"] and parsed["frame"]["kind"] == frame["kind"]:
                continue  # unvowelled scripts cannot show person or tense
            if parsed["ambiguities"]:
                continue  # reported to the learner
            failures.append((label, written, frame, parsed["frame"]))
    assert checked > 10
    assert not failures, failures[:4]


def test_any_to_any_through_the_shared_meaning():
    english = "The scribe did not write the great name"
    meaning = translate(english, "english")["meaning"]
    assert meaning["negative"] is True
    for src in SENTENCE_LANGUAGES:
        written = REALIZERS[src].realize(meaning)
        if not written["ok"]:
            continue  # Proto-Semitic has no secure word for 'scribe': reported as a gap, not invented
        result = translate(written["text"], src, "all")
        for target, row in result["results"].items():
            assert row["text"] == REALIZERS[target].realize(meaning)["text"], (src, target)


@pytest.mark.parametrize("lang,frame,expected", [
    ("middle_egyptian", {"subject": {"person": "3ms", "noun": "king", "adj": None}, "verb": "see", "tense": "past", "negative": True}, "n mꜣ nswt"),
    ("middle_egyptian", {"subject": {"person": "3ms", "noun": "king", "adj": None}, "verb": "see", "tense": "present", "negative": True}, "n mꜣ.n nswt"),
    ("old_latin", {"subject": {"person": "3ms", "noun": "king", "adj": None}, "verb": "see", "tense": "past", "question": True}, "uiditne rex"),
    ("old_latin", {"subject": {"person": "3ms", "noun": "king", "adj": None}, "verb": "see", "tense": "past", "negative": True}, "rex non uidit"),
    ("old_arabic", {"subject": {"person": "3ms", "noun": "king", "adj": None}, "verb": "see", "tense": "past", "negative": True}, "mā raʾā al-maliku"),
    ("old_arabic", {"subject": {"person": "3ms", "noun": "king", "adj": None}, "verb": "see", "tense": "present", "negative": True}, "lā yarā al-maliku"),
    ("swahili", {"subject": {"person": "3ms", "noun": "king", "adj": None}, "verb": "see", "tense": "past", "negative": True}, "Mfalme hakuona"),
    ("swahili", {"subject": {"person": "1s"}, "verb": "go", "tense": "past", "negative": True}, "Sikwenda"),
    ("swahili", {"subject": {"person": "3fs", "noun": "woman", "adj": None}, "verb": "eat", "tense": "present", "negative": True}, "Mwanamke hali"),
    ("old_amharic", {"subject": {"person": "3ms", "noun": "king", "adj": None}, "verb": "see", "tense": "past", "negative": True}, "nəgusu ʾalayyäm"),
    ("geez", {"subject": {"person": "3ms", "noun": "king", "adj": None}, "verb": "make", "tense": "past", "negative": True, "question": True}, "ʾigabranu nəguś"),
    ("archaic_sumerian", {"subject": {"person": "3ms", "noun": "king", "adj": None}, "verb": "make", "tense": "past", "negative": True}, "lugal-e nu-mu-un-du3"),
    ("proto_semitic", {"subject": {"person": "3ms", "noun": "king", "adj": None}, "verb": "make", "tense": "past", "negative": True}, "*lā *ʕamala *malku"),
])
def test_negation_and_questions_use_each_languages_own_grammar(lang, frame, expected):
    out = REALIZERS[lang].realize({"kind": "clause", "object": None, **frame})
    assert out["ok"] and out["text"].rstrip("?") == expected


def test_nominal_sentences():
    sun = {"kind": "identity", "subject": {"person": "3ms", "noun": "sun"}, "predicate": {"noun": None, "adj": "great"}}
    expected = {"english": "The sun is great", "swahili": "Jua ni kubwa", "archaic_sumerian": "utu gal-am3", "old_latin": "sol magnos est",
                "old_arabic": "aš-šamsu kabīratun", "old_amharic": "ṣäḥayu təlləq näw", "middle_egyptian": "ꜥꜣ rꜥ", "geez": "ḍaḥāy ʿabiy wəʾətu"}
    for lang, text in expected.items():
        assert REALIZERS[lang].realize(sun)["text"] == text, lang
    negative = {"kind": "identity", "subject": {"person": "3ms", "noun": "king"}, "predicate": {"noun": None, "adj": "great"}, "negative": True}
    assert REALIZERS["old_arabic"].realize(negative)["text"] == "laysa al-maliku kabīran"  # accusative after laysa
    assert REALIZERS["old_amharic"].realize(negative)["text"] == "nəgusu təlləq ʾaydälläm"
    # No secure form: refused with a reason, never a guess
    for lang in ("archaic_sumerian", "geez", "middle_egyptian", "proto_semitic"):
        out = REALIZERS[lang].realize(negative)
        assert not out["ok"] and out["text"] == "" and out["refusal"], lang


def test_questions_are_punctuated_in_native_scripts():
    frame = {"kind": "clause", "subject": {"person": "3ms", "noun": "king", "adj": None}, "verb": "see", "tense": "past", "object": None, "question": True}
    assert REALIZERS["old_amharic"].realize(frame)["scripts"]["fidel"].endswith("፧")
    assert REALIZERS["old_arabic"].realize(frame)["scripts"]["arabic_unvocalized"].startswith("هل")
    assert REALIZERS["middle_egyptian"].realize(frame)["text"].startswith("jn ")


def test_arabic_particles_are_spelled_with_alif():
    frame = {"kind": "clause", "subject": {"person": "1s"}, "verb": "see", "tense": "present", "object": None, "negative": True}
    assert REALIZERS["old_arabic"].realize(frame)["scripts"]["arabic_unvocalized"].startswith("لا ")


def test_indefinite_arabic_object_reads_back():
    result = translate("ṣanaʿa al-maliku baytan kabīran", "old_arabic", "english")
    assert result["results"]["english"]["text"] == "The king made a great house"
    assert result["meaning"]["object"]["definite"] is False


@pytest.mark.parametrize("text,check", [
    ("I did not see the king", lambda f: f["negative"] and f["tense"] == "past"),
    ("Did the king see the river?", lambda f: f["question"] and f["subject"]["noun"] == "king"),
    ("She doesn't eat bread", lambda f: f["negative"] and f["tense"] == "present" and f["subject"]["person"] == "3fs"),
    ("Is the sun great?", lambda f: f["kind"] == "identity" and f["question"] and f["predicate"] == {"noun": None, "adj": "great"}),
    ("The king is not a servant", lambda f: f["kind"] == "identity" and f["negative"] and f["subject"]["noun"] == "king"),
    ("You are good", lambda f: f["kind"] == "identity" and f["subject"] == {"person": "2ms"}),
    ("We built the temple", lambda f: f["verb"] == "build" and f["object"]["noun"] == "temple"),
    ("I never saw the scribe", lambda f: f["negative"] and f["object"]["noun"] == "scribe"),
])
def test_english_reads_negation_questions_and_nominal_sentences(text, check):
    frame = parse(text, "english")["frame"]
    assert frame and check(frame), frame


def test_swahili_reads_negatives_questions_and_copula():
    assert parse("Mfalme hakuona mto", "swahili")["frame"]["negative"] is True
    assert parse("Je, nilijenga hekalu?", "swahili")["frame"]["question"] is True
    frame = parse("Jua ni kubwa", "swahili")["frame"]
    assert frame["kind"] == "identity" and frame["subject"]["noun"] == "sun" and frame["predicate"]["adj"] == "great"
    assert parse("Mimi si mtumishi", "swahili")["frame"]["negative"] is True
    assert parse("Wao hawaoni mto", "swahili")["frame"]["subject"]["person"] == "3p"


@pytest.mark.parametrize("text,left_out", [
    ("He gave bread to the woman", "'to the woman'"),
    ("The scribe wrote the name of the king", "'of the king'"),
    ("The gods heard the king", "plural 'gods'"),
    ("The king saw the spaceship", "'spaceship'"),
])
def test_nothing_is_dropped_silently(text, left_out):
    result = translate(text, "english")
    assert result["complete"] is False and left_out in result["warning"]


def test_complete_sentences_carry_no_warning():
    result = translate("The king did not build the temple", "english")
    assert result["complete"] is True and "warning" not in result


def test_new_vocabulary_is_aligned_across_the_ladder():
    result = translate("The scribe built the temple", "english")
    assert result["results"]["archaic_sumerian"]["text"] == "dub-sar-e eš3 mu-un-du3"
    assert result["results"]["middle_egyptian"]["text"] == "qd.n sš ḥwt-nṯr"
    assert result["results"]["old_egyptian"]["text"] == "qd.n zš ḥwt-nṯr"  # Old Egyptian keeps z
    assert result["results"]["proto_semitic"]["gaps"]  # no secure Proto-Semitic word for 'temple' or 'scribe'


# ------------------------------------------------------------------ modern bridge
def fake_mt(monkeypatch, table):
    calls = []

    async def mt(text, source, target):
        calls.append((text, source, target))
        return {"translation": table[(text, source, target)], "provider": "google-cloud"}
    monkeypatch.setattr(bridge, "_mt", mt)
    monkeypatch.setattr(bridge, "_mt_available", lambda: True)
    return calls


def test_modern_language_needs_a_translator():
    with pytest.raises(LadderError, match="UNIVERSAL_MT_BASE_URL"):
        asyncio.run(bridge.translate_any("Le roi a vu le fleuve", "french", ["archaic_sumerian"]))
    result = asyncio.run(bridge.translate_any("The king saw the river", "english", ["russian", "old_latin"]))
    assert result["results"]["old_latin"]["text"] == "rex flumen uidit"
    assert result["results"]["russian"]["ok"] is False and "UNIVERSAL_MT_BASE_URL" in result["results"]["russian"]["refusal"]


def test_french_to_sumerian_and_old_latin_to_chinese(monkeypatch):
    calls = fake_mt(monkeypatch, {
        ("Le roi n'a pas vu le fleuve", "fr", "en"): "The king did not see the river",
        ("The king did not see the river", "en", "zh"): "国王没有看见河",
    })
    result = asyncio.run(bridge.translate_any("Le roi n'a pas vu le fleuve", "French", ["archaic_sumerian", "chinese"]))
    assert result["bridge"]["english"] == "The king did not see the river"
    assert result["results"]["archaic_sumerian"]["text"] == "lugal-e id2 igi nu-mu-un-du8"
    assert result["results"]["chinese"]["text"] == "国王没有看见河" and result["results"]["chinese"]["status"] == "machine_translation"
    back = asyncio.run(bridge.translate_any("rex flumen non uidit", "old_latin", ["chinese"]))
    assert back["results"]["chinese"]["text"] == "国王没有看见河"
    assert calls[-1] == ("The king did not see the river", "en", "zh")


def test_modern_to_modern_is_direct(monkeypatch):
    fake_mt(monkeypatch, {("Guten Tag", "de", "he"): "שלום"})
    result = asyncio.run(bridge.translate_any("Guten Tag", "german", ["hebrew"]))
    assert result["results"]["hebrew"]["text"] == "שלום" and result["meaning"] is None


def test_language_resolution():
    assert bridge.resolve("Sumerian") == ("ladder", "archaic_sumerian")
    assert bridge.resolve("zh") == ("modern", "chinese")
    assert bridge.resolve("Hebrew") == ("modern", "hebrew")
    assert bridge.resolve("classical_latin") == ("modern", "classical_latin")
    with pytest.raises(LadderError):
        bridge.resolve("Klingon")


def test_api_lists_modern_languages_and_bridges(monkeypatch):
    from app.main import app
    fake_mt(monkeypatch, {("Мы построили храм", "ru", "en"): "We built the temple"})
    with TestClient(app) as client:
        langs = client.get("/api/ancient/languages").json()
        assert {"french", "german", "russian", "chinese", "hebrew"} <= {m["id"] for m in langs["modern_languages"]}
        response = client.post("/api/ancient/translate", json={"text": "Мы построили храм", "source": "russian", "targets": ["middle_egyptian"]})
        assert response.status_code == 200
        assert response.json()["results"]["middle_egyptian"]["text"] == "qd.n.n ḥwt-nṯr"
        assert client.post("/api/ancient/translate", json={"text": "x", "source": "klingon"}).status_code == 422


# ------------------------------------------------------------------ quizzes
@pytest.mark.parametrize("lang", [item["id"] for item in quiz_languages()])
def test_quiz_for_every_rung(lang):
    for explain in ("english", "swahili"):
        quiz = make_quiz(lang, explain, "mixed", 9, seed=7)
        assert len(quiz["questions"]) == (8 if lang == "proto_world" else 9)  # Proto-World has only 8 proposed roots
        for q in quiz["questions"]:
            assert q["answer"] in q["choices"] and len(set(q["choices"])) == len(q["choices"]) >= 2


def test_sentence_quiz_tests_reading_not_guessing():
    quiz = make_quiz("old_latin", "english", "sentence", 10, seed=11)
    assert len(quiz["questions"]) == 10
    for q in quiz["questions"]:
        assert q["kind"] == "sentence" and len(q["choices"]) == 4
        parsed = parse(q["prompt_text"], "old_latin")["frame"]
        assert REALIZERS["english"].realize(parsed)["text"] == q["answer"] or parse(q["prompt_text"], "old_latin")["ambiguities"]


def test_quiz_api_refuses_sentences_where_none_exist():
    from app.main import app
    with TestClient(app) as client:
        assert client.get("/api/ancient/quiz", params={"language": "sumerian", "mode": "sentence", "count": 3}).status_code == 200
        assert client.get("/api/ancient/quiz", params={"language": "proto_world", "mode": "sentence"}).status_code == 422


# ------------------------------------------------------------------ the live guide uses the same engine
def test_guide_tool_reports_gaps_and_bridges(monkeypatch):
    from app.avatar_chat import tools
    out = asyncio.run(tools.execute(None, "translate_ancient", {"text": "He gave bread to the woman", "source_language": "english", "target_languages": ["old_latin"]}))
    assert out.output["complete"] is False and "'to the woman'" in out.output["warning"]
    assert out.events[0]["card"]["warning"]
    fake_mt(monkeypatch, {("Le soleil est grand", "fr", "en"): "The sun is great"})
    out = asyncio.run(tools.execute(None, "translate_ancient", {"text": "Le soleil est grand", "source_language": "french", "target_languages": ["old_amharic"]}))
    assert out.output["translations"]["old_amharic"]["text"] == "ṣäḥayu təlləq näw" and out.output["bridge"]["from"] == "french"
