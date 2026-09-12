from __future__ import annotations

import argparse
import asyncio
import json

from app.ai import ai_status
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

    sub.add_parser("status", help="Show optional AI provider status")
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
    else:  # pragma: no cover
        raise RuntimeError("Unknown command")
    _dump(output)


if __name__ == "__main__":
    main()
