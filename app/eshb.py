from __future__ import annotations
import re
import unicodedata
from dataclasses import dataclass
from typing import Iterable

# ESHB = English/Swahili Hieroglyphic Bridge.
# Strict mode uses visible token separators so the mapping remains reversible.
CODEBOOK = {
    "A":"𓄿","B":"𓃀","C":"𓎡𓎡","D":"𓂧","E":"𓇋𓇋","F":"𓆑","G":"𓎼","H":"𓉔",
    "I":"𓇋","J":"𓆓","K":"𓎡","L":"𓃭","M":"𓅓","N":"𓈖","O":"𓅱𓄿","P":"𓊪",
    "Q":"𓈎","R":"𓂋","S":"𓋴","T":"𓏏","U":"𓅱","V":"𓆑𓆑","W":"𓅱𓅱","X":"𓎡𓋴",
    "Y":"𓇌","Z":"𓋴𓋴",
    "CH":"𓍿","SH":"𓈙","DH":"𓂧𓉔","TH":"𓏏𓉔","KH":"𓐍","GH":"𓎼𓉔",
    "NY":"𓈖𓇌","NG":"𓈖𓎼","NG'":"𓈖𓐍"
}
REVERSE = {v:k for k,v in CODEBOOK.items()}
DIGRAPHS = sorted([k for k in CODEBOOK if len(k) > 1], key=len, reverse=True)

WORD_SEP = " / "
TOKEN_SEP = "·"
ESCAPE_PREFIX = "§"

# Common IPA symbols used by English and Swahili. These are encoded into unique,
# explicit ESHB tokens. An arbitrary IPA symbol not listed is preserved using
# a reversible Unicode escape token.
IPA_TO_LABEL = {
    "p":"P","b":"B","t":"T","d":"D","k":"K","g":"G","f":"F","v":"V","s":"S","z":"Z",
    "ʃ":"SH","ʒ":"ZH","h":"H","m":"M","n":"N","ŋ":"NG'","ɲ":"NY","l":"L","r":"R","ɾ":"R",
    "j":"Y","w":"W","tʃ":"CH","dʒ":"J","θ":"TH","ð":"DH","x":"KH","ɣ":"GH",
    "i":"I","ɪ":"I_SHORT","e":"E","ɛ":"E_OPEN","æ":"AE","a":"A","ɑ":"A_BACK","ɒ":"O_SHORT",
    "ɔ":"O_OPEN","o":"O","ʊ":"U_SHORT","u":"U","ə":"SCHWA","ɜ":"ER","ʌ":"UH",
    "ː":"LENGTH","ˈ":"STRESS1","ˌ":"STRESS2",".":"SYLLABLE"
}
# Unique hieroglyph sequences for IPA-only labels that are not ordinary ESHB letters.
IPA_SPECIAL = {
    "ZH":"𓈙𓆓",
    "I_SHORT":"𓇋𓏏",
    "E_OPEN":"𓇋𓇋𓂝",
    "AE":"𓄿𓇋𓇋",
    "A_BACK":"𓄿𓂋",
    "O_SHORT":"𓅱𓄿𓏏",
    "O_OPEN":"𓅱𓄿𓂝",
    "U_SHORT":"𓅱𓏏",
    "SCHWA":"𓇋𓅱",
    "ER":"𓇋𓇋𓂋",
    "UH":"𓅱𓉔",
    "LENGTH":"𓏭𓏭",
    "STRESS1":"𓏭𓏏",
    "STRESS2":"𓏭𓂧",
    "SYLLABLE":"𓏭𓋴",
}
IPA_LABEL_TO_GLYPH = {**CODEBOOK, **IPA_SPECIAL}
GLYPH_TO_IPA_LABEL = {v:k for k,v in IPA_LABEL_TO_GLYPH.items()}
LABEL_TO_IPA = {}
for ipa, label in IPA_TO_LABEL.items():
    LABEL_TO_IPA.setdefault(label, ipa)

@dataclass
class ESHBResult:
    source: str
    strict: str
    display: str
    tokens: list[str]
    mode: str
    warnings: list[str]

def _clean_word(word: str) -> str:
    return unicodedata.normalize("NFC", word.upper())

def tokenize_orthography(text: str, language: str = "auto") -> list[list[str]]:
    """Tokenize English/Swahili orthography into reversible ESHB units."""
    words = re.findall(r"[A-Za-zÀ-ÖØ-öø-ÿ']+|[0-9]+|[^\w\s]", text, flags=re.UNICODE)
    out: list[list[str]] = []
    for raw in words:
        word = _clean_word(raw)
        if re.fullmatch(r"[0-9]+", word):
            out.append([f"{ESCAPE_PREFIX}N{d}" for d in word])
            continue
        if len(word) == 1 and not word.isalpha() and word != "'":
            out.append([f"{ESCAPE_PREFIX}P{ord(word):X}"])
            continue
        units: list[str] = []
        i = 0
        while i < len(word):
            matched = None
            # Swahili and phonetic-friendly digraphs are preferred.
            for dg in DIGRAPHS:
                if word.startswith(dg, i):
                    matched = dg
                    break
            if matched:
                units.append(matched)
                i += len(matched)
                continue
            ch = word[i]
            if ch in CODEBOOK:
                units.append(ch)
            elif ch == "'":
                units.append(f"{ESCAPE_PREFIX}APOS")
            else:
                units.append(f"{ESCAPE_PREFIX}U{ord(ch):X}")
            i += 1
        out.append(units)
    return out

def _unit_to_glyph(unit: str) -> str:
    if unit in CODEBOOK:
        return CODEBOOK[unit]
    # Escaped material is encoded as readable metadata in strict mode.
    return unit

def encode(text: str, language: str = "auto") -> ESHBResult:
    words = tokenize_orthography(text, language)
    strict_words, display_words, flat_tokens = [], [], []
    for units in words:
        glyph_units = [_unit_to_glyph(u) for u in units]
        strict_words.append(TOKEN_SEP.join(glyph_units))
        display_words.append("".join(g for g in glyph_units if not g.startswith(ESCAPE_PREFIX)))
        flat_tokens.extend(units)
    strict = WORD_SEP.join(strict_words)
    display = " ".join(display_words)
    return ESHBResult(text, strict, display, flat_tokens, "orthographic", [])

def decode(strict: str) -> str:
    """Decode strict ESHB. Display mode without separators is intentionally not guaranteed."""
    words = strict.split(WORD_SEP)
    decoded_words = []
    for word in words:
        pieces = [p for p in word.split(TOKEN_SEP) if p != ""]
        chars = []
        for p in pieces:
            if p in REVERSE:
                chars.append(REVERSE[p])
            elif p == f"{ESCAPE_PREFIX}APOS":
                chars.append("'")
            elif p.startswith(f"{ESCAPE_PREFIX}N") and p[2:].isdigit():
                chars.append(p[2:])
            elif p.startswith(f"{ESCAPE_PREFIX}P"):
                try:
                    chars.append(chr(int(p[2:], 16)))
                except ValueError:
                    chars.append("�")
            elif p.startswith(f"{ESCAPE_PREFIX}U"):
                try:
                    chars.append(chr(int(p[2:], 16)))
                except ValueError:
                    chars.append("�")
            else:
                chars.append("�")
        decoded_words.append("".join(chars))
    return " ".join(decoded_words)

def _longest_ipa_tokens(ipa: str) -> list[str]:
    ipa = unicodedata.normalize("NFC", ipa.strip())
    candidates = sorted(IPA_TO_LABEL.keys(), key=len, reverse=True)
    result = []
    i = 0
    while i < len(ipa):
        if ipa[i].isspace():
            result.append(" ")
            i += 1
            continue
        match = None
        for c in candidates:
            if ipa.startswith(c, i):
                match = c
                break
        if match is None:
            result.append(f"{ESCAPE_PREFIX}I{ord(ipa[i]):X}")
            i += 1
        else:
            result.append(match)
            i += len(match)
    return result

def encode_ipa(ipa: str) -> ESHBResult:
    tokens = _longest_ipa_tokens(ipa)
    strict_parts = []
    display_parts = []
    labels = []
    for token in tokens:
        if token == " ":
            strict_parts.append(WORD_SEP)
            display_parts.append(" ")
            continue
        if token.startswith(ESCAPE_PREFIX):
            strict_parts.append(token)
            labels.append(token)
            continue
        label = IPA_TO_LABEL[token]
        glyph = IPA_LABEL_TO_GLYPH.get(label)
        if glyph is None:
            escaped = f"{ESCAPE_PREFIX}I{ord(token[0]):X}"
            strict_parts.append(escaped)
            labels.append(escaped)
        else:
            strict_parts.append(glyph)
            display_parts.append(glyph)
            labels.append(label)
    strict = TOKEN_SEP.join(strict_parts).replace(TOKEN_SEP + WORD_SEP + TOKEN_SEP, WORD_SEP)
    strict = strict.replace(TOKEN_SEP + WORD_SEP, WORD_SEP).replace(WORD_SEP + TOKEN_SEP, WORD_SEP)
    return ESHBResult(ipa, strict, "".join(display_parts), labels, "ipa", [])

def decode_ipa(strict: str) -> str:
    words = strict.split(WORD_SEP)
    decoded_words = []
    for word in words:
        pieces = [p for p in word.split(TOKEN_SEP) if p]
        out = []
        for p in pieces:
            if p in GLYPH_TO_IPA_LABEL:
                label = GLYPH_TO_IPA_LABEL[p]
                out.append(LABEL_TO_IPA.get(label, f"<{label}>"))
            elif p.startswith(f"{ESCAPE_PREFIX}I"):
                try:
                    out.append(chr(int(p[2:], 16)))
                except ValueError:
                    out.append("�")
            else:
                out.append("�")
        decoded_words.append("".join(out))
    return " ".join(decoded_words)

def codebook_rows() -> list[dict]:
    return [{"unit":k, "glyph":v, "type":"digraph" if len(k)>1 else "letter"} for k,v in CODEBOOK.items()]
