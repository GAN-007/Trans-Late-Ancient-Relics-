"""Artifact-level translation evaluation in English and Swahili.

A benchmark is a list of artifacts (a stela, an ostracon, a papyrus column), each with its
provenance and its lines, and reference translations in English and Swahili with a review
status. Systems are scored per line, then per artifact, and the headline number is the mean
over artifacts, so one long papyrus cannot hide failures on many short inscriptions.

Metrics: chrF and chrF++ (character n-gram F-score with β = 2, word bigrams for ++; Popović
2015, 2017), exact match, and coverage (share of lines the system produced anything for).
References marked "draft" are reported separately from expert-reviewed ones.
"""
from __future__ import annotations

import json
import re
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any, Callable

DATA = Path(__file__).resolve().parent / "data" / "eval"
LANGS = ("english", "swahili")


def _clean(text: str) -> str:
    text = unicodedata.normalize("NFC", (text or "").lower())
    text = re.sub(r"[\(\)\[\]⸢⸣〈〉\"“”'’.,;:!?«»]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _char_ngrams(text: str, n: int) -> Counter:
    s = text.replace(" ", "")
    return Counter(s[i:i + n] for i in range(len(s) - n + 1))


def _word_ngrams(text: str, n: int) -> Counter:
    w = text.split()
    return Counter(tuple(w[i:i + n]) for i in range(len(w) - n + 1))


def chrf(hypothesis: str, reference: str, char_order: int = 6, word_order: int = 0, beta: float = 2.0) -> float:
    """chrF (word_order=0) or chrF++ (word_order=2), 0-100, as defined by Popović (WMT 2015/2017)."""
    hyp, ref = _clean(hypothesis), _clean(reference)
    if not hyp or not ref:
        return 0.0
    precisions, recalls = [], []
    orders = [(_char_ngrams, n) for n in range(1, char_order + 1)] + [(_word_ngrams, n) for n in range(1, word_order + 1)]
    for fn, n in orders:
        h, r = fn(hyp, n), fn(ref, n)
        if not h or not r:
            continue
        match = sum((h & r).values())
        precisions.append(match / sum(h.values()))
        recalls.append(match / sum(r.values()))
    if not precisions:
        return 0.0
    p, r = sum(precisions) / len(precisions), sum(recalls) / len(recalls)
    if p + r == 0:
        return 0.0
    return round(100 * (1 + beta ** 2) * p * r / (beta ** 2 * p + r), 2)


def load_benchmark(path: str | Path | None = None) -> dict[str, Any]:
    path = Path(path) if path else DATA / "artifact_benchmark.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    for artifact in data["artifacts"]:
        for key in ("id", "provenance", "language", "lines"):
            if key not in artifact:
                raise ValueError(f"Artifact is missing '{key}': {artifact.get('id')}")
    return data


# ------------------------------------------------------------------ systems
def system_app(line: dict[str, Any], language: str, target: str) -> str:
    """The platform's own deterministic translators (no model): ladder grammar or the Egyptian lexicon translator."""
    from .ancient.engine import LADDER_ORDER, translate as ladder
    text = line["input"]
    if language in LADDER_ORDER and language not in {"middle_egyptian", "old_egyptian"}:
        result = ladder(text, language, [target])
        return result["results"].get(target, {}).get("text", "") if result["ok"] else ""
    if language in {"middle_egyptian", "old_egyptian", "late_egyptian", "egyptian"}:
        from .translator import egyptian_to_modern
        formula = egyptian_to_modern(text, target)
        if formula.get("formulae") and len(formula["formulae"]) == 1 and formula["literal_gloss"] == formula["formulae"][0]["translation"]:
            return formula["literal_gloss"]  # a standard formula is translated as a unit
        result = ladder(text, "middle_egyptian", [target])
        if result["ok"] and result["results"].get(target, {}).get("text") and not result["parse"]["unknown_words"]:
            return result["results"][target]["text"]
        from .translator import egyptian_to_modern
        out = egyptian_to_modern(text, target)
        # words the lexicon does not know come back as [word]; they are not a translation
        return re.sub(r"\s+", " ", re.sub(r"\[[^\]]*\]", " ", out.get("literal_gloss") or "")).strip()
    return ""


SYSTEMS: dict[str, Callable[[dict[str, Any], str, str], str]] = {"app": system_app}


def evaluate(system: str | Callable = "app", benchmark: dict[str, Any] | None = None) -> dict[str, Any]:
    bench = benchmark or load_benchmark()
    fn = SYSTEMS[system] if isinstance(system, str) else system
    artifacts = []
    for artifact in bench["artifacts"]:
        per_lang: dict[str, Any] = {}
        for lang in LANGS:
            lines = []
            for line in artifact["lines"]:
                reference = line.get(f"reference_{lang}")
                if not reference:
                    continue
                hypothesis = fn(line, artifact["language"], lang) or ""
                lines.append({"line": line.get("line"), "input": line["input"], "hypothesis": hypothesis, "reference": reference,
                              "reference_status": line.get("reference_status", "draft"), "chrf": chrf(hypothesis, reference),
                              "chrf_pp": chrf(hypothesis, reference, word_order=2),
                              "exact": _clean(hypothesis) == _clean(reference)})
            if lines:
                hyp = " ".join(l["hypothesis"] for l in lines)
                ref = " ".join(l["reference"] for l in lines)
                per_lang[lang] = {"lines": lines, "chrf": chrf(hyp, ref), "chrf_pp": chrf(hyp, ref, word_order=2),
                                  "coverage": round(sum(1 for l in lines if l["hypothesis"]) / len(lines), 3),
                                  "exact": round(sum(l["exact"] for l in lines) / len(lines), 3)}
        artifacts.append({"id": artifact["id"], "title": artifact.get("title"), "provenance": artifact["provenance"],
                          "language": artifact["language"], "results": per_lang})
    summary = {}
    for lang in LANGS:
        scored = [a["results"][lang] for a in artifacts if lang in a["results"]]
        expert = [a["results"][lang] for a in artifacts if lang in a["results"]
                  and all(l["reference_status"] == "expert" for l in a["results"][lang]["lines"])]
        if scored:
            summary[lang] = {"artifacts": len(scored),
                             "chrf_mean_over_artifacts": round(sum(s["chrf"] for s in scored) / len(scored), 2),
                             "chrf_pp_mean_over_artifacts": round(sum(s["chrf_pp"] for s in scored) / len(scored), 2),
                             "coverage": round(sum(s["coverage"] for s in scored) / len(scored), 3),
                             "exact_match": round(sum(s["exact"] for s in scored) / len(scored), 3),
                             "artifacts_with_expert_references": len(expert)}
    return {"benchmark": bench.get("name"), "version": bench.get("version"), "system": system if isinstance(system, str) else "custom",
            "summary": summary, "artifacts": artifacts, "reference_policy": bench.get("reference_policy")}
