from __future__ import annotations

import argparse
import asyncio
import json

from app.ai import ai_status
from app.ancient.engine import LADDER_ORDER, translate as ladder_translate
from app.contextual import contextual_translate
from app.egyptian import hieroglyphize_phrase, search_dictionary
from app.eshb import decode, decode_ipa, encode, encode_ipa
from app.speech import classroom_reading
from app.translator import translate_phrase, translate_word


def _dump(value) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Trans-Late Ancient Relics / ESHB CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    command = sub.add_parser("encode", help="Encode English/Swahili spelling as strict/display ESHB")
    command.add_argument("text")
    command.add_argument("--lang", choices=["auto", "english", "swahili"], default="auto")

    command = sub.add_parser("decode", help="Decode strict reversible ESHB")
    command.add_argument("text")

    command = sub.add_parser("ipa-encode", help="Encode IPA into reversible ESHB")
    command.add_argument("text")

    command = sub.add_parser("ipa-decode", help="Decode strict IPA-ESHB")
    command.add_argument("text")

    command = sub.add_parser("hiero", help="Render Egyptological transliteration as teaching hieroglyphs")
    command.add_argument("text")

    command = sub.add_parser("dict", help="Search the trilingual learner lexicon")
    command.add_argument("query")
    command.add_argument("--lang", choices=["all", "english", "swahili", "egyptian", "transliteration"], default="all")
    command.add_argument("--limit", type=int, default=50)

    command = sub.add_parser("translate", help="Run deterministic historical translation/analysis")
    command.add_argument("text")
    command.add_argument("--source", choices=["english", "swahili", "egyptian"], default="english")
    command.add_argument("--target", choices=["english", "swahili", "egyptian"], default="egyptian")

    command = sub.add_parser("contextual", help="Run ambiguity-aware translation and optional AI review")
    command.add_argument("text")
    command.add_argument("--source", choices=["english", "swahili", "egyptian"], default="english")
    command.add_argument("--target", choices=["english", "swahili", "egyptian"], default="egyptian")
    command.add_argument("--context", default="")
    command.add_argument("--register", choices=["literal", "natural", "scholarly", "learner"], default="natural")
    command.add_argument("--ai", action="store_true", help="Use the configured AI provider to rank nuance/intent")

    command = sub.add_parser("pronounce", help="Return a conventional Egyptological classroom reading")
    command.add_argument("transliteration")

    command = sub.add_parser("ladder", help="Translate between English, Swahili and the oldest stages of Sumerian, Egyptian, Latin, Arabic, Ge'ez, Amharic, Proto-Semitic and Proto-World")
    command.add_argument("text")
    command.add_argument("--source", default="english", help="Source language id or alias (english, sw, old_latin, geez, ...)")
    command.add_argument("--target", action="append", help=f"Target language (repeatable); default is all of: {', '.join(LADDER_ORDER)}")
    command.add_argument("--brief", action="store_true", help="Print only one line per language")

    sub.add_parser("status", help="Show optional AI provider status")

    command = sub.add_parser("corpus", help="Attestation database: import TLA records or the Coptic lexicon, search, stats")
    command.add_argument("action", choices=["import-tla", "import-coptic", "stats", "search", "lemma"])
    command.add_argument("value", nargs="?", help="path (imports), query (search) or lemma id (lemma)")
    command.add_argument("--source-id", default="tla", help="source id for a TLA import (re-importing replaces it)")

    command = sub.add_parser("restore", help="Restore lacunae ([...]) with probability distributions")
    command.add_argument("text")

    command = sub.add_parser("evaluate", help="Artifact-level evaluation: translation (EN/SW) or a vision model")
    command.add_argument("kind", choices=["translation", "restoration", "vision"])
    command.add_argument("--model", help="ONNX model (vision)")
    command.add_argument("--classes", help="classes.json (vision)")
    command.add_argument("--manifest", help="dataset manifest JSON/JSONL (vision)")
    command.add_argument("--split", default="test", choices=["train", "val", "test", "all"])

    command = sub.add_parser("models", help="Model registry: list, register, approve, deploy, retire")
    command.add_argument("action", choices=["list", "register", "approve", "deploy", "retire"])
    command.add_argument("value", nargs="?", help="model id, or file path for register")
    command.add_argument("--name")
    command.add_argument("--dataset")
    command.add_argument("--license")
    command.add_argument("--metrics", help="metrics JSON file (e.g. from evaluate vision)")
    command.add_argument("--actor", default="cli")

    command = sub.add_parser("audit", help="Show or verify the tamper-evident audit log")
    command.add_argument("action", choices=["show", "verify"])

    sub.add_parser("migrate", help="Apply database migrations (SQLite or PostgreSQL)")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.cmd == "encode":
        output = encode(args.text, args.lang).__dict__
    elif args.cmd == "decode":
        output = {"decoded": decode(args.text)}
    elif args.cmd == "ipa-encode":
        output = encode_ipa(args.text).__dict__
    elif args.cmd == "ipa-decode":
        output = {"ipa": decode_ipa(args.text)}
    elif args.cmd == "hiero":
        output = hieroglyphize_phrase(args.text)
    elif args.cmd == "dict":
        output = search_dictionary(args.query, args.lang, limit=max(1, min(args.limit, 500)))
    elif args.cmd == "pronounce":
        output = classroom_reading(args.transliteration)
    elif args.cmd == "status":
        output = ai_status()
    elif args.cmd == "ladder":
        output = ladder_translate(args.text, args.source, args.target or "all")
        if args.brief:
            if not output["ok"]:
                print(output["message"])
                if output["parse"]["unknown_words"]:
                    print("Not recognized: " + ", ".join(output["parse"]["unknown_words"]))
            for lang, result in output["results"].items():
                scripts = "  ".join(result["scripts"].values())
                print(f"{lang:22} {result['text']}  {scripts}  [{result['status']}, {result['confidence']}]")
            return
    elif args.cmd == "contextual":
        output = asyncio.run(
            contextual_translate(
                args.text,
                args.source,
                args.target,
                context=args.context,
                register=args.register,
                use_ai=args.ai,
            )
        )
    elif args.cmd == "translate":
        if args.source == "egyptian":
            from app.translator import egyptian_to_modern
            output = hieroglyphize_phrase(args.text) if args.target == "egyptian" else egyptian_to_modern(args.text, args.target)
        else:
            output = translate_word(args.text, args.source, args.target)
            if args.target == "egyptian" and not output.get("ok"):
                output = translate_phrase(args.text, args.source)
    elif args.cmd == "corpus":
        from app.corpus import store
        if args.action == "import-tla":
            output = store.import_tla(args.value, args.source_id)
        elif args.action == "import-coptic":
            output = store.import_coptic(args.value)
        elif args.action == "stats":
            output = store.stats()
        elif args.action == "search":
            output = store.search(args.value or "")
        else:
            output = store.lemma(args.value or "")
    elif args.cmd == "restore":
        from app.restoration import restore
        output = restore(args.text)
    elif args.cmd == "evaluate":
        if args.kind == "translation":
            from app.translation_eval import evaluate
            output = evaluate()
        elif args.kind == "restoration":
            from app.restoration import evaluate as restoration_eval
            output = restoration_eval()
        else:
            from app.vision_bench import artifact_split, evaluate_onnx, load_manifest
            items = load_manifest(args.manifest)
            if args.split != "all":
                items = artifact_split(items)["splits"][args.split]
            output = evaluate_onnx(args.model, json.loads(open(args.classes, encoding="utf-8").read()), items)
    elif args.cmd == "models":
        from app.storage import registry
        if args.action == "list":
            output = registry.list_models(args.name)
        elif args.action == "register":
            metrics = json.loads(open(args.metrics, encoding="utf-8").read()) if args.metrics else {}
            output = registry.register(args.name or "model", args.value, metrics, args.dataset, args.license, actor=args.actor)
        else:
            status = {"approve": "approved", "deploy": "deployed", "retire": "retired"}[args.action]
            output = registry.promote(int(args.value), status, args.actor)
    elif args.cmd == "audit":
        from app.storage import audit
        output = audit.entries(50) if args.action == "show" else audit.verify()
    elif args.cmd == "migrate":
        from app.storage.migrations import migrate, status
        output = {"applied": migrate(), "migrations": status()}
    else:  # pragma: no cover
        raise RuntimeError("Unknown command")
    _dump(output)


if __name__ == "__main__":
    main()
