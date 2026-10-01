#!/usr/bin/env python3
"""Offline structural audit of the paper bibliography and literature ledger."""
from __future__ import annotations
import argparse, json, re, unicodedata
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


def reading_category(record: dict) -> str:
    """Classify the ledger's declared access depth, not what this audit read."""
    depth = str(record.get('reading') or record.get('access')
                or record.get('reading_depth') or record.get('depth') or '').lower()
    if any(term in depth for term in ('inaccessible', 'not counted', 'limited')):
        return 'limited'
    if depth in {'full-paper calibration reading', 'full-text reading'}:
        return 'full'
    return 'other'



def normalize(value: object) -> str:
    """Ignore typography, not author order, words, digits or identifiers."""
    text = str(value).replace(r'\i', 'i').replace(r'\ss', 'ss')
    text = text.replace(r'\ae', 'ae').replace(r'\oe', 'oe')
    text = unicodedata.normalize('NFKD', text)
    return ''.join(c for c in text.casefold() if c.isalnum())


def strip_comments(text: str) -> str:
    """Keep line numbers stable; only unescaped percent starts a comment."""
    lines = []
    for line in text.splitlines():
        for i, char in enumerate(line):
            if char == '%':
                n = 0
                j = i - 1
                while j >= 0 and line[j] == '\\':
                    n += 1
                    j -= 1
                if n % 2 == 0:
                    line = line[:i]
                    break
        lines.append(line)
    return '\n'.join(lines)


def active_sources(paper: Path) -> dict[str, str]:
    """Audit reachable manuscript inputs, never a citation in an unused .tex."""
    sources: dict[str, str] = {}
    include = re.compile(r'\\(?:input|include)\s*\{([^}]+)\}')
    roots = [paper/'main.tex']
    if (paper/'supplement.tex').exists():
        roots.append(paper/'supplement.tex')
    if not roots[0].is_file():
        raise ValueError('missing main.tex')
    def visit(path: Path) -> None:
        path = path.resolve()
        try:
            key = str(path.relative_to(paper.resolve()))
        except ValueError as exc:
            raise ValueError('manuscript input escapes paper directory') from exc
        if key in sources:
            return
        if not path.is_file():
            raise ValueError(f'missing manuscript input: {key}')
        text = strip_comments(path.read_text(encoding='utf-8'))
        sources[key] = text
        for match in include.finditer(text):
            child = Path(match.group(1))
            if not child.suffix:
                child = child.with_suffix('.tex')
            visit(paper/child)
    for root in roots:
        visit(root)
    return sources


def indexed_records(records: list[dict], label: str) -> dict[str, dict]:
    indexed: dict[str, dict] = {}
    for record in records:
        key = record.get('key')
        if not isinstance(key, str) or not key:
            raise ValueError(f'{label}: missing key')
        if key in indexed:
            raise ValueError(f'{label}: duplicate key {key}')
        indexed[key] = record
    return indexed


def run(paper: Path, ledger: Path, output: Path,
        min_references: int = 60, evidence: Path | None = None):
    bibs = list(paper.rglob('*.bib'))
    if len(bibs) != 1:
        raise ValueError(f'expected one .bib file, found {bibs}')
    entries = parse_bib(bibs[0].read_text(encoding='utf-8'))
    keys = [e['key'] for e in entries]
    if len(keys) != len(set(keys)):
        raise ValueError('duplicate bibliography key')
    if len(keys) < min_references:
        raise ValueError(f'fewer than {min_references} references')
    sources = active_sources(paper)
    citation_locations: dict[str, list[dict]] = {}
    for filename, text in sources.items():
        if re.search(r'\\nocite\b', text):
            raise ValueError('nocite is forbidden')
        for match in CITE.finditer(text):
            line = text.count('\n', 0, match.start()) + 1
            for key in match.group(1).split(','):
                citation_locations.setdefault(key.strip(), []).append(
                    {'file': filename, 'line': line})
    cited = set(citation_locations)
    if cited - set(keys):
        raise ValueError(f'unknown citation keys: {sorted(cited-set(keys))}')
    if set(keys) - cited:
        raise ValueError(f'uncited bibliography entries: {sorted(set(keys)-cited)}')
    records = ledger_records(json.loads(ledger.read_text(encoding='utf-8')))
    indexed = indexed_records(records, 'literature ledger')
    if set(indexed) != set(keys):
        raise ValueError('bibliography and literature ledger key sets differ')
    evidence = evidence or ledger.parent/'citation_evidence.json'
    ev = indexed_records(ledger_records(json.loads(evidence.read_text(encoding='utf-8'))),
                         'citation evidence')
    if set(ev) != set(keys):
        raise ValueError('bibliography and citation-evidence key sets differ')
    dois: set[str] = set()
    titles: set[str] = set()
    report = []
    for entry in entries:
        key, fields = entry['key'], entry['fields']
        record, support = indexed[key], ev[key]
        for field in ('author', 'title', 'year'):
            if not fields.get(field):
                raise ValueError(f'{key}: missing {field}')
        venue = fields.get('journal') or fields.get('booktitle')
        if not venue and entry['type'] not in ('misc','techreport','unpublished'):
            raise ValueError(f'{key}: missing journal/booktitle')
        if PLACEHOLDER.search(' '.join(fields.values())):
            raise ValueError(f'{key}: placeholder')
        if not re.fullmatch(r'(?:19|20)\d{2}', fields['year'].strip('{} ')):
            raise ValueError(f'{key}: invalid year')
        title = normalize(fields['title'])
        if title in titles:
            raise ValueError(f'{key}: duplicate work title (do not double-count editions)')
        titles.add(title)
        for field, target in (('author','authors'), ('title','title'), ('year','year'),
                              ('doi','doi'), ('pages','pages'), ('volume','volume'),
                              ('number','number')):
            if normalize(fields.get(field, '')) != normalize(record.get(target, '')):
                raise ValueError(f'{key}: bibliography/ledger {field} mismatch')
        if normalize(venue or '') != normalize(record.get('venue', '')):
            raise ValueError(f'{key}: bibliography/ledger venue mismatch')
        doi = fields.get('doi', '').removeprefix('https://doi.org/').strip().lower()
        if doi:
            if not DOI.fullmatch(doi):
                raise ValueError(f'{key}: invalid DOI')
            if doi in dois:
                raise ValueError(f'{key}: duplicate DOI')
            dois.add(doi)
        if fields.get('url') and not URL.fullmatch(fields['url']):
            raise ValueError(f'{key}: invalid bibliography URL')
        if not URL.fullmatch(str(record.get('url', ''))):
            raise ValueError(f'{key}: missing stable ledger URL')
        for field in ('source_url','source_locator','supported_claim','access_basis'):
            if not isinstance(support.get(field), str) or not support[field].strip():
                raise ValueError(f'{key}: missing evidence {field}')
        if not URL.fullmatch(support['source_url']):
            raise ValueError(f'{key}: invalid evidence URL')
        if not record.get('reading'):
            raise ValueError(f'{key}: missing reading-depth label')
        report.append({'key':key, 'identity_matches_ledger':True,
                       'cited_at':citation_locations[key],
                       'source_url':support['source_url'],
                       'source_locator':support['source_locator'],
                       'supported_claim':support['supported_claim'],
                       'access_basis':support['access_basis'],
                       'ledger_reading_category':reading_category(record)})
    categories = [reading_category(record) for record in records]
    result = {
        'schema_version':2, 'bibliography_entries':len(entries),
        'cited_entries':len(cited), 'uncited_entries':0, 'unknown_citations':0,
        'nocite_present':False, 'doi_entries':len(dois),
        'literature_ledger_records':len(records),
        'ledger_records_with_stable_url':len(records),
        'citation_evidence_records':len(ev),
        'ledger_full_text_records':categories.count('full'),
        'ledger_limited_access_records':categories.count('limited'),
        'ledger_other_or_metadata_records':categories.count('other'),
        'minimum_reference_count':min_references,
        'active_tex_sources':sorted(sources), 'references':report,
        'offline_scope':('Checks identity consistency, active citation locations and presence '
                         'of curated source/claim evidence. It does not independently authenticate '
                         'websites, certify every cited assertion, or turn metadata into full-text reading.')}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2)+'\n',
                      encoding='utf-8')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--paper', type=Path, required=True)
    parser.add_argument('--ledger', type=Path, required=True)
    parser.add_argument('--evidence', type=Path)
    parser.add_argument('--min-references', type=int, default=60)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = run(args.paper, args.ledger, args.output, args.min_references, args.evidence)
    print(json.dumps({key:value for key,value in result.items() if key != 'references'}, indent=2))

if __name__ == '__main__':
    main()
