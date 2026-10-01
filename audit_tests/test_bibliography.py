"""Offline evidence-adapter regression tests; not part of the 68 science tests."""
from __future__ import annotations
import json
import tempfile
import unittest
from pathlib import Path
from audit_bibliography import run, reading_category

BIB = '''@article{known,
 author = {Alice A. Example and Bob B. Scholar},
 title = {{A Realistically Shaped Test Fixture}},
 year = {2001},
 journal = {Fixture Journal},
 volume = {2},
 number = {1},
 pages = {10--20},
 doi = {10.1234/fixture}
}
'''
# These are explicitly fictitious offline fixtures, never manuscript sources.
RECORD = dict(key='known', authors='Alice A. Example and Bob B. Scholar',
              title='A Realistically Shaped Test Fixture', year='2001',
              venue='Fixture Journal', volume='2', number='1', pages='10--20',
              doi='10.1234/fixture', url='https://doi.org/10.1234/fixture',
              reading='offline test fixture, not a published reference')
SUPPORT = dict(key='known', source_url='https://doi.org/10.1234/fixture',
               source_locator='fictitious fixture', supported_claim='fixture identity only',
               access_basis='offline fixture')

class BibliographyTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name); self.paper=self.root/'paper'; self.paper.mkdir()
        self.bib=self.paper/'references.bib'; self.bib.write_text(BIB)
        self.main=self.paper/'main.tex'; self.main.write_text(r'\cite{known}')
        self.ledger=self.root/'literature.json'; self.evidence=self.root/'citation_evidence.json'
        self.save(self.ledger,[RECORD]); self.save(self.evidence,[SUPPORT])
    def save(self,path,value): path.write_text(json.dumps(value))
    def check(self): return run(self.paper,self.ledger,self.root/'audit.json',1,self.evidence)
    def rejects(self,pattern):
        with self.assertRaisesRegex(ValueError,pattern): self.check()
    def change_record(self,field,value):
        obj=dict(RECORD); obj[field]=value; self.save(self.ledger,[obj])
    def test_valid_fixture(self): self.assertEqual(self.check()['cited_entries'],1)
    def test_wrong_author_rejected(self):
        self.change_record('authors','A Different Person'); self.rejects('author mismatch')
    def test_author_order_rejected(self):
        self.change_record('authors','Bob B. Scholar and Alice A. Example');self.rejects('author mismatch')
    def test_wrong_title_rejected(self):
        self.change_record('title','Another result');self.rejects('title mismatch')
    def test_wrong_year_rejected(self):
        self.change_record('year','2002');self.rejects('year mismatch')
    def test_wrong_doi_rejected(self):
        self.change_record('doi','10.1234/other');self.rejects('doi mismatch')
    def test_wrong_pages_rejected(self):
        self.change_record('pages','10--21');self.rejects('pages mismatch')
    def test_missing_ledger_record_rejected(self):
        self.save(self.ledger,[]);self.rejects('key sets differ')
    def test_duplicate_ledger_record_rejected(self):
        self.save(self.ledger,[RECORD,RECORD]);self.rejects('duplicate key')
    def test_duplicate_bib_key_rejected(self):
        self.bib.write_text(BIB+BIB);self.rejects('duplicate bibliography key')
    def test_unused_entry_rejected(self):
        self.main.write_text('No citation.');self.rejects('uncited')
    def test_comment_citation_is_not_counted(self):
        self.main.write_text('% '+r'\cite{known}');self.rejects('uncited')
    def test_orphan_tex_citation_is_not_counted(self):
        self.main.write_text('No citation.');(self.paper/'unused.tex').write_text(r'\cite{known}');self.rejects('uncited')
    def test_reachable_input_is_counted(self):
        self.main.write_text(r'\input{body}');(self.paper/'body.tex').write_text(r'\cite{known}')
        self.assertEqual(self.check()['references'][0]['cited_at'][0]['file'],'body.tex')
    def test_unknown_citation_rejected(self):
        self.main.write_text(r'\cite{known,unknown}');self.rejects('unknown citation')
    def test_nocite_rejected(self):
        self.main.write_text(r'\nocite{known}');self.rejects('nocite')
    def test_missing_evidence_record_rejected(self):
        self.save(self.evidence,[]);self.rejects('citation-evidence key sets')
    def test_missing_claim_rejected(self):
        obj=dict(SUPPORT);obj['supported_claim']='';self.save(self.evidence,[obj]);self.rejects('supported_claim')
    def test_minimum_count_enforced(self):
        with self.assertRaisesRegex(ValueError,'fewer than 60'):
            run(self.paper,self.ledger,self.root/'audit.json',60,self.evidence)
    def test_typographic_accents_normalize(self):
        self.bib.write_text(BIB.replace('Alice A. Example',r'Alice {\"O}st'))
        self.change_record('authors','Alice Öst and Bob B. Scholar');self.check()
    def test_reading_negation_is_not_full(self):
        self.assertNotEqual(reading_category({'reading':'limited: not counted as a full-paper read'}),'full')
    def test_duplicate_work_title_rejected(self):
        self.bib.write_text(BIB+BIB.replace('{known,','{second,').replace('10.1234/fixture','10.1234/second'))
        second=dict(RECORD,key='second',doi='10.1234/second')
        self.save(self.ledger,[RECORD,second]);self.save(self.evidence,[SUPPORT,dict(SUPPORT,key='second')])
        self.main.write_text(r'\cite{known,second}');self.rejects('duplicate work title')
    def test_missing_input_rejected(self):
        self.main.write_text(r'\input{missing}');self.rejects('missing manuscript input')
    def test_input_outside_paper_rejected(self):
        (self.root/'outside.tex').write_text(r'\cite{known}');self.main.write_text(r'\input{../outside.tex}');self.rejects('escapes')
    def test_escaped_percent_retains_citation(self):
        self.main.write_text(r'100\% ordinary text \cite{known}');self.assertEqual(self.check()['cited_entries'],1)
