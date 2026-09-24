#!/usr/bin/env python3
"""One-shot external metadata verification for the paper bibliography.

This script is deliberately not part of the offline reproduction path.  It resolves
DOIs through Crossref and checks non-DOI locators without downloading papers.  The
retained JSON is evidence of a dated metadata audit, not evidence of full-text
novelty review.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
import urllib.parse
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

STOP = {"a","an","and","as","at","by","for","from","in","of","on","or","the","to","with"}


def read_entries(text: str) -> list[tuple[str, str, str]]:
    out: list[tuple[str, str, str]] = []
    pos = 0
    while True:
        m = re.search(r"@(\w+)\s*\{\s*([^,]+),", text[pos:], re.I)
        if not m:
            break
        start = pos + m.start()
        body_start = pos + m.end()
        depth = 1
        quote = False
        esc = False
        i = body_start
        while i < len(text) and depth:
            ch = text[i]
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                quote = not quote
            elif not quote and ch == "{":
                depth += 1
            elif not quote and ch == "}":
                depth -= 1
            i += 1
        if depth:
            raise ValueError(f"unterminated BibTeX entry at {start}")
        out.append((m.group(1).lower(), m.group(2).strip(), text[body_start:i-1]))
        pos = i
    return out


def parse_fields(body: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    i = 0
    n = len(body)
    while i < n:
        while i < n and (body[i].isspace() or body[i] == ','):
            i += 1
        m = re.match(r"([A-Za-z][A-Za-z0-9_-]*)\s*=\s*", body[i:])
        if not m:
            # tolerate trailing comments/whitespace, but not a hidden field
            i += 1
            continue
        key = m.group(1).lower()
        i += m.end()
        if i >= n:
            raise ValueError(f"missing value for {key}")
        if body[i] == "{":
            depth = 1; j = i + 1; esc = False
            while j < n and depth:
                ch = body[j]
                if esc: esc = False
                elif ch == "\\": esc = True
                elif ch == "{": depth += 1
                elif ch == "}": depth -= 1
                j += 1
            if depth: raise ValueError(f"unterminated braced field {key}")
            value = body[i+1:j-1]
            i = j
        elif body[i] == '"':
            j = i + 1; esc = False
            while j < n:
                ch = body[j]
                if esc: esc = False
                elif ch == "\\": esc = True
                elif ch == '"': break
                j += 1
            if j >= n: raise ValueError(f"unterminated quoted field {key}")
            value = body[i+1:j]
            i = j + 1
        else:
            j = i
            while j < n and body[j] != ',': j += 1
            value = body[i:j].strip()
            i = j
        fields[key] = value.strip()
    return fields


def plain(s: str) -> str:
    s = re.sub(r"\\[A-Za-z]+\s*", " ", s)
    s = s.replace("~", " ")
    s = re.sub(r"[{}$\\]", "", s)
    s = re.sub(r"[^0-9A-Za-z]+", " ", s).lower()
    return " ".join(s.split())


def title_similarity(a: str, b: str) -> float:
    pa, pb = plain(a), plain(b)
    ta = {x for x in pa.split() if x not in STOP}
    tb = {x for x in pb.split() if x not in STOP}
    jac = len(ta & tb) / max(1, len(ta | tb))
    seq = SequenceMatcher(None, pa, pb).ratio()
    return max(jac, seq)


def curl_json(url: str, timeout: int) -> tuple[int, dict[str, Any] | None, str]:
    proc = subprocess.run(
        ["curl", "-L", "--silent", "--show-error", "--max-time", str(timeout),
         "-A", "proof-carrying-robust-plan-reference-audit/1.0", "-w", "\n%{http_code}", url],
        text=True, capture_output=True,
    )
    if proc.returncode != 0:
        return 0, None, proc.stderr.strip()
    payload, _, code_s = proc.stdout.rpartition("\n")
    try: code = int(code_s.strip())
    except ValueError: return 0, None, f"invalid HTTP trailer: {code_s!r}"
    try: data = json.loads(payload) if payload.strip() else None
    except json.JSONDecodeError as exc: return code, None, f"JSON parse error: {exc}"
    return code, data, ""


def check_url(url: str, timeout: int) -> tuple[int, str, str]:
    proc = subprocess.run(
        ["curl", "-L", "--silent", "--show-error", "--max-time", str(timeout),
         "-A", "proof-carrying-robust-plan-reference-audit/1.0", "-o", "/dev/null",
         "-w", "%{http_code}\n%{url_effective}", url],
        text=True, capture_output=True,
    )
    lines=proc.stdout.splitlines()
    code=int(lines[0]) if lines and lines[0].isdigit() else 0
    effective=lines[1] if len(lines)>1 else ""
    return code,effective,proc.stderr.strip()


def crossref_year(msg: dict[str, Any]) -> int | None:
    for key in ("published-print","published-online","published","issued","created"):
        parts=((msg.get(key) or {}).get("date-parts") or [])
        if parts and parts[0]:
            try: return int(parts[0][0])
            except (TypeError,ValueError): pass
    return None


def main() -> int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--paper", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--as-of", required=True)
    ap.add_argument("--timeout", type=int, default=25)
    ns=ap.parse_args()
    bibs=sorted(ns.paper.rglob("*.bib"))
    if not bibs: raise SystemExit("no .bib file under --paper")
    entries=[]
    for bib in bibs:
        for typ,key,body in read_entries(bib.read_text(errors="strict")):
            f=parse_fields(body); f["entry_type"]=typ; f["key"]=key; f["source_bib"]=str(bib.relative_to(ns.paper)); entries.append(f)
    results=[]
    doi_failures=[]
    non_doi_unreachable=[]
    for idx,f in enumerate(entries):
        title=f.get("title","")
        year=int(re.sub(r"\D","",f.get("year","0"))[:4] or 0)
        doi=f.get("doi","").strip().lower().removeprefix("https://doi.org/").removeprefix("http://doi.org/")
        record={"key":f["key"],"entry_type":f["entry_type"],"title":title,"year":year,"doi":doi or None,"url":f.get("url") or None}
        if doi:
            url="https://api.crossref.org/works/"+urllib.parse.quote(doi,safe="")
            code,data,error=curl_json(url,ns.timeout)
            msg=(data or {}).get("message") if isinstance(data,dict) else None
            cr_title=""
            if isinstance(msg,dict):
                titles=msg.get("title") or []
                cr_title=str(titles[0]) if titles else ""
            cr_doi=str((msg or {}).get("DOI","")).lower() if isinstance(msg,dict) else ""
            cr_year=crossref_year(msg) if isinstance(msg,dict) else None
            sim=title_similarity(title,cr_title) if cr_title else 0.0
            ok=(code==200 and cr_doi==doi and sim>=0.60 and (not year or cr_year is None or abs(year-cr_year)<=2))
            record["external"]={"service":"Crossref","http_status":code,"resolved_doi":cr_doi or None,"resolved_title":cr_title or None,"resolved_year":cr_year,"title_similarity":round(sim,4),"error":error or None,"verified":ok}
            if not ok: doi_failures.append(f["key"])
        else:
            url=f.get("url","")
            code,effective,error=check_url(url,ns.timeout) if url else (0,"","missing URL")
            # 403/429 still demonstrates a live protected endpoint; the structural audit separately checks locator syntax.
            ok=code in set(range(200,400))|{401,403,429}
            record["external"]={"service":"publisher-or-archive locator","http_status":code,"effective_url":effective or None,"error":error or None,"verified":ok}
            if not ok: non_doi_unreachable.append(f["key"])
        results.append(record)
        time.sleep(0.12)
    summary={
        "as_of":ns.as_of,
        "entries":len(results),
        "doi_entries":sum(1 for r in results if r["doi"]),
        "doi_verified":sum(1 for r in results if r["doi"] and r["external"]["verified"]),
        "non_doi_entries":sum(1 for r in results if not r["doi"]),
        "non_doi_locator_verified":sum(1 for r in results if not r["doi"] and r["external"]["verified"]),
        "doi_failures":doi_failures,
        "non_doi_unreachable":non_doi_unreachable,
        "scope":"Metadata and locator verification only; not a full-text or novelty audit.",
    }
    ns.output.parent.mkdir(parents=True,exist_ok=True)
    ns.output.write_text(json.dumps({"summary":summary,"records":results},indent=2,ensure_ascii=False)+"\n")
    print(json.dumps(summary,indent=2))
    return 1 if doi_failures else 0

if __name__=="__main__":
    raise SystemExit(main())
