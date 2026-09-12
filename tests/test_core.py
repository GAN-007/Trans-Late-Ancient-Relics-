from app.eshb import encode, decode, encode_ipa, decode_ipa
from app.egyptian import mdc_to_transliteration, transliteration_to_mdc, hieroglyphize_phrase, parse_uniliterals
from app.translator import translate_word

def test_eshb_roundtrip():
    for text in ["HABARI", "NAIROBI", "KENYA", "SHUJAA", "CHAKULA"]:
        encoded=encode(text,"swahili")
        assert decode(encoded.strict)==text

def test_english_roundtrip():
    text="MY NAME IS GEORGE"
    encoded=encode(text,"english")
    assert decode(encoded.strict)==text

def test_ipa_roundtrip_basic():
    for ipa in ["hɑbari", "ɾa", "tʃai", "dʒa", "ŋa"]:
        encoded=encode_ipa(ipa)
        assert decode_ipa(encoded.strict)==ipa

def test_mdc():
    assert mdc_to_transliteration("sDm")=="sḏm"
    assert transliteration_to_mdc("sḏm")=="sDm"

def test_hieroglyphize_known():
    x=hieroglyphize_phrase("nfr")
    assert "𓄤" in x["hieroglyphs"]

def test_parse_uniliterals():
    x=parse_uniliterals("𓈖𓆑𓂋")
    assert x["transliteration"]=="nfr"

def test_dictionary_translation():
    x=translate_word("good","english","egyptian")
    assert x["ok"]
    assert x["transliteration"]=="nfr"


def test_learning_data_loaded():
    from app.egyptian import LEXICON
    from app.pedagogy import lessons
    assert len(LEXICON) >= 140
    assert len(lessons()) == 26
