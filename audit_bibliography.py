#!/usr/bin/env python3
"""Offline structural audit of the paper bibliography and literature ledger."""
from __future__ import annotations
import argparse, hashlib, json, re
from pathlib import Path

ENTRY_START=re.compile(r'@(\w+)\s*\{\s*([^,\s]+)\s*,',re.I)
FIELD=re.compile(r'(?ms)^\s*([A-Za-z][\w-]*)\s*=\s*(\{(?:[^{}]|\{[^{}]*\})*\}|"(?:[^"\\]|\\.)*"|[^,\n]+)\s*,?')
CITE=re.compile(r'\\cite\w*\s*(?:\[[^\]]*\]\s*)*\{([^}]+)\}')
DOI=re.compile(r'^10\.\d{4,9}/\S+$',re.I)
URL=re.compile(r'^https?://\S+$',re.I)
PLACEHOLDER=re.compile(r'\b(?:tbd|todo|placeholder|anonymous repository|example\.com|xxx+)\b',re.I)


def parse_bib(text: str):
    entries=[]; pos=0
    while True:
        m=ENTRY_START.search(text,pos)
        if not m: break
        depth=1; i=m.end()
        while i < len(text) and depth:
            if text[i]=='{': depth+=1
            elif text[i]=='}': depth-=1
            i+=1
        if depth: raise ValueError(f'unclosed BibTeX entry {m.group(2)}')
        body=text[m.end():i-1]
        fields={}
        for fm in FIELD.finditer(body):
            v=fm.group(2).strip()
            if (v.startswith('{') and v.endswith('}')) or (v.startswith('"') and v.endswith('"')):
                v=v[1:-1]
            fields[fm.group(1).lower()]=v.strip()
        entries.append({'type':m.group(1).lower(),'key':m.group(2),'fields':fields})
        pos=i
    return entries


def ledger_records(value):
    if isinstance(value,list) and all(isinstance(x,dict) for x in value): return value
    if isinstance(value,dict):
        for key in ('papers','references','entries','literature','records'):
            if isinstance(value.get(key),list): return value[key]
    raise ValueError('unrecognized literature ledger shape')


def run(paper: Path, ledger: Path, output: Path):
    bibs=list(paper.rglob('*.bib'))
    if len(bibs)!=1: raise ValueError(f'expected one .bib file, found {bibs}')
    bib_text=bibs[0].read_text(encoding='utf-8')
    entries=parse_bib(bib_text)
    keys=[e['key'] for e in entries]
    if len(keys)!=len(set(keys)): raise ValueError('duplicate bibliography key')
    tex='\n'.join(p.read_text(encoding='utf-8') for p in paper.rglob('*.tex'))
    if '\\nocite' in tex: raise ValueError('nocite is forbidden in the final paper')
    cited=set()
    for m in CITE.finditer(tex): cited.update(k.strip() for k in m.group(1).split(','))
    unknown=sorted(cited-set(keys)); uncited=sorted(set(keys)-cited)
    if unknown: raise ValueError(f'unknown citation keys: {unknown}')
    if uncited: raise ValueError(f'uncited bibliography entries: {uncited}')
    dois=[]; urls=[]
    for e in entries:
        f=e['fields']; missing=[x for x in ('author','title','year') if not f.get(x)]
        if e['type'] not in ('misc','techreport','unpublished') and not (f.get('journal') or f.get('booktitle')):
            missing.append('journal/booktitle')
        if missing: raise ValueError(f"{e['key']} missing {missing}")
        blob=' '.join(f.values())
        if PLACEHOLDER.search(blob): raise ValueError(f"placeholder text in {e['key']}")
        year=f['year'].strip('{} ')
        if not re.fullmatch(r'(?:19|20)\d{2}',year): raise ValueError(f"invalid year in {e['key']}: {year}")
        if 'doi' in f:
            doi=f['doi'].replace('https://doi.org/','').strip()
            if not DOI.match(doi): raise ValueError(f"invalid DOI in {e['key']}: {doi}")
            dois.append(doi.lower())
        if 'url' in f:
            url=f['url'].strip()
            if not URL.match(url): raise ValueError(f"invalid URL in {e['key']}: {url}")
            urls.append(url)
    if len(dois)!=len(set(dois)): raise ValueError('duplicate DOI')
    ledger_value=json.loads(ledger.read_text(encoding='utf-8'))
    records=ledger_records(ledger_value)
    stable_url_count=0; full=metadata=limited=0
    for record in records:
        joined=json.dumps(record,sort_keys=True).lower()
        if 'http://' in joined or 'https://' in joined: stable_url_count+=1
        depth=str(record.get('access') or record.get('reading_depth') or record.get('depth') or '').lower()
        if 'full' in depth: full+=1
        elif 'limit' in depth: limited+=1
        else: metadata+=1
    result={
      'schema_version':1,'bibliography_entries':len(entries),'cited_entries':len(cited),
      'uncited_entries':0,'unknown_citations':0,'nocite_present':False,
      'doi_entries':len(dois),'url_entries_in_bib':len(urls),
      'literature_ledger_records':len(records),'ledger_records_with_stable_url':stable_url_count,
      'ledger_full_text_records':full,'ledger_limited_access_records':limited,
      'ledger_other_or_metadata_records':metadata,
      'bib_sha256':hashlib.sha256(bib_text.encode()).hexdigest(),
      'ledger_sha256':hashlib.sha256(ledger.read_bytes()).hexdigest(),
      'offline_scope':'Structural consistency only; DOI/URL existence and theorem-level novelty require external source access and expert review.'
    }
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(result,sort_keys=True,indent=2)+'\n',encoding='utf-8')
    return result


def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--paper',type=Path,required=True); ap.add_argument('--ledger',type=Path,required=True); ap.add_argument('--output',type=Path,required=True)
    a=ap.parse_args(); print(json.dumps(run(a.paper,a.ledger,a.output),sort_keys=True,indent=2))
if __name__=='__main__': main()
