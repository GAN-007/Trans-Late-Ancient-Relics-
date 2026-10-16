#!/usr/bin/env python3
"""Build explicitly approved, legally reviewable Hy-MT2 SFT datasets.

Input CSV fields:
source_text,target_text,source_language,target_language,document_id,
license,evidence_url,approved,approved_by

Excludes ancient/undeciphered languages, unapproved or unattributed data.
Splits by document ID and checks for cross-split duplicate source strings.
Outputs one Hy-MT2-compatible {"messages": [...]} JSONL per split.
No training or model promotion happens in this utility.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

REQUIRED = {
    "source_text", "target_text", "source_language", "target_language",
    "document_id", "license", "evidence_url", "approved", "approved_by",
}
ACCEPTED_APPROVAL = {"yes", "true", "1"}
FORBIDDEN = {"egyptian", "ancient-egyptian", "unknown", "und", "undeciphered"}
MODEL_BASE = "https://github.com/Tencent-Hunyuan/Hy-MT2"
MAX_LENGTH = 8192


def _clean(value: str | None) -> str:
    return (value or "").strip()


def _validate(row: dict[str, str], line: int) -> tuple[dict[str, str] | None, str | None]:
    value = {key: _clean(row.get(key)) for key in REQUIRED}
    if value["approved"].lower() not in ACCEPTED_APPROVAL:
        return None, "not_approved"
    if not all(value[k] for k in REQUIRED - {"approved"}):
        return None, "missing_provenance_or_content"
    if (value["source_language"].lower() in FORBIDDEN
            or value["target_language"].lower() in FORBIDDEN):
        return None, "unverified_ancient_or_unknown_language"
    if len(value["source_text"]) > MAX_LENGTH or len(value["target_text"]) > MAX_LENGTH:
        return None, "text_length_exceeds_limit"
    if value["source_text"].casefold() == value["target_text"].casefold():
        return None, "identical_source_and_target"
    if not re.match(r"^https://[^\s]+$", value["evidence_url"]):
        return None, "missing_https_evidence_url"
    if value["license"].lower() in {
        "unknown", "unlicensed", "all rights reserved", "none", "n/a"
    }:
        return None, "unverified_dataset_license"
    return value, None


def _split(document_id: str, fraction: int) -> str:
    digest = hashlib.sha256(document_id.encode("utf-8")).digest()
    return "validation" if int.from_bytes(digest[:8], "big") % 100 < fraction else "train"


def export_dataset(input_path: Path, out_dir: Path, validation_percent: int = 10) -> dict:
    if not 1 <= validation_percent <= 40:
        raise ValueError("validation_percent must be between 1 and 40.")
    if not input_path.exists() or not input_path.is_file():
        raise ValueError("CSV input file does not exist.")
    out_dir.mkdir(parents=True, exist_ok=True)
    counters: Counter[str] = Counter()
    grouped: dict[str, list[dict[str, str]]] = {}
    with input_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or not REQUIRED.issubset(reader.fieldnames):
            raise ValueError("CSV must contain: " + ", ".join(sorted(REQUIRED)))
        for lineno, row in enumerate(reader, start=2):
            record, rejection = _validate(row, lineno)
            if rejection:
                counters[rejection] += 1
                continue
            assert record is not None
            grouped.setdefault(record["document_id"], []).append(record)
            counters["accepted"] += 1
    if not grouped:
        raise ValueError("No approved, license-attributed translation pairs survived validation.")

    split_pairs: dict[str, list[dict]] = {"train": [], "validation": []}
    seen_pair: set[tuple[str, str, str, str]] = set()
    seen_source: dict[tuple[str, str], str] = {}
    for document_id, records in sorted(grouped.items()):
        split = _split(document_id, validation_percent)
        for record in records:
            key = (
                record["source_language"].lower(),
                record["target_language"].lower(),
                record["source_text"].casefold(),
                record["target_text"].casefold(),
            )
            if key in seen_pair:
                counters["deduplicated"] += 1
                continue
            source_key = (record["source_language"].lower(), record["source_text"].casefold())
            previous = seen_source.get(source_key)
            if previous and previous != split:
                counters["source_leakage_rejected"] += 1
                continue
            seen_pair.add(key)
            seen_source[source_key] = split
            source_name = record["source_language"]
            target_name = record["target_language"]
            instruction = (
                f"Translate the following text from {source_name} to {target_name}. "
                "Note that you should only output the translated result without "
                "any additional explanation:\n" + record["source_text"]
            )
            split_pairs[split].append({
                "messages": [
                    {"role": "user", "content": instruction},
                    {"role": "assistant", "content": record["target_text"]},
                ]
            })
            counters[f"split_{split}"] += 1

    outputs: dict[str, str] = {}
    for split, rows in split_pairs.items():
        target = out_dir / f"{split}.jsonl"
        with target.open("w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        outputs[split] = target.name

    input_sha = hashlib.sha256(input_path.read_bytes()).hexdigest()
    manifest = {
        "schema": "hy-mt2-supervised-translation-v1",
        "input_sha256": input_sha,
        "reference_model_repo": MODEL_BASE,
        "source_license_review_required": True,
        "splitting": "deterministic SHA256(document_id) grouping, duplicate-source leakage protection",
        "validation_percent": validation_percent,
        "stats": dict(counters),
        "outputs": outputs,
        "privacy": "Dataset contains supplied text; review PII and artifact provenance before any model training.",
        "model_promotion": "manual approval required; this program performs no training or deployment",
    }
    with (out_dir / "manifest.json").open("w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_csv", type=Path)
    parser.add_argument("output_directory", type=Path)
    parser.add_argument("--validation-percent", type=int, default=10)
    args = parser.parse_args()
    print(json.dumps(
        export_dataset(args.input_csv, args.output_directory, args.validation_percent),
        indent=2, ensure_ascii=False,
    ))


if __name__ == "__main__":
    main()
