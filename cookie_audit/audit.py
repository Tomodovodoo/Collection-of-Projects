#!/usr/bin/env python3
"""Dutch Cookie Audit: evidence-first browser measurements, not legal judgments.

Requires: pip install -r requirements.txt && python -m playwright install chromium
Run: python audit.py --targets config/seed_sites.csv --viewports mobile,desktop
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import datetime as dt
import json
import os
import re
import shutil
from pathlib import Path
from urllib.parse import urlsplit

from playwright.async_api import async_playwright, TimeoutError as PWTimeout

try:
    import tldextract
    _extract = tldextract.TLDExtract(suffix_list_urls=())
except ImportError:
    _extract = None

ROOT = Path(__file__).resolve().parent
CONSENT_TERMS = re.compile(r"cookie|toestemming|privacy|consent|gegevens.*(partner|advertent)|your data|personal data|tracking|advertentiepartner", re.I)
REJECT = re.compile(r"^(?:(?:alle[s]?|alle\s+cookies)\s+)?(?:weiger(?:en)?|afwijz(?:en|ing)?|reject(?:\s+all)?|decline(?:\s+all)?|refuse(?:\s+all)?|niet\s+akkoord|niet\s+accepteren|geen\s+toestemming|alleen\s+(?:noodzakelijke|functionele)\s+cookies|only\s+necessary|only\s+essential|continue\s+without\s+(?:accept|consent)|doorgaan\s+zonder\s+(?:akkoord|accepteren|toestemming)|verder\s+zonder\s+(?:cookies|toestemming|accepteren)|nee(?:,?\s+bedankt)?|disagree|deny(?:\s+all)?)\b", re.I)
ACCEPT = re.compile(r"^(?:alles?\s+|alle\s+cookies\s+)?(?:accepteer|accepteren|accept(?:\s+all)?|akkoord|agree(?:\s+to\s+all)?|allow\s+all|toestaan|ik\s+ga\s+akkoord|yes(?:,?\s+i\s+agree)?)\b", re.I)
SETTINGS = re.compile(r"\b(instellingen|voorkeuren|aanpassen|beheren|wijzigen|preferences|settings|manage|configure|options|meer\s+informatie|more\s+choices|customi[sz]e)\b", re.I)
BOT_BLOCK = re.compile(r"captcha|verify you are human|verifieer dat je een mens bent|access denied|too many requests|unusual traffic", re.I)
TRACK_COOKIE = re.compile(r"^(?:_ga(?:_.+)?|_fbp|_fbc|_gcl_au|_ttp|_pin_unauth|__gads|__gpi|_uetvid|_uetsid)$", re.I)

# These patterns are intentionally narrow: a third-party script or CDN alone is NOT proof of tracking.
EVENT_ENDPOINTS = [
    (re.compile(r"(^|\.)google-analytics\.com$", re.I), re.compile(r"/(?:g/)?collect(?:$|/)", re.I), "Google Analytics collection"),
    (re.compile(r"(^|\.)facebook\.com$", re.I), re.compile(r"^/tr/?$", re.I), "Meta Pixel event"),
    (re.compile(r"(^|\.)doubleclick\.net$", re.I), re.compile(r"/(?:pagead|activity|ddm)/", re.I), "Google advertising event"),
    (re.compile(r"(^|\.)googleadservices\.com$", re.I), re.compile(r"/(?:pagead/conversion|pagead/1p-conversion)", re.I), "Google Ads conversion"),
    (re.compile(r"(^|\.)bat\.bing\.com$", re.I), re.compile(r"^/action", re.I), "Microsoft Ads UET event"),
    (re.compile(r"(^|\.)tiktok\.com$", re.I), re.compile(r"/pixel/|/api/v2/pixel", re.I), "TikTok Pixel event"),
    (re.compile(r"(^|\.)clarity\.ms$", re.I), re.compile(r"^/(?:collect|e)\b", re.I), "Microsoft Clarity collection"),
    (re.compile(r"(^|\.)hotjar\.com$", re.I), re.compile(r"/(?:api/|track|collect)", re.I), "Hotjar collection"),
    (re.compile(r"(^|\.)px\.ads\.linkedin\.com$", re.I), re.compile(r"/collect", re.I), "LinkedIn Insight event"),
    (re.compile(r"(^|\.)ct\.pinterest\.com$", re.I), re.compile(r"/v3/", re.I), "Pinterest Tag event"),
]

DOM_SCAN = r'''(stamp) => {
 const consent = /cookie|toestemming|privacy|consent|advertentiepartner|personal data|your data|legitimate interest|gebruiken.*gegevens|tracking/i;
 const rootSelectors = '#onetrust-banner-sdk,#onetrust-consent-sdk,#CybotCookiebotDialog,#didomi-host,.qc-cmp2-container,[id*="cookie-banner" i],[class*="cookie-banner" i],[id*="consent-banner" i],[class*="consent-banner" i],[role="dialog"],dialog,[aria-modal="true"]';
 const clickable = 'button,[role="button"],a,input[type="button"],input[type="submit"]';
 const seen = new Set(); const roots=[]; const controls=[];
 function walk(root) {
   if (!root || seen.has(root)) return; seen.add(root);
   try {
     roots.push(...root.querySelectorAll(rootSelectors));
     controls.push(...root.querySelectorAll(clickable));
     for (const n of root.querySelectorAll('*')) if (n.shadowRoot) walk(n.shadowRoot);
   } catch(e) {}
 }
 walk(document);
 function visible(e) {
   const r=e.getBoundingClientRect(),s=getComputedStyle(e);
   return r.width>=4 && r.height>=4 && s.display!=='none' && s.visibility!=='hidden' && Number(s.opacity)>0.06;
 }
 function ancestorContext(e) {
   let p=e; let depth=0; let best='';
   while (p && depth++<9) {
     const t=(p.innerText||p.textContent||'').slice(0,5500);
     if (t.length>=15 && t.length<=5500 && consent.test(t)) best=t.slice(0,400);
     p=p.parentElement || (p.getRootNode && p.getRootNode().host);
   }
   return best;
 }
 const visibleRoots=roots.filter(e=>visible(e) && consent.test((e.innerText||e.textContent||'').slice(0,5000)));
 const isInRoot=(e)=>visibleRoots.some(r=>r===e || r.contains(e) || (e.getRootNode && e.getRootNode().host && r.contains(e.getRootNode().host)));
 const out=[];
 for(const [i,e] of controls.entries()) {
   if(!visible(e) || i>1500) continue;
   let t=(e.getAttribute('aria-label')||e.innerText||e.textContent||e.value||e.getAttribute('title')||'').trim().replace(/\s+/g,' ').slice(0,140);
   if(!t) continue;
   const context=ancestorContext(e);
   const inside=isInRoot(e) || Boolean(context);
   if(!inside) continue;
   const r=e.getBoundingClientRect(),s=getComputedStyle(e);
   const id='ca-'+stamp+'-'+i;
   try { e.setAttribute('data-cookie-audit',id); } catch(e) {}
   out.push({id,text:t,tag:e.tagName.toLowerCase(),role:e.getAttribute('role')||'',
     rect:{x:Math.round(r.x),y:Math.round(r.y),w:Math.round(r.width),h:Math.round(r.height)},
     inViewport:r.bottom>0 && r.right>0 && r.top<innerHeight && r.left<innerWidth,
     fg:s.color,bg:s.backgroundColor,fontSize:parseFloat(s.fontSize)||0,fontWeight:s.fontWeight,
     opacity:parseFloat(s.opacity)||1,display:s.display,context:context.slice(0,240),inRoot:isInRoot(e)});
 }
 return {banner:visibleRoots.length>0 || out.some(x=>/cookie|consent|toestemming|privacy/i.test(x.context) && /accepteer|accepteren|accept|akkoord|agree|allow all/i.test(x.text)),
   roots:visibleRoots.length,controls:out.slice(0,120),title:document.title,body:(document.body?.innerText||'').slice(0,700)};
}'''


def registrar(host: str) -> str:
    """Registrable-domain approximation when tldextract is unavailable."""
    host = (host or "").lower().split(":")[0].strip(".")
    if not host or host == "localhost":
        return host
    if _extract:
        part = _extract(host)
        return ".".join(x for x in (part.domain, part.suffix) if x)
    parts = host.split(".")
    if len(parts) < 3:
        return host
    suffix2 = ".".join(parts[-2:])
    if suffix2 in {"co.uk", "org.uk", "gov.uk", "com.au", "co.nz", "co.jp", "com.br"}:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def detect_event(url: str):
    try:
        parsed=urlsplit(url); host=(parsed.hostname or "").lower(); path=parsed.path
        for domain, endpoint, name in EVENT_ENDPOINTS:
            if domain.search(host) and endpoint.search(path):
                return name
    except ValueError:
        pass
    return None


def safe_url(url: str) -> str:
    try:
        u=urlsplit(url)
        return f"{u.scheme}://{u.netloc}{u.path[:220]}"  # deliberately drop query, fragments, tokens
    except ValueError:
        return "[invalid URL]"


def choice_kind(s: str) -> str:
    s=" ".join((s or "").lower().split()).strip(" .!?\n\t")
    if REJECT.search(s): return "reject"
    if ACCEPT.search(s): return "accept"
    if SETTINGS.search(s): return "settings"
    return "other"


def color_rgb(css: str):
    m=re.match(r"rgba?\(\s*(\d+)[, ]+\s*(\d+)[, ]+\s*(\d+)",css or "")
    return tuple(int(x) for x in m.groups()) if m else None


def color_luminance(rgb):
    if not rgb: return None
    def x(c):
        c=c/255
        return c/12.92 if c<=.04045 else ((c+.055)/1.055)**2.4
    return sum(a*b for a,b in zip((.2126,.7152,.0722),map(x,rgb)))


def contrast(a: str,b: str):
    x=color_luminance(color_rgb(a));y=color_luminance(color_rgb(b))
    if x is None or y is None: return None
    return (max(x,y)+.05)/(min(x,y)+.05)


def button_visibility(reject: dict, accept: dict):
    """Flag conspicuous text links, substantial size disparity, and provably low text contrast."""
    if not reject.get("inViewport"):
        return "fail", "Reject option is outside the initial viewport"
    a=accept.get("rect",{});r=reject.get("rect",{})
    ar=max(1, a.get("w",1)*a.get("h",1));rr=max(1,r.get("w",1)*r.get("h",1))
    if reject.get("tag")=="a" and accept.get("tag")=="button" and (reject.get("bg") in ("rgba(0, 0, 0, 0)","transparent","")):
        return "fail", "Reject is an unfilled text link beside an accept button"
    if ar/max(rr,1)>2.6 and r.get("w",0)<a.get("w",0)*.72:
        return "fail", "Reject control is substantially smaller than accept"
    if reject.get("fontSize",16)<accept.get("fontSize",16)*.78:
        return "fail", "Reject label is substantially smaller"
    c=contrast(reject.get("fg"),reject.get("bg"))
    if c is not None and c<2.8 and not (reject.get("bg","").startswith("rgba") and reject.get("bg","").endswith(", 0)")):
        return "fail", f"Reject text has low measured contrast ({c:.1f}:1; transparency can affect this estimate)"
    return "pass", "Reject appears visible and comparably prominent (heuristic)"


def mark(status: str, reason: str):
    return {"status":status,"reason":reason}


def tracker_cookie_names(cookies):
    return sorted({c.get("name","") for c in cookies if TRACK_COOKIE.match(c.get("name",""))})


async def inspect(page):
    results=[]; has_banner=False; roots=0
    for i,frame in enumerate(page.frames):
        try:
            data=await asyncio.wait_for(frame.evaluate(DOM_SCAN, f"{i}-{int(dt.datetime.now().timestamp()*1000)}"), timeout=4)
            roots+=data.get("roots",0)
            has_banner |= data.get("banner",False)
            for c in data.get("controls",[]):
                c["kind"]=choice_kind(c["text"])
                c["frameIndex"]=i
                c["frameUrl"]=safe_url(frame.url)
                c["_frame"]=frame  # remove before serialization
                results.append(c)
        except Exception:
            continue
    # Prefer matching consent modal root, not site's navigation.
    actions=[c for c in results if c["kind"]!="other"]
    if any(c["kind"]=="accept" and c.get("context") for c in actions):
        has_banner=True
    return {"banner":has_banner,"roots":roots,"controls":actions}


def find_choice(state, kind):
    arr=[c for c in state["controls"] if c["kind"]==kind and c.get("inViewport")]
    return sorted(arr,key=lambda x:(not x.get("inRoot"), -x["rect"]["w"]*x["rect"]["h"]))[0] if arr else None


async def click_choice(c):
    if c is None: return False
    try:
        await c["_frame"].locator(f'[data-cookie-audit="{c["id"]}"]').click(timeout=3500)
        return True
    except Exception:
        return False


def public_controls(state):
    return [{k:v for k,v in c.items() if k not in ("_frame","context") } for c in state.get("controls",[])[:60]]


async def capture(page,path):
    path.parent.mkdir(parents=True,exist_ok=True)
    try:
        await page.screenshot(path=str(path),type="jpeg",quality=60,full_page=False,timeout=6000,animations="disabled")
        return str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path)
    except Exception:
        return None


async def run_one(browser, target, view, args):
    domain=target["domain"]
    viewport={"width":390,"height":844} if view=="mobile" else {"width":1365,"height":900}
    context=await browser.new_context(locale="nl-NL",timezone_id="Europe/Amsterdam",viewport=viewport,
       is_mobile=(view=="mobile"),has_touch=(view=="mobile"),device_scale_factor=2 if view=="mobile" else 1,
       service_workers="allow",ignore_https_errors=False)
    page=await context.new_page()
    events=[];counts={"requests":0}
    main_host=(urlsplit(target["url"]).hostname or domain)
    def on_req(req):
        counts["requests"]+=1
        typ=detect_event(req.url)
        if typ and len(events)<100:
            u=urlsplit(req.url)
            events.append({"type":typ,"url":safe_url(req.url),"method":req.method,
                "thirdParty":registrar(u.hostname or "")!=registrar(main_host),"phase":phase[0]})
    phase=["before"]
    page.on("request",on_req)
    result={"domain":domain,"url":target["url"],"name":target.get("name") or domain,
            "consortium":target.get("consortium") or "Unknown", "rank":target.get("rank"),"viewport":view,
            "testedAt":dt.datetime.now(dt.timezone.utc).isoformat(),"checks":{},"overall":"unknown",
            "acceptClicks":None,"rejectClicks":None,"bannerDetected":False,"status":"unknown",
            "trackerEvents":[],"trackingCookiesBefore":[],"trackingCookiesAfterReject":[],
            "evidence":{},"warnings":[],"requestCount":0}
    ev_dir=ROOT/"evidence"/re.sub(r"[^a-z0-9.-]","_",domain)/view
    try:
        response=await page.goto(target["url"],wait_until="domcontentloaded",timeout=args.timeout_ms)
        await page.wait_for_timeout(args.wait_ms)
        result["httpStatus"]=response.status if response else None
        result["finalUrl"]=safe_url(page.url)
        if response and response.status in (401,403,429,503):
            result["warnings"].append(f"HTTP {response.status}; may be bot protection or an error page")
        body=await page.locator("body").inner_text(timeout=4000)
        if BOT_BLOCK.search(body[:2200]):
            raise RuntimeError("Bot protection, CAPTCHA, or access-denied page detected")
        initial=await inspect(page)
        result["bannerDetected"]=initial["banner"]
        result["controls"]=public_controls(initial)
        result["evidence"]["initialScreenshot"]=await capture(page,ev_dir/"before.jpg")
        cookies_before=await context.cookies()
        result["trackingCookiesBefore"]=tracker_cookie_names(cookies_before)
        accept=find_choice(initial,"accept");reject=find_choice(initial,"reject")
        result["acceptClicks"]=1 if accept else None
        reject_steps=0;applied=False;attempted=False
        if reject:
            attempted=True;reject_steps=1
            phase[0]="after-reject"
            applied=await click_choice(reject)
        elif initial["banner"]:
            settings=find_choice(initial,"settings")
            if settings:
                attempted=True
                opened=await click_choice(settings)
                if opened:
                    await page.wait_for_timeout(700)
                    second=await inspect(page)
                    reject2=find_choice(second,"reject")
                    if reject2:
                        reject_steps=2;phase[0]="after-reject";applied=await click_choice(reject2)
                        # A second layer can require an additional Save action.
                    else:
                        save=next((x for x in second["controls"] if re.search(r"^(?:selectie opslaan|keuze opslaan|save (?:choices|preferences|selection)|bevestig|confirm)\b",x["text"],re.I) and x["inViewport"]),None)
                        if save:
                            reject_steps=2;phase[0]="after-reject";applied=await click_choice(save)
                if not opened:result["warnings"].append("Settings control found but could not be clicked")
        if applied:
            await page.wait_for_timeout(800)
            after=await inspect(page)
            if after["banner"] and find_choice(after,"reject"):
                result["warnings"].append("Consent dialog appears to remain open after rejection")
            result["rejectClicks"]=reject_steps
            phase[0]="after-reject"
            result["evidence"]["afterRejectScreenshot"]=await capture(page,ev_dir/"after-reject.jpg")
            try:
                await page.reload(wait_until="domcontentloaded",timeout=args.timeout_ms)
                await page.wait_for_timeout(args.wait_ms)
            except Exception as e:
                result["warnings"].append("Reload after reject failed: "+type(e).__name__)
            result["trackingCookiesAfterReject"]=tracker_cookie_names(await context.cookies())
        elif attempted:
            result["warnings"].append("Rejection flow not completed/verified")
        # UI tests: only when we have evidence the page is a consent UI and accept action exists.
        if not initial["banner"]:
            for k in ("rejectAvailable","sameLayer","equalEffort","rejectVisible"):
                result["checks"][k]=mark("unknown","No consent banner detected; may not be required, may be delayed or missed")
        elif not accept:
            for k in ("rejectAvailable","sameLayer","equalEffort","rejectVisible"):
                result["checks"][k]=mark("unknown","Could not identify a direct accept action in the initial consent layer")
        else:
            if reject and applied:
                result["checks"]["rejectAvailable"]=mark("pass","Direct rejection control clicked")
                result["checks"]["sameLayer"]=mark("pass","Accept and reject exposed in initial consent layer")
                result["checks"]["equalEffort"]=mark("pass","Both direct actions take one click")
                s,why=button_visibility(reject,accept)
                result["checks"]["rejectVisible"]=mark(s,why)
            elif reject:
                result["checks"]["rejectAvailable"]=mark("unknown","A reject-labelled control exists, but clicking it failed")
                result["checks"]["sameLayer"]=mark("pass","A reject-labelled control is visible on the initial layer")
                result["checks"]["equalEffort"]=mark("unknown","Reject click could not be verified")
                s,why=button_visibility(reject,accept)
                result["checks"]["rejectVisible"]=mark(s,why)
            else:
                result["checks"]["rejectAvailable"]=mark("pass" if applied else "unknown",
                     "Reject reachable via settings" if applied else "Could not verify any completed rejection path")
                result["checks"]["sameLayer"]=mark("fail","Accept action exists on initial layer but reject does not")
                result["checks"]["equalEffort"]=mark("fail" if applied and reject_steps>1 else "unknown",
                    f"Reject took {reject_steps} clicks versus 1 to accept" if applied else "Reject click count could not be established")
                result["checks"]["rejectVisible"]=mark("fail","No directly visible reject option on initial layer")
        before_events=[e for e in events if e["phase"]=="before"]
        after_events=[e for e in events if e["phase"]=="after-reject"]
        before_indicators=len(before_events)+len(result["trackingCookiesBefore"])
        after_indicators=len(after_events)+len(result["trackingCookiesAfterReject"])
        if before_indicators:
            result["checks"]["noTrackingBefore"]=mark("fail",f"{len(before_events)} known collection requests and {len(result['trackingCookiesBefore'])} tracker-like cookie names observed pre-consent; requires review")
        else:
            result["checks"]["noTrackingBefore"]=mark("pass","No known collection endpoints or tracker-like cookie names observed; not proof of absence")
        if not applied:
            result["checks"]["noTrackingAfterReject"]=mark("unknown","No verified rejection and reload")
        elif after_indicators:
            result["checks"]["noTrackingAfterReject"]=mark("fail",f"{len(after_events)} known collection requests and {len(result['trackingCookiesAfterReject'])} tracker-like cookie names observed after reject; requires review")
        else:
            result["checks"]["noTrackingAfterReject"]=mark("pass","No known collection endpoints or tracker-like cookie names observed after reject and reload")
        result["trackerEvents"]=events
        result["requestCount"]=counts["requests"]
        result["status"]="scanned"
    except (PWTimeout,Exception) as e:
        result["status"]="error"
        result["warnings"].append(f"Scan incomplete: {type(e).__name__}: {str(e)[:170]}")
        result["evidence"]["errorScreenshot"]=await capture(page,ev_dir/"error.jpg")
        for k in ("rejectAvailable","sameLayer","equalEffort","rejectVisible","noTrackingBefore","noTrackingAfterReject"):
            result["checks"][k]=mark("unknown","Scan incomplete or blocked")
    finally:
        await context.close()
    vals=[x["status"] for x in result["checks"].values()]
    result["overall"]="fail" if "fail" in vals else ("pass" if vals and all(v=="pass" for v in vals) else "unknown")
    return result


def targets_from_csv(path):
    targets=[];seen=set()
    with open(path,newline="",encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            raw=(row.get("url") or row.get("domain") or "").strip()
            if not raw or raw.startswith("#"):continue
            url=raw if raw.startswith(("https://","http://","file://")) else "https://"+raw
            hostname=(urlsplit(url).hostname or "").lower()
            if not hostname or hostname in seen:continue
            seen.add(hostname)
            targets.append({"domain":hostname.removeprefix("www."),"name":row.get("name") or hostname,
                "consortium":row.get("consortium") or "Unknown","rank":int(row["rank"]) if (row.get("rank") or "").isdigit() else None,"url":url})
    return targets


async def main(args):
    targets=targets_from_csv(args.targets)[:args.limit]
    views=[x.strip() for x in args.viewports.split(",")]
    if not views or any(x not in ("mobile","desktop") for x in views):
        raise SystemExit("--viewports must be mobile, desktop, or mobile,desktop")
    output=Path(args.output);output.mkdir(parents=True,exist_ok=True)
    chromium=os.environ.get("CHROME_BIN") or shutil.which("chromium") or shutil.which("google-chrome")
    sem=asyncio.Semaphore(args.concurrency)
    async with async_playwright() as pw:
        browser=await pw.chromium.launch(headless=not args.headful,executable_path=chromium or None,
            args=["--disable-dev-shm-usage"])
        async def worker(target,view):
            file=output/f"{target['domain'].replace('.','_')}-{view}.json"
            if file.exists() and not args.force:
                return file
            async with sem:
                result=await run_one(browser,target,view,args)
                file.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
                print(f"{result['overall']:7s} {target['domain']:32s} {view:7s} {result['status']}",flush=True)
                return file
        await asyncio.gather(*(worker(t,v) for t in targets for v in views))
        await browser.close()
    print(f"Saved {len(targets)*len(views)} audits. Run: python export.py --targets {args.targets} --results {output}")

if __name__=="__main__":
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--targets",default="config/seed_sites.csv")
    ap.add_argument("--output",default="results")
    ap.add_argument("--limit",type=int,default=1000)
    ap.add_argument("--viewports",default="mobile,desktop")
    ap.add_argument("--concurrency",type=int,default=5)
    ap.add_argument("--timeout-ms",type=int,default=22000)
    ap.add_argument("--wait-ms",type=int,default=1800)
    ap.add_argument("--headful",action="store_true")
    ap.add_argument("--force",action="store_true",help="Replace existing result files")
    asyncio.run(main(ap.parse_args()))