"""Restoration of damaged text with uncertainty distributions.

A lacuna is filled with a probability distribution, never with one silent guess. The model is an
interpolated trigram language model with Witten-Bell smoothing (Witten & Bell 1991; Chen & Goodman
1998) trained on the attestation database (TLA sentences when imported), the standard formulae,
the lesson examples and the teaching lexicon. Each gap is scored with its left and right context
in both directions, constrained by any visible letters and by the gap length, and returned as:

* the top candidates with probabilities,
* the probability left for "something else" (all other words, including unseen ones),
* the entropy of the distribution in bits,
* the evidence used (n-gram context or prior only).

Input conventions (Leiden system, as used by Egyptologists):
  [...] or [---]      lost, unknown length (1-3 words are considered)
  [2] / [-2-]         lost, two words
  n[...]  [...]r      partly preserved word: visible n at the start / r at the end
  [nfr]               restored by the editor: kept, but marked as restored
  ⸢nfr⸣               damaged but legible: kept
"""
from __future__ import annotations

import glob
import json
import math
import re
import unicodedata
from collections import Counter, defaultdict
from functools import lru_cache
from pathlib import Path
from typing import Any

DATA = Path(__file__).resolve().parent / "data"
BOS, EOS = "<s>", "</s>"
GAP_RX = re.compile(r"^(?P<pre>[^\[\]]*)\[(?P<body>[^\]]*)\](?P<post>[^\[\]]*)$")


def _norm(word: str) -> str:
    word = unicodedata.normalize("NFC", word.strip()).replace("⸢", "").replace("⸣", "")
    return word.replace("i̯", "j").replace("ꞽ", "j").replace("=", ".")


class TrigramModel:
    def __init__(self, sentences: list[list[str]], prior: Counter):
        self.uni: Counter = Counter()
        self.bi: dict[str, Counter] = defaultdict(Counter)
        self.tri: dict[tuple[str, str], Counter] = defaultdict(Counter)
        for words in sentences:
            seq = [BOS, BOS, *words, EOS]
            for i in range(2, len(seq)):
                self.uni[seq[i]] += 1
                self.bi[seq[i - 1]][seq[i]] += 1
                self.tri[(seq[i - 2], seq[i - 1])][seq[i]] += 1
        self.prior = prior
        self.vocab = sorted(set(self.uni) | set(prior) - {EOS})
        self.total = sum(self.uni.values())
        # unseen-word mass: Witten-Bell estimate at the unigram level, kept for "something else"
        self.p_unseen = len(self.uni) / (self.total + len(self.uni)) if self.total else 1.0
        self.sentences = len(sentences)

    def _unigram(self, w: str) -> float:
        seen = (self.uni[w] + 0.5 * self.prior.get(w, 0)) / (self.total + 0.5 * sum(self.prior.values()) or 1)
        return (1 - self.p_unseen) * seen + self.p_unseen / (len(self.vocab) + 1)

    def _wb(self, counts: Counter, w: str, lower: float) -> float:
        n, types = sum(counts.values()), len(counts)
        if n == 0:
            return lower
        lam = n / (n + types)
        return lam * counts[w] / n + (1 - lam) * lower

    def prob(self, w: str, h2: str, h1: str) -> float:
        p1 = self._unigram(w)
        p2 = self._wb(self.bi.get(h1, Counter()), w, p1)
        return self._wb(self.tri.get((h2, h1), Counter()), w, p2)

    def evidence(self, h2: str, h1: str, w: str) -> str:
        if self.tri.get((h2, h1), Counter())[w]:
            return "trigram"
        if self.bi.get(h1, Counter())[w]:
            return "bigram"
        if self.uni[w]:
            return "unigram"
        return "lexicon prior"


@lru_cache(maxsize=1)
def model() -> TrigramModel:
    sentences: list[list[str]] = []
    formulae = json.loads((DATA / "corpus" / "formulae.json").read_text(encoding="utf-8"))
    for phrase in formulae["phrases"]:
        sentences.append([_norm(w) for w in phrase["text"].split()])
    for path in sorted(glob.glob(str(DATA / "lessons" / "*.json"))):
        for lesson in json.loads(Path(path).read_text(encoding="utf-8")):
            for value in lesson.values():
                for item in value if isinstance(value, list) else []:
                    if isinstance(item, dict) and item.get("transliteration") and " " in item["transliteration"]:
                        sentences.append([_norm(w) for w in item["transliteration"].split()])
    try:  # attested sentences from the corpus database (grows when the full TLA corpus is imported)
        from .corpus.store import _rows, ensure_bundled
        ensure_bundled()
        for row in _rows("SELECT transliteration FROM corpus_sentences WHERE transliteration IS NOT NULL"):
            words = [_norm(w) for w in row["transliteration"].split() if w.strip()]
            if words:
                sentences.append(words)
    except Exception:  # the database is optional for restoration
        pass
    prior: Counter = Counter()
    for path in sorted((DATA / "lexicon").glob("*.json")):
        for entry in json.loads(path.read_text(encoding="utf-8")):
            if entry.get("transliteration"):
                prior[_norm(entry["transliteration"])] += 1
    return TrigramModel(sentences, prior)


def reset() -> None:
    model.cache_clear()


def _parse(text: str) -> list[dict[str, Any]]:
    tokens = []
    for raw in text.split():
        m = GAP_RX.match(raw)
        if not m:
            tokens.append({"kind": "word", "text": _norm(raw), "damaged": "⸢" in raw})
            continue
        pre, body, post = _norm(m.group("pre")), m.group("body").strip(), _norm(m.group("post"))
        count = re.sub(r"[^0-9]", "", body)
        if body and not re.fullmatch(r"[.\-–—\s0-9?…]*", body):  # [nfr] = editor's restoration
            tokens.append({"kind": "word", "text": pre + _norm(body) + post, "restored_by_editor": True})
        elif pre or post:
            tokens.append({"kind": "partial", "pre": pre, "post": post})
        else:
            tokens.append({"kind": "gap", "length": int(count) if count else None})
    return tokens


def _candidates(m: TrigramModel, left: list[str], right: list[str], pre: str = "", post: str = "") -> list[tuple[str, float, str]]:
    h2, h1 = (left[-2] if len(left) > 1 else BOS), (left[-1] if left else BOS)
    scored = []
    for w in m.vocab:
        if w in (BOS, EOS) or not w.startswith(pre) or not w.endswith(post) or len(w) < len(pre) + len(post):
            continue
        p = m.prob(w, h2, h1)
        r1 = right[0] if right else EOS
        p *= m.prob(r1, h1, w)
        if len(right) > 1:
            p *= m.prob(right[1], w, r1)
        scored.append((w, p, m.evidence(h2, h1, w) if m.evidence(h2, h1, w) != "lexicon prior" else
                       ("bigram (right context)" if m.bi.get(w, Counter())[r1] else m.evidence(h2, h1, w))))
    return scored


def _distribution(scored: list[tuple[str, float, str]], unseen: float, top: int) -> dict[str, Any]:
    total = sum(p for _, p, _ in scored)
    if total <= 0:
        return {"candidates": [], "other": 1.0, "entropy_bits": None}
    # reserve the model's unseen-word mass for words it has never seen
    probs = [(w, (1 - unseen) * p / total, ev) for w, p, ev in scored]
    probs.sort(key=lambda x: -x[1])
    entropy = -sum(p * math.log2(p) for _, p, _ in probs if p > 0) - (unseen * math.log2(unseen) if unseen > 0 else 0)
    # candidates below half a percent are noise for a reader; their mass stays in "other"
    best = [x for x in probs[:top] if x[1] >= 0.005] or probs[:1]
    return {"candidates": [{"text": w, "probability": round(p, 4), "evidence": ev} for w, p, ev in best],
            "other": round(1 - sum(p for _, p, _ in best), 4), "entropy_bits": round(entropy, 3)}


def restore(text: str, top: int = 5) -> dict[str, Any]:
    """Fill each lacuna with a probability distribution over restorations."""
    m = model()
    tokens = _parse(text)
    if not any(t["kind"] in {"gap", "partial"} for t in tokens):
        return {"text": text, "gaps": [], "note": "No lacuna found. Mark lost text with [...] (Leiden conventions)."}
    gaps = []
    for index, token in enumerate(tokens):
        if token["kind"] not in {"gap", "partial"}:
            continue
        left = [t["text"] for t in tokens[:index] if t["kind"] == "word"][-2:]
        right = [t["text"] for t in tokens[index + 1:] if t["kind"] == "word"][:2]
        if token["kind"] == "partial":
            dist = _distribution(_candidates(m, left, right, token["pre"], token["post"]), m.p_unseen, top)
            gaps.append({"position": index, "kind": "partly preserved", "visible": {"start": token["pre"], "end": token["post"]}, **dist})
            continue
        lengths = [token["length"]] if token["length"] else [1, 2, 3]
        options = []
        for n in lengths:
            if n == 1:
                for w, p, ev in _candidates(m, left, right):
                    options.append(([w], p, ev))
            else:
                # beam search over n words, keeping the 40 best partial sequences
                beam = [([], 1.0)]
                for step in range(n):
                    nxt = []
                    for seq, p in beam:
                        ctx = (left + seq)[-2:]
                        h2, h1 = (ctx[-2] if len(ctx) > 1 else BOS), (ctx[-1] if ctx else BOS)
                        for w in m.vocab:
                            if w in (BOS, EOS):
                                continue
                            nxt.append((seq + [w], p * m.prob(w, h2, h1)))
                    beam = sorted(nxt, key=lambda x: -x[1])[:40]
                for seq, p in beam:
                    ctx = (left + seq)[-2:]
                    r1 = right[0] if right else EOS
                    options.append((seq, p * m.prob(r1, ctx[-2] if len(ctx) > 1 else BOS, ctx[-1]), "sequence"))
            # a longer gap must pay for its extra words, so lengths compete fairly
        scored = [(" ".join(seq), p, ev) for seq, p, ev in options]
        merged: dict[str, tuple[float, str]] = {}
        for w, p, ev in scored:
            merged[w] = (merged.get(w, (0.0, ev))[0] + p, ev)
        dist = _distribution([(w, p, ev) for w, (p, ev) in merged.items()], m.p_unseen, top)
        gaps.append({"position": index, "kind": "lost", "length": token["length"] or "unknown (1-3 words considered)", **dist})
    return {"text": text, "gaps": gaps, "model": info(),
            "note": "Probabilities come from a trigram model of the bundled and imported texts; 'other' is the probability that "
                    "the lost text is something not listed, including words the model has never seen. Treat restorations as "
                    "hypotheses to check against parallels, sign traces and the space on the object."}


def info() -> dict[str, Any]:
    m = model()
    return {"type": "interpolated trigram, Witten-Bell smoothing", "training_sentences": m.sentences, "vocabulary": len(m.vocab),
            "unseen_word_mass": round(m.p_unseen, 4)}


def evaluate(max_items: int = 400) -> dict[str, Any]:
    """Leave-one-word-out evaluation on the training sentences: top-1/top-5 accuracy and calibration (ECE)."""
    m = model()
    sentences = []
    formulae = json.loads((DATA / "corpus" / "formulae.json").read_text(encoding="utf-8"))
    sentences += [[_norm(w) for w in p["text"].split()] for p in formulae["phrases"]]
    items = [(s, i) for s in sentences for i in range(len(s))][:max_items]
    hits1 = hits5 = 0
    bins: dict[int, list[tuple[float, int]]] = defaultdict(list)
    for words, i in items:
        dist = _distribution(_candidates(m, words[max(0, i - 2):i], words[i + 1:i + 3]), m.p_unseen, 5)
        cands = [c["text"] for c in dist["candidates"]]
        correct = int(bool(cands) and cands[0] == words[i])
        hits1 += correct
        hits5 += int(words[i] in cands)
        if dist["candidates"]:
            conf = dist["candidates"][0]["probability"]
            bins[min(9, int(conf * 10))].append((conf, correct))
    n = len(items) or 1
    ece = sum(len(b) / n * abs(sum(c for c, _ in b) / len(b) - sum(k for _, k in b) / len(b)) for b in bins.values() if b)
    return {"items": len(items), "top1": round(hits1 / n, 3), "top5": round(hits5 / n, 3), "expected_calibration_error": round(ece, 3),
            "caveat": "Measured on the formulae the model was trained on (in-sample), so it is an upper bound; import the TLA "
                      "corpus and evaluate on held-out texts for a real estimate."}
