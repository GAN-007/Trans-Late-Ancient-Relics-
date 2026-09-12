from app.eshb import encode, decode, encode_ipa, decode_ipa
from app.egyptian import mdc_to_transliteration, transliteration_to_mdc, hieroglyphize_phrase, parse_uniliterals
from app.translator import translate_word, contextual_translate
from app.linguistics import analyze_morphology, classroom_pronunciation, detect_intent


def test_eshb_roundtrip():
    for text in ["HABARI", "NAIROBI", "KENYA", "SHUJAA", "CHAKULA"]:
        encoded = encode(text, "swahili")
        assert decode(encoded.strict) == text


def test_english_roundtrip():
    text = "MY NAME IS GEORGE"
    encoded = encode(text, "english")
    assert decode(encoded.strict) == text


def test_ipa_roundtrip_basic():
    for ipa in ["hɑbari", "ɾa", "rɑ", "tʃaŋa"]:
        encoded = encode_ipa(ipa)
        assert decode_ipa(encoded.strict) == ipa


def test_tap_and_trill_are_distinct():
    assert encode_ipa("ɾ").strict != encode_ipa("r").strict


def test_mdc():
    assert mdc_to_transliteration("sDm") == "sḏm"
    assert transliteration_to_mdc("sḏm") == "sDm"


def test_hieroglyphize_known():
    x = hieroglyphize_phrase("nfr")
    assert "𓄤" in x["hieroglyphs"]


def test_parse_uniliterals():
    x = parse_uniliterals("𓈖𓆑𓂋")
    assert x["transliteration"] == "nfr"


def test_dictionary_translation():
    x = translate_word("good", "english", "egyptian")
    assert x["ok"]
    assert x["transliteration"] == "nfr"
    assert x["exact_match"]


def test_contextual_translation_preserves_candidates():
    x = contextual_translate("I am a scribe", "english", "egyptian", context="self introduction")
    assert x["ok"]
    assert x["candidates"]
    assert x["intent_analysis"]["primary"] == "identity"


def test_unknown_sentence_is_not_faked():
    x = contextual_translate("quantum rockets remember tomorrow", "english", "egyptian")
    assert not x["ok"]
    assert x["mode"] == "analysis_only"


def test_morphology_suffix_pronoun():
    x = analyze_morphology("rn.j")
    assert x["words"][0]["stem"] == "rn"
    assert x["words"][0]["suffix_pronoun"]["person"] == "1sg"


def test_classroom_pronunciation_is_explicitly_conventional():
    x = classroom_pronunciation("nfr")
    assert x["classroom_reading"] == "nefer"
    assert x["historical_accuracy"] == "conventional_not_reconstructed"


def test_intent_detection_swahili():
    x = detect_intent("Habari, wewe ni nani?", "swahili")
    assert "greeting" in x["signals"]
    assert x["primary"] == "question"
