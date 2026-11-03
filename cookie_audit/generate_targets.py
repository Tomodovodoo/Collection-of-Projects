#!/usr/bin/env python3
"""Build a ranked audit list from a country-specific CSV or Tranco .nl candidates.

A list filtered to .nl is NOT the same as 'most visited in the Netherlands'.
For defensible top 1,000 NL-visitor sites, obtain a country-ranked, web-only dataset
and provide it through --ranking-csv. The --tranco-nl mode is an explicit proxy.
"""
import argparse, csv, io, re, zipfile
from pathlib import Path
from urllib.parse import urlsplit
import requests

BANNED_TERMS=re.compile(r"(?:^|[.-])(porn|xxx|sexcam|adult|hentai|escort|onlyfans|redtube|xvideos|xhamster|youporn)(?:[.-]|$)",re.I)


def normalize(domain):
    s=(domain or "").strip().lower()
    if not s:return ""
    if s.startswith(("https://","http://")):
        s=urlsplit(s).hostname or ""
    s=s.removeprefix("www.").strip(".")
    return s if re.fullmatch(r"[a-z0-9.-]+",s) and "." in s else ""


def read_rank(path,domain_col="domain",rank_col="rank"):
    with open(path,newline="",encoding="utf-8-sig") as f:
        rows=csv.DictReader(f)
        if not rows.fieldnames or domain_col not in rows.fieldnames:
            raise SystemExit(f"Input CSV must contain {domain_col!r} column")
        for i,row in enumerate(rows,1):
            yield row.get(rank_col) or str(i),row.get(domain_col) or "",row


def tranco():
    url="https://tranco-list.eu/top-1m.csv.zip"
    r=requests.get(url,timeout=65);r.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        name=next(x for x in z.namelist() if x.endswith(".csv"))
        for line in io.TextIOWrapper(z.open(name),encoding="utf8"):
            parts=line.rstrip().split(",",1)
            if len(parts)==2:yield parts[0],parts[1],{}


def main(args):
    if not args.tranco_nl and not args.ranking_csv:
        raise SystemExit("Pass --ranking-csv (recommended) or --tranco-nl (documented proxy)")
    # Filter explicit adult category if present, plus clear adult hostnames; this is NOT perfect NSFW screening.
    seen=set();out=[]
    for rank,raw,row in tranco() if args.tranco_nl else read_rank(args.ranking_csv,args.domain_col,args.rank_col):
        domain=normalize(raw)
        if args.tranco_nl and not (domain.endswith(".nl") or domain.endswith(".amsterdam")):continue
        if not domain or domain in seen or BANNED_TERMS.search(domain):continue
        cat=(row.get("category") or row.get("categories") or "").lower()
        if any(x in cat for x in ("adult","pornography","sexually explicit","gambling")):continue
        seen.add(domain)
        out.append({"rank":str(rank) if str(rank).isdigit() else "", "name":domain,"domain":domain,"url":"https://"+domain,"consortium":"Unknown"})
        if len(out)>=args.limit:break
    Path(args.out).parent.mkdir(parents=True,exist_ok=True)
    with open(args.out,"w",newline="",encoding="utf8") as f:
        writer=csv.DictWriter(f,fieldnames=["rank","name","domain","url","consortium"])
        writer.writeheader();writer.writerows(out)
    print(f"Generated {len(out)} candidates in {args.out}")
    if args.tranco_nl: print("WARNING: Tranco .nl ranking is not a ranking of sites visited by Dutch users.")
    print("WARNING: Adult filtering is heuristic; review domains manually before publishing rankings.")

if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--ranking-csv",help="CSV of top domains by visitors from the Netherlands")
    p.add_argument("--tranco-nl",action="store_true",help="Use Tranco .nl domains as an imperfect proxy")
    p.add_argument("--domain-col",default="domain")
    p.add_argument("--rank-col",default="rank")
    p.add_argument("--limit",type=int,default=1000)
    p.add_argument("--out",default="config/top1000.csv")
    main(p.parse_args())