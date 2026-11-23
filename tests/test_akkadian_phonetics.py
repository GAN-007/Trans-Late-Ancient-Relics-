"""Old Akkadian as its own rung (Sumerian untouched) and pronunciation for every rung."""
from __future__ import annotations

import re

import pytest

from app.ancient import scripts
from app.ancient.engine import LADDER_ORDER, translate
from app.ancient.grammar import REALIZERS
from app.ancient.lexicon import adjectives, nouns, verbs
from app.ancient.parsing import _synthetic_frames
from app.ancient.phonetics import pronounce, speakable
from app.ancient.quiz import make_quiz

AKK = REALIZERS["old_akkadian"]


def test_akkadian_is_its_own_rung_next_to_sumerian():
    assert LADDER_ORDER.index("old_akkadian") == LADDER_ORDER.index("archaic_sumerian") + 1
    assert AKK.family.startswith("Afro-Asiatic") and REALIZERS["archaic_sumerian"].family == "Language isolate"
    for kind in (nouns(), adjectives(), verbs()):
        assert all("akk" in entry for entry in kind.values())
    for verb in verbs().values():
        assert len(verb["akk"]["past"]) == 8 and len(verb["akk"]["present"]) == 8


@pytest.mark.parametrize("english,sumerian", [
    ("The king made a great house", "lugal-e e2 gal mu-un-du3"),
    ("The truth, I have put my trust in", "niĝ-gi-na-še3 šag4 mu-ĝal2"),
    ("I am a servant", "arad-me-en"),
    ("We went to the city", "uru-še3 ba-ĝen-en-de3-en"),
])
def test_sumerian_is_unchanged(english, sumerian):
    assert translate(english, "english", ["archaic_sumerian"])["results"]["archaic_sumerian"]["text"] == sumerian


@pytest.mark.parametrize("english,akkadian,signs", [
    ("The king made a great house", "šarrum bītam rabiam īpuš", "ša-ar-ru-um bi-ta-am ra-bi-am i-pu-uš"),
    ("I did not see the king", "šarram ula āmur", "ša-ar-ra-am u-la a-mu-ur"),
    ("The woman wrote the name", "sinništum šumam tašṭur", "si-in-ni-iš-tu-um šu-ma-am ta-aš-ṭu-ur"),
    ("We went to the city", "ana ālim nillik", "a-na a-li-im ni-il-li-ik"),
    ("The sun is great", "šamšum rabi", "ša-am-šu-um ra-bi"),
    ("I am good", "damqāku", "da-am-qa-ku"),
    ("I am a servant", "anāku wardum", "a-na-ku wa-ar-du-um"),
    ("The scribe builds the temple", "ṭupšarrum ekurram ibanni", "ṭu-up-ša-ar-ru-um e-ku-ur-ra-am i-ba-an-ni"),
    ("The water is good", "mû damqū", "mu da-am-qu"),
    ("I trusted the truth", "ana kittim atkal", "a-na ki-it-ti-im at-ka-al"),
])
def test_akkadian_grammar(english, akkadian, signs):
    row = translate(english, "english", ["old_akkadian"])["results"]["old_akkadian"]
    assert row["ok"] and row["text"] == akkadian
    assert row["scripts"]["sign_reading"] == signs and row["scripts"]["cuneiform"]


def test_old_akkadian_features():
    she = AKK.realize({"kind": "clause", "subject": {"person": "3fs"}, "verb": "see", "tense": "past", "object": None})
    assert she["text"] == "tāmur"  # Old Akkadian 3rd feminine ta- (Old Babylonian īmur)
    assert AKK.realize({"kind": "word", "word_kind": "verb", "concept": "build"})["text"] == "banûm"  # infinitive = dictionary form
    negative = AKK.realize({"kind": "identity", "subject": {"person": "3ms", "noun": "king"}, "predicate": {"noun": None, "adj": "great"}, "negative": True})
    assert negative["ok"] and negative["text"] == "šarrum ula rabi"  # stative negated, no refusal needed


def test_every_akkadian_form_has_a_cuneiform_spelling():
    """The form index skips forms it cannot render, so check every one explicitly."""
    missing = set()
    for frame in _synthetic_frames("old_akkadian"):
        for token in AKK.tokens_for(frame):
            if token.is_gap:
                continue
            for word in token.text.split():
                try:
                    scripts.akkadian_cuneiform(word)
                except KeyError as exc:
                    missing.add((word, str(exc)))
    assert not missing, sorted(missing)[:10]


@pytest.mark.parametrize("written", [
    "šarrum bītam rabiam īpuš",
    "sarrum bitam rabiam ipus",                         # without diacritics
    "ša-ar-ru-um bi-ta-am ra-bi-am i-pu-uš",            # sign-by-sign transliteration, as in textbooks
    "𒊭𒅈𒊒𒌝 𒁉𒋫𒄠 𒊏𒁉𒄠 𒄿𒁍𒍑",                              # cuneiform
])
def test_akkadian_reads_back_in_every_form(written):
    result = translate(written, "old_akkadian", ["english", "archaic_sumerian", "swahili"])
    assert result["results"]["english"]["text"] == "The king made the great house"  # Akkadian has no articles
    assert result["results"]["archaic_sumerian"]["text"] == "lugal-e e2 gal mu-un-du3"


def test_pasted_akkadian_cuneiform_is_read_as_a_lesson_but_sumerian_keeps_priority():
    from app.avatar_chat.reading import read_text
    akk = read_text("𒊭𒅈𒊒𒌝 𒁉𒋫𒄠 𒊏𒁉𒄠 𒄿𒁍𒍑", "english")
    assert akk["language"] == "old_akkadian" and akk["translation"]["english"] == "The king made the great house"
    assert akk["segments"][0]["pronunciation"] == "SHAR-rum"
    sux = read_text("𒈗𒂊 𒂍 𒃲 𒈬𒌦𒆕", "english")
    assert sux["language"] == "archaic_sumerian"


# ------------------------------------------------------------------ pronunciation
@pytest.mark.parametrize("lang,text,say", [
    ("old_akkadian", "šarrum", "SHAR-rum"),
    ("old_akkadian", "damqāku", "dam-KAA-ku"),
    ("old_akkadian", "irâm", "i-RAAM"),
    ("archaic_sumerian", "niĝ-gi-na", "ning-gi-na"),
    ("archaic_sumerian", "lugal-e", "lu-ga-le"),
    ("middle_egyptian", "ꜥnḫ nfr", "ankh nefer"),
    ("old_latin", "uidit", "wi-dit"),
    ("old_arabic", "tawakkaltu ʿalā l-ḥaqqi", "ta-wak-KAL-tu ’A-laal HAK-ki"),
    ("swahili", "Mfalme hakuona mto", "m-FAL-me ha-koo-O-na M-to"),
    ("swahili", "nyumba", "NYOO-mba"),
    ("old_amharic", "ʾaydälläm", "’ay-del-lem"),
])
def test_pronunciation(lang, text, say):
    assert pronounce(lang, text)["say"] == say


@pytest.mark.parametrize("lang", [lang for lang in LADDER_ORDER if lang != "english"])
def test_every_word_on_every_rung_can_be_said(lang):
    """Every form has a respelling made of plain letters a voice can read, and states its certainty."""
    realizer = REALIZERS[lang]
    bad = []
    for kind, table in (("noun", nouns()), ("adj", adjectives()), ("verb", verbs())):
        for concept in table:
            out = realizer.realize({"kind": "word", "word_kind": kind, "concept": concept})
            if not out["ok"]:
                continue
            p = out["pronunciation"]
            if not p or not p["say"] or not re.fullmatch(r"[A-Za-z’' -]+", p["say"]) or not p["note"]:
                bad.append((concept, out["text"], p))
    assert not bad, bad[:5]


def test_old_latin_stress_is_not_guessed():
    assert pronounce("old_latin", "amauet")["say"] == "a-ma-wet"  # vowel length unwritten, so no stress is claimed


def test_results_tokens_and_quizzes_carry_pronunciation():
    row = translate("The king made a great house", "english", ["old_akkadian"])["results"]["old_akkadian"]
    assert row["pronunciation"]["ipa"].startswith("/ˈʃar.rum") and row["pronunciation"]["system"] == "reconstructed"
    assert [t["say"] for t in row["tokens"]] == ["SHAR-rum", "BEE-tam", "RA-bi-am", "EE-push"]
    quiz = make_quiz("old_akkadian", "english", "meaning", 5, seed=1)
    assert all(q["pronunciation"]["say"] for q in quiz["questions"])
    assert speakable("archaic_sumerian", "lugal-e") == "lu-ga-le" and speakable("swahili", "Mfalme") == "Mfalme"
