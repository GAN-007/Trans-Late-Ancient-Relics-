import argparse, json
from app.eshb import encode, decode, encode_ipa, decode_ipa
from app.egyptian import search_dictionary, hieroglyphize_phrase
from app.translator import translate_phrase, translate_word

def main():
    p=argparse.ArgumentParser(description="ESHB / Middle Egyptian tutor CLI")
    sub=p.add_subparsers(dest="cmd",required=True)
    a=sub.add_parser("encode"); a.add_argument("text"); a.add_argument("--lang",default="auto")
    a=sub.add_parser("decode"); a.add_argument("text")
    a=sub.add_parser("ipa-encode"); a.add_argument("text")
    a=sub.add_parser("ipa-decode"); a.add_argument("text")
    a=sub.add_parser("hiero"); a.add_argument("text")
    a=sub.add_parser("dict"); a.add_argument("query"); a.add_argument("--lang",default="all")
    a=sub.add_parser("translate"); a.add_argument("text"); a.add_argument("--source",choices=["english","swahili"],default="english")
    args=p.parse_args()
    if args.cmd=="encode": out=encode(args.text,args.lang).__dict__
    elif args.cmd=="decode": out={"decoded":decode(args.text)}
    elif args.cmd=="ipa-encode": out=encode_ipa(args.text).__dict__
    elif args.cmd=="ipa-decode": out={"ipa":decode_ipa(args.text)}
    elif args.cmd=="hiero": out=hieroglyphize_phrase(args.text)
    elif args.cmd=="dict": out=search_dictionary(args.query,args.lang)
    elif args.cmd=="translate":
        out=translate_word(args.text,args.source,"egyptian")
        if not out.get("ok"): out=translate_phrase(args.text,args.source)
    print(json.dumps(out,ensure_ascii=False,indent=2))

if __name__=="__main__": main()
