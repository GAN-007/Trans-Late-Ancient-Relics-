"""Research layers: sign catalog, quadrats, attestation corpus, Coptic, periods, restoration,
vision benchmark, translation evaluation and institutional storage."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures"


@pytest.fixture(autouse=True)
def isolated_runtime(tmp_path, monkeypatch):
    monkeypatch.setenv("ESHB_RUNTIME_DIR", str(tmp_path))
    monkeypatch.setenv("ESHB_DB_PATH", str(tmp_path / "research.sqlite3"))
    monkeypatch.setenv("ESHB_AI_PROVIDER", "disabled")
    monkeypatch.setenv("ESHB_OBJECT_DIR", str(tmp_path / "objects"))
    monkeypatch.delenv("ESHB_OBJECT_STORE", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    yield


# ------------------------------------------------------------------ 2. sign catalog
def test_unikemet_catalog_counts_and_lookup():
    from app import signs
    info = signs.catalog_info()
    assert info["count"] > 5000 and info["with_gardiner_code"] > 3500
    a1 = signs.sign("A1")
    assert a1["glyph"] == "𓀀" and signs.sign("𓀀")["gardiner"] == "A1"
    assert a1["unikemet_code"] and a1["orientation"] is not None
    assert any(s["gardiner"] == "F35" for s in signs.by_value("nfr"))
    assert signs.sign("not-a-sign") is None


def test_epigraphy_falls_back_to_full_catalog():
    from app.epigraphy import analyze_hieroglyphic_text
    result = analyze_hieroglyphic_text("𓀀𓅓")
    coverage = result["coverage"]
    assert coverage["known_signs"] == coverage["from_reviewed_core"] + coverage["from_unikemet"]
    assert coverage["unknown_or_unmapped_signs"] == 0


# ------------------------------------------------------------------ 3. quadrats
def test_quadrat_mdc_unicode_round_trip():
    from app.quadrat import parse
    mdc = parse("ra:n-f")
    assert mdc["encoding"] == "mdc" and mdc["sign_count"] == 3
    back = parse(mdc["unicode"])
    assert back["encoding"] == "unicode" and back["unicode"] == mdc["unicode"]
    assert parse(back["mdc"])["unicode"] == mdc["unicode"]


def test_quadrat_cartouche_and_errors():
    from app.quadrat import QuadratError, parse
    cartouche = parse("<ra-mn-xpr>")
    assert cartouche["unicode"].startswith("\U00013379\U0001343c") and cartouche["unicode"].endswith("\U0001343d\U0001337a")
    with pytest.raises(QuadratError):
        parse("A1:")


def test_quadrat_svg_layout_both_directions():
    from app.quadrat import render_svg
    ltr = render_svg("ra:n-f", "ltr")
    rtl = render_svg("ra:n-f", "rtl")
    assert ltr["svg"].startswith("<svg") and rtl["direction"] == "rtl"
    assert ltr["svg"] != rtl["svg"]
    damaged = render_svg("#b ra #e -n")
    assert "pattern" in damaged["svg"]


# ------------------------------------------------------------------ 1. attestation corpus
def test_corpus_bundled_sources_and_provenance():
    from app.corpus import store
    stats = store.stats()
    assert stats["lemmas"] > 11000 and stats["attestations"] >= 10
    hits = store.search("ḥtp")
    assert hits
    attested = [h for h in store.search("") if h.get("attestations")] or hits
    lemma = store.lemma(attested[0]["id"])
    assert lemma and lemma["lemma"]


def test_corpus_attestations_carry_object_line_and_date():
    from app.corpus import store
    store.ensure_bundled()
    from app.runtime import connect
    conn = connect()
    try:
        row = conn.execute("SELECT lemma_id FROM corpus_attestations LIMIT 1").fetchone()
    finally:
        conn.close()
    assert row is not None
    rows = store.attestations(row["lemma_id"])
    first = rows[0]
    assert first.get("object") or first.get("text")
    assert "date_from" in json.dumps(first) or "date" in json.dumps(first)


def test_corpus_import_flat_jsonl_replaces_source(tmp_path):
    from app.corpus import store
    path = tmp_path / "flat.jsonl"
    rows = [{"transcription": "ḥtp dj nswt", "lemmatization": "111230|ḥtp 851424|dj 88040|nswt",
             "glossing": "V N N", "translation": "an offering which the king gives", "dateNotBefore": "-1980",
             "dateNotAfter": "-1760", "UPOS": "VERB NOUN NOUN"}]
    path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8")
    first = store.import_tla(path, "tla-flat-test")
    second = store.import_tla(path, "tla-flat-test")
    assert first == second and first["imported"]["corpus_sentences"] == 1
    from app.storage import audit
    assert any(e["action"] == "corpus.import" and e["target"] == "tla-flat-test" for e in audit.entries(50))


# ------------------------------------------------------------------ 7/8. Coptic and script stages
def test_coptic_pronunciation_and_reading():
    from app import coptic
    assert coptic.is_coptic("ⲣⲱⲙⲉ")
    assert coptic.pronounce("ⲣⲣⲟ")["ipa"] == "/ər.ˈro/"
    word = coptic.read("ⲡⲣⲱⲙⲉ")["words"][0]
    assert word["known"] and word["analysis"]["prefix_gloss"] == "the (masc.)"
    assert "man" in word["gloss"]


def test_egyptian_to_coptic_vocalization_bridge():
    from app import coptic
    found = coptic.vocalization("rmṯ")
    assert found["coptic"]["lemma"] == "ⲣⲱⲙⲉ" and found["coptic"]["pronunciation"]["ipa"]
    status = coptic.bridge_status()
    assert status["pairs"] >= 43 and len(status["unresolved"]) <= 1


def test_script_stages_cover_all_egyptian_scripts():
    from app.script_stages import stages
    names = {s["id"] for s in stages()}
    assert {"hieroglyphic", "hieratic", "demotic", "coptic"} <= names


def test_reading_routes_coptic_text():
    from app.avatar_chat.reading import read_text
    out = read_text("ⲡⲣⲱⲙⲉ")
    assert "coptic" in json.dumps(out, ensure_ascii=False).lower()


# ------------------------------------------------------------------ 4. period grammar
def test_period_detection_flags_anachronism():
    from app.periods import detect, explain_gloss
    late = detect("sḏm.n=f", "late_egyptian")
    assert late["anachronisms"] and "middle_egyptian" in late["consistent_stages"]
    assert not detect("sḏm.n=f", "middle_egyptian")["anachronisms"]
    gloss = explain_gloss("V\\tam.act-ngem:stpr.3sg.m")
    assert gloss["part_of_speech"] == "verb" and "stative / pseudoparticiple" in gloss["features"]


def test_unknown_period_rejected():
    from app.periods import detect
    with pytest.raises(ValueError):
        detect("nfr", "not_a_stage")


# ------------------------------------------------------------------ 6. restoration
def test_restoration_returns_normalised_distribution():
    from app.restoration import restore
    gap = restore("ḥtp dj [...]")["gaps"][0]
    probs = [c["probability"] for c in gap["candidates"]]
    assert gap["candidates"][0]["text"] == "nswt"
    assert probs == sorted(probs, reverse=True)
    assert sum(probs) + gap["other"] == pytest.approx(1.0, abs=0.02)
    assert gap["entropy_bits"] >= 0


def test_restoration_respects_partial_and_length():
    from app.restoration import restore
    gap = restore("ḥtp dj n[...]")["gaps"][0]
    assert all(c["text"].startswith("n") for c in gap["candidates"])


# ------------------------------------------------------------------ 5. vision benchmark
def test_artifact_split_has_no_leakage():
    from app.vision_bench import artifact_split, load_manifest
    items = load_manifest(FIXTURES / "vision" / "manifest.json")
    split = artifact_split(items)
    assert split["leakage"] == []
    seen = {}
    for name, rows in split["splits"].items():
        for row in rows:
            assert seen.setdefault(row["artifact"], name) == name


def test_vision_metrics_calibration_and_open_set():
    from app.vision_bench import evaluate_predictions
    rows = [{"label": "A1", "ranked": [("A1", 0.9), ("G17", 0.1)]},
            {"label": "G17", "ranked": [("A1", 0.6), ("G17", 0.4)]},
            {"label": None, "ranked": [("A1", 0.3)]}]
    report = evaluate_predictions(rows)
    assert report["top1"] == 0.5 and report["top5"] == 1.0
    assert report["unknown_rejection_auroc"] == 1.0
    assert report["most_confused"][0] == {"true": "G17", "predicted": "A1", "count": 1}
    assert 0 <= report["expected_calibration_error"] <= 1


def test_onnx_evaluation_on_fixture_model():
    pytest.importorskip("onnxruntime")
    pytest.importorskip("PIL")
    from app.vision_bench import evaluate_onnx, load_manifest
    folder = FIXTURES / "vision"
    classes = json.loads((folder / "classes.json").read_text())
    report = evaluate_onnx(folder / "tiny_classifier.onnx", classes, load_manifest(folder / "manifest.json"))
    assert report["items"] == 19 and report["model"]["classes"] == len(classes)


def test_franken_dataset_not_benchmark_eligible():
    from app.vision_bench import DATASETS
    assert DATASETS["franken_unas"]["benchmark_eligible"] is False
    assert DATASETS["mmm"]["license"] == "CC BY-SA 4.0"


# ------------------------------------------------------------------ 9. translation evaluation
def test_chrf_properties():
    from app.translation_eval import chrf
    assert chrf("an offering which the king gives", "an offering which the king gives") == 100.0
    assert chrf("", "x") == 0.0
    assert chrf("an offering", "an offering which the king gives") < 100
    assert chrf("a b", "a b", word_order=2) == 100.0


def test_translation_benchmark_meets_baseline():
    from app.translation_eval import evaluate
    baseline = json.loads((ROOT / "app" / "data" / "eval" / "baseline.json").read_text(encoding="utf-8"))["summary"]
    report = evaluate()
    for lang in ("english", "swahili"):
        assert report["summary"][lang]["chrf_mean_over_artifacts"] >= baseline[lang]["chrf_mean_over_artifacts"] - 0.01
        assert report["summary"][lang]["coverage"] >= baseline[lang]["coverage"]
    assert all(a["provenance"] for a in report["artifacts"])


def test_offering_formula_translated_as_unit():
    from app.translator import egyptian_to_modern
    out = egyptian_to_modern("ḥtp dj nswt", "english")
    assert out["formulae"] and "offering" in out["literal_gloss"].lower()


# ------------------------------------------------------------------ 10. storage
def test_postgres_sql_translation():
    from app.storage.pg import translate
    sql, _ = translate("INSERT OR IGNORE INTO t (a) VALUES (?)")
    assert "%s" in sql and "ON CONFLICT DO NOTHING" in sql
    sql, _ = translate("CREATE TABLE x (id INTEGER PRIMARY KEY AUTOINCREMENT, d BLOB)")
    assert "IDENTITY" in sql and "BYTEA" in sql
    assert translate("PRAGMA journal_mode=WAL")[0] is None
    sql, _ = translate("SELECT * FROM t WHERE a LIKE '50%' AND b=?")
    assert "50%%" in sql and sql.endswith("%s")


def test_object_store_is_content_addressed():
    from app.storage import objects
    a = objects.put(b"stela photo", "image/jpeg", purpose="test")
    b = objects.put(b"stela photo", "image/jpeg", purpose="test")
    assert a["key"] == b["key"] and objects.get(a["key"]) == b"stela photo"
    assert objects.exists(a["key"]) and objects.status()["backend"] == "local"


def test_audit_chain_detects_tampering():
    from app.runtime import connect
    from app.storage import audit
    for n in range(3):
        audit.record("tester", "test.event", str(n), {"n": n})
    assert audit.verify()["ok"]
    conn = connect()
    try:
        conn.execute("UPDATE audit_log SET details=? WHERE id=(SELECT MIN(id) FROM audit_log)", (json.dumps({"n": 99}),))
        conn.commit()
    finally:
        conn.close()
    assert audit.verify()["ok"] is False


def test_model_registry_gates(tmp_path):
    from app.storage import registry
    model = tmp_path / "m.onnx"
    model.write_bytes(b"onnx-bytes")
    weak = registry.register("signs", str(model), {"top1": 0.5, "expected_calibration_error": 0.05}, "mmm", "CC BY-SA 4.0")
    with pytest.raises(registry.RegistryError):
        registry.promote(weak["id"], "approved", "admin")
    unlicensed = registry.register("signs", str(model), {"top1": 0.95, "expected_calibration_error": 0.02}, "franken_unas", None)
    with pytest.raises(registry.RegistryError):
        registry.promote(unlicensed["id"], "approved", "admin")
    good = registry.register("signs", str(model), {"top1": 0.93, "expected_calibration_error": 0.04}, "mmm", "CC BY-SA 4.0")
    assert good["version"] == 3
    registry.promote(good["id"], "approved", "admin")
    deployed = registry.promote(good["id"], "deployed", "admin")
    assert deployed["status"] == "deployed"
    with pytest.raises(registry.RegistryError):
        registry.promote(good["id"], "candidate", "admin")


def test_migrations_are_idempotent():
    from app.storage.migrations import migrate, status
    migrate()
    assert migrate() == []
    assert all(m["applied"] for m in status())


# ------------------------------------------------------------------ API
def test_research_api_endpoints():
    from app.main import app
    with TestClient(app) as client:
        assert client.get("/api/signs/catalog").json()["count"] > 5000
        assert client.get("/api/signs/lookup", params={"q": "A1"}).json()["sign"]["glyph"] == "𓀀"
        assert client.get("/api/quadrat", params={"text": "ra:n-f"}).json()["svg"].startswith("<svg")
        assert client.get("/api/quadrat", params={"text": "A1:"}).status_code == 422
        assert client.get("/api/quadrat", params={"text": "ra", "direction": "up"}).status_code == 422
        assert client.get("/api/corpus/stats").json()["lemmas"] > 11000
        assert client.get("/api/corpus/search", params={"q": "nfr"}).json()["results"]
        assert client.get("/api/corpus/lemmas/does-not-exist").status_code == 404
        assert client.get("/api/coptic/read", params={"text": "ⲣⲱⲙⲉ"}).json()["words"]
        assert client.get("/api/coptic/vocalization", params={"egyptian": "rmṯ"}).json()["result"]
        assert client.get("/api/scripts/stages").json()["stages"]
        assert client.get("/api/grammar/periods").json()["inventory"]
        assert client.get("/api/grammar/periods", params={"text": "sḏm.n=f", "period": "late_egyptian"}).json()["anachronisms"]
        assert client.get("/api/grammar/gloss", params={"gloss": "N.m:sg"}).json()["part_of_speech"]
        assert client.get("/api/restoration", params={"text": "ḥtp dj [...]"}).json()["gaps"]
        assert client.get("/api/evaluation/translation").json()["summary"]["english"]
        assert client.get("/api/vision/datasets").json()["datasets"]


def test_admin_storage_endpoints_require_admin():
    from app.auth import create_session, create_user, init_auth_db
    from app.main import app
    with TestClient(app) as client:
        assert client.get("/api/admin/storage").status_code in (401, 403)
        assert client.get("/api/admin/audit").status_code in (401, 403)
        init_auth_db()
        admin = create_user("storageadmin", "Storage-admin-123", role="admin")
        client.cookies.set("eshb_session", create_session(admin["id"]))
        storage = client.get("/api/admin/storage").json()
        assert storage["database"] in ("sqlite", "postgresql") and storage["migrations"]
        audit = client.get("/api/admin/audit").json()
        assert audit["chain"]["ok"]
        assert client.get("/api/admin/models").json()["models"] == []
        assert client.post("/api/admin/models/999/status", json={"status": "approved"}).status_code == 422
