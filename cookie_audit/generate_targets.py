#!/usr/bin/env python3
"""Generate a Dutch-visitor website target list from a country ranking.

Preferred: --netapi-nl, which downloads NetAPI's country-specific ranked sites.
Alternatively: --ranking-csv INPUT.csv, including NetAPI's downloaded CSV.
Fallback: --tranco-nl (only .nl/.amsterdam domains, NOT country visitors).
All lists need manual NSFW and ownership review before publishing.
"""
from __future__ import annotations

import argparse
import csv
import io
import re
import zipfile
from pathlib import Path
from urllib.parse import urlsplit

import requests

# Screening heuristic, not a reliable content classification system.
BANNED_TERMS = re.compile(
    r"(?:^|[.-])(?:porn(?:hub|ography)?|xxx|xnxx|xvideos|xhamster|xhamster2|youporn|redtube|"
    r"sexcam|adult|hentai|escort|onlyfans|chaturbate|stripchat|cam4|brazzers|fapello|"
    r"eporner|erome|spankbang|xvideo|xfreehd|fetlife|flirt4free|youjizz|hclips|"
    r"livejasmin|bongacams|myfreecams|camsoda|xhamsterlive|faphouse)(?:[.-]|$)", re.I
)


def normalize(domain: str) -> str:
    s = (domain or "").strip().lower()
    if not s:
        return ""
    if s.startswith(("https://", "http://")):
        s = urlsplit(s).hostname or ""
    s = s.removeprefix("www.").strip(".")
    if not re.fullmatch(r"[a-z0-9-]+(?:\.[a-z0-9-]+)+", s):
        return ""
    if any(part.startswith("-") or part.endswith("-") for part in s.split(".")):
        return ""
    return s


def read_rank(path: str, domain_col: str = "domain", rank_col: str = "rank"):
    """Accept lower/upper-case CSV headers and NetAPI_Rank_NL without manual renaming."""
    with open(path, newline="", encoding="utf-8-sig") as f:
        rows = csv.DictReader(f)
        headers = {name.lower().strip(): name for name in (rows.fieldnames or [])}
        domain_key = headers.get(domain_col.lower())
        rank_key = headers.get(rank_col.lower()) or headers.get("netapi_rank_nl")
        if not domain_key:
            raise SystemExit(f"Input CSV must contain a {domain_col!r} column")
        for i, row in enumerate(rows, 1):
            yield row.get(rank_key) or str(i), row.get(domain_key) or "", row


def netapi_nl():
    """Use documented no-token JSON endpoint; fail explicitly on schema changes."""
    r = requests.get(
        "https://netapi.com/api-json/",
        params={"method": "top-websites", "country": "NL", "limit": 1000, "offset": 0},
        timeout=65,
        headers={"User-Agent": "CookieAuditNL/1.0 (public research, target-list download)"},
    )
    r.raise_for_status()
    obj = r.json()
    if isinstance(obj, dict) and obj.get("error"):
        raise RuntimeError(f"NetAPI API error: {obj['error']}")
    candidates = obj if isinstance(obj, list) else None
    if isinstance(obj, dict):
        for key in ("websites", "sites", "domains", "results", "data", "items"):
            candidate = obj.get(key)
            if isinstance(candidate, list):
                candidates = candidate
                break
            if isinstance(candidate, dict):
                for nested in ("websites", "sites", "domains", "results", "items"):
                    if isinstance(candidate.get(nested), list):
                        candidates = candidate[nested]
                        break
            if candidates is not None:
                break
    if not isinstance(candidates, list) or not candidates:
        raise RuntimeError("Unexpected NetAPI response format; download their NL CSV and use --ranking-csv instead")
    for i, item in enumerate(candidates, 1):
        if isinstance(item, str):
            yield i, item, {}
        elif isinstance(item, dict):
            yield item.get("rank") or item.get("country_rank") or i, item.get("domain") or item.get("name") or "", item


def tranco():
    r = requests.get("https://tranco-list.eu/top-1m.csv.zip", timeout=65)
    r.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        name = next(x for x in z.namelist() if x.endswith(".csv"))
        for line in io.TextIOWrapper(z.open(name), encoding="utf8"):
            parts = line.rstrip().split(",", 1)
            if len(parts) == 2:
                yield parts[0], parts[1], {}


def generate(source, *, limit=1000, tranco_only=False):
    seen, out = set(), []
    for rank, raw, row in source:
        domain = normalize(raw)
        if tranco_only and not domain.endswith((".nl", ".amsterdam")):
            continue
        if not domain or domain in seen or BANNED_TERMS.search(domain):
            continue
        category = (row.get("category") or row.get("categories") or "").lower()
        if any(term in category for term in ("adult", "pornography", "sexually explicit", "gambling")):
            continue
        seen.add(domain)
        rank_str = str(rank).strip()
        out.append({"rank": rank_str if rank_str.isdigit() else "", "name": domain, "domain": domain,
                    "url": "https://" + domain, "consortium": "Unknown"})
        if len(out) >= limit:
            break
    return out


def main(args):
    sources = [bool(args.ranking_csv), bool(args.tranco_nl), bool(args.netapi_nl)]
    if sum(sources) != 1:
        raise SystemExit("Select exactly one: --netapi-nl, --ranking-csv FILE, or --tranco-nl")
    source = (netapi_nl() if args.netapi_nl else tranco() if args.tranco_nl
              else read_rank(args.ranking_csv, args.domain_col, args.rank_col))
    out = generate(source, limit=args.limit, tranco_only=args.tranco_nl)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", newline="", encoding="utf8") as f:
        writer = csv.DictWriter(f, fieldnames=["rank", "name", "domain", "url", "consortium"])
        writer.writeheader()
        writer.writerows(out)
    print(f"Generated {len(out)} candidates in {args.out}")
    if args.tranco_nl:
        print("WARNING: Tranco .nl domains are NOT a ranking of sites visited by Dutch users.")
    if len(out) < args.limit:
        print(f"WARNING: fewer than {args.limit} candidates remain after filtering. Do not backfill by guessing ranks.")
    print("WARNING: Adult filtering and ownership classification require manual validation.")
    if args.netapi_nl:
        print("Data source: NetAPI, https://netapi.com/top-websites/nl/ (CC BY 4.0).")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--ranking-csv", help="Country-ranked CSV (e.g. NetAPI's NL list)")
    p.add_argument("--netapi-nl", action="store_true", help="Fetch NL-visitor ranking from NetAPI's free JSON API")
    p.add_argument("--tranco-nl", action="store_true", help="Use Tranco .nl domains as an imperfect proxy")
    p.add_argument("--domain-col", default="domain")
    p.add_argument("--rank-col", default="rank")
    p.add_argument("--limit", type=int, default=1000)
    p.add_argument("--out", default="config/top1000.csv")
    main(p.parse_args())