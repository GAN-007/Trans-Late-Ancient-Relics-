from __future__ import annotations

import csv
import json
import pytest
from scripts.build_mt_dataset import export_dataset, REQUIRED

def write_csv(path, rows):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer=csv.DictWriter(handle, fieldnames=sorted(REQUIRED))
        writer.writeheader()
        writer.writerows(rows)

def sample(**changes):
    row={
        "source_text":"Welcome to this museum",
        "target_text":"Bienvenue dans ce musée",
        "source_language":"English",
        "target_language":"French",
        "document_id":"museum-entry-001",
        "license":"CC-BY-4.0",
        "evidence_url":"https://example.org/attestation/one",
        "approved":"yes",
        "approved_by":"human-reviewer-001",
    }
    row.update(changes)
    return row

def test_export_provenance_and_sft_schema(tmp_path):
    input_file=tmp_path/"approved.csv"
    write_csv(input_file, [
        sample(),
        sample(document_id="museum-entry-002",source_text="Please enter",
               target_text="Entrez, s'il vous plaît"),
        sample(document_id="unreviewed",approved="no"),
        sample(document_id="unsafe",source_language="Egyptian"),
        sample(document_id="no-license",license="unknown"),
        sample(document_id="missing-proof",evidence_url="http://example.org"),
    ])
    out=tmp_path/"output"
    manifest=export_dataset(input_file,out,validation_percent=20)
    assert manifest["stats"]["accepted"]==2
    assert manifest["stats"]["not_approved"]==1
    assert manifest["stats"]["unverified_ancient_or_unknown_language"]==1
    assert manifest["stats"]["unverified_dataset_license"]==1
    assert manifest["stats"]["missing_https_evidence_url"]==1
    rows=[]
    for split in ("train","validation"):
        rows.extend(json.loads(line) for line in (out/f"{split}.jsonl").read_text().splitlines())
    assert len(rows)==2
    assert all([m["role"] for m in item["messages"]]==["user","assistant"] for item in rows)
    assert manifest["model_promotion"].startswith("manual")
    assert (out/"manifest.json").exists()

def test_reject_invalid_files_and_approval(tmp_path):
    with pytest.raises(ValueError,match="does not exist"):
        export_dataset(tmp_path/"absent.csv",tmp_path/"out")
    raw=tmp_path/"none.csv"
    write_csv(raw,[sample(approved="false")])
    with pytest.raises(ValueError,match="No approved"):
        export_dataset(raw,tmp_path/"out")
    with pytest.raises(ValueError,match="validation_percent"):
        export_dataset(raw,tmp_path/"out",validation_percent=100)

def test_duplicate_source_does_not_leak_across_train_validation(tmp_path):
    # Split placement depends on document hashes, but a single normalized source
    # cannot enter both splits, even when documents provide different targets.
    src=tmp_path/"source.csv"
    write_csv(src,[
        sample(document_id=f"record-{index:03d}",
               source_text="Hello world",
               target_text=f"Bonjour monde {index}")
        for index in range(30)
    ])
    out=tmp_path/"out"
    manifest=export_dataset(src,out,validation_percent=40)
    train=[json.loads(line) for line in (out/"train.jsonl").read_text().splitlines()]
    validation=[json.loads(line) for line in (out/"validation.jsonl").read_text().splitlines()]
    assert len(train)+len(validation)>=1
    assert not (train and validation)
    assert manifest["stats"]["source_leakage_rejected"]>=1
