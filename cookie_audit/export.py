#!/usr/bin/env python3
"""Merge raw per-viewport results into the public, privacy-sanitized dashboard dataset."""
import argparse,datetime as dt,csv,json
from pathlib import Path
from audit import targets_from_csv

KEYS=("rejectAvailable","sameLayer","equalEffort","rejectVisible","noTrackingBefore","noTrackingAfterReject")

def aggregate(targets,files):
    keyed={}
    for file in files:
        try:
            data=json.loads(Path(file).read_text(encoding="utf8"))
            if data.get("domain") and data.get("viewport"):
                keyed[(data["domain"],data["viewport"])]=data
        except (OSError,ValueError):continue
    res=[]
    for target in targets:
        sessions=[v for (domain,_),v in keyed.items() if domain==target["domain"]]
        checks={}
        for key in KEYS:
            vals=[s.get("checks",{}).get(key,{}).get("status","unknown") for s in sessions]
            status="fail" if "fail" in vals else ("pass" if vals and all(v=="pass" for v in vals) else "unknown")
            details=[f"{s['viewport']}: {s.get('checks',{}).get(key,{}).get('reason','')}" for s in sessions]
            checks[key]={"status":status,"reason":"; ".join(details) or "Not scanned"}
        status="fail" if any(c["status"]=="fail" for c in checks.values()) else ("pass" if all(c["status"]=="pass" for c in checks.values()) else "unknown")
        res.append({"domain":target["domain"],"name":target["name"],"url":target["url"],
            "consortium":target["consortium"],"rank":target.get("rank"),"status":status,
            "checks":checks,"viewports":sorted(s["viewport"] for s in sessions),
            "testedAt":max((s.get("testedAt","") for s in sessions),default=None),
            "acceptClicks":max((s.get("acceptClicks") or 0 for s in sessions),default=0) or None,
            "rejectClicks":max((s.get("rejectClicks") or 0 for s in sessions),default=0) or None,
            "trackerEventsBefore":sum(len([e for e in s.get("trackerEvents",[]) if e["phase"]=="before"]) for s in sessions),
            "trackerEventsAfter":sum(len([e for e in s.get("trackerEvents",[]) if e["phase"]=="after-reject"]) for s in sessions),
            "warnings":[f"{s['viewport']}: {w}" for s in sessions for w in s.get("warnings",[])][:12],
            "auditStatus": "not-scanned" if not sessions else ("error" if all(s.get("status")=="error" for s in sessions) else "scanned")})
    return res


def main(args):
    targets=targets_from_csv(args.targets)
    rows=aggregate(targets,Path(args.results).glob("*.json"))
    data={"generatedAt":dt.datetime.now(dt.timezone.utc).isoformat(),
          "method":"Automated heuristic detection of consent UI and selected tracker indicators. Not a legal determination.",
          "source":args.targets,"results":rows}
    path=Path(args.out);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf8")
    fails=sum(r["status"]=="fail" for r in rows)
    passes=sum(r["status"]=="pass" for r in rows)
    print(f"Exported {len(rows)} domains to {path}: {fails} flagged, {passes} no detected issues, {len(rows)-fails-passes} uncertain")

if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--targets",default="config/seed_sites.csv")
    p.add_argument("--results",default="results")
    p.add_argument("--out",default="docs/data/results.json")
    main(p.parse_args())