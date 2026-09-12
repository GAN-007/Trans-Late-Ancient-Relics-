from __future__ import annotations

import argparse
import json

from app.eshb import encode, decode, encode_ipa, decode_ipa
from app.egyptian import search_dictionary, hieroglyphize_phrase
from app.translator import contextual_translate
from app.linguistics import classroom_pronunciation, analyze_morphology


def main():
    parser = argparse.ArgumentParser(description="Trans-Late Ancient Relics CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("encode"); p.add_argument("text"); p.add_argument("--lang", default="auto", choices=["auto","english","swahili"])
    p = sub.add_parser("decode"); p.add_argument("text")
    p = sub.add_parser("ipa-encode"); p.add_argument("text")
    p = sub.add_parser("ipa-decode"); p.add_argument("text")
    p = sub.add_parser("hiero"); p.add_argument("text")
    p = sub.add_parser("dict"); p.add_argument("query"); p.add_argument("--lang", default="all")
    p = sub.add_parser("translate"); p.add_argument("text"); p.add_argument("--source", choices=["english","swahili","egyptian"], default="english"); p.add_argument("--target", choices=["english","swahili","egyptian"], default="egyptian"); p.add_argument("--context", default=""); p.add_argument("--intent", default=""); p.add_argument("--mode", choices=["careful","literal","natural"], default="careful")
    p = sub.add_parser("pronounce"); p.add_argument("text")
    p = sub.add_parser("morphology"); p.add_argument("text")

    args = parser.parse_args()
    if args.cmd == "encode": out = encode(args.text, args.lang).__dict__
    elif args.cmd == "decode": out = {"decoded": decode(args.text)}
    elif args.cmd == "ipa-encode": out = encode_ipa(args.text).__dict__
    elif args.cmd == "ipa-decode": out = {"ipa": decode_ipa(args.text)}
    elif args.cmd == "hiero": out = hieroglyphize_phrase(args.text)
    elif args.cmd == "dict": out = search_dictionary(args.query, args.lang)
    elif args.cmd == "translate": out = contextual_translate(args.text, args.source, args.target, args.context, args.intent, args.mode)
    elif args.cmd == "pronounce": out = classroom_pronunciation(args.text)
    elif args.cmd == "morphology": out = analyze_morphology(args.text)
    else: raise SystemExit(2)
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
