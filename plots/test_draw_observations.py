"""Standard-library tests for the optional renderer; no PDF/science execution."""
import copy
import csv
import math
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
import draw_observations as plot


class ObservationsTests(unittest.TestCase):
    def setUp(self):
        with (plot.ARTIFACT/'results/campaign/cases.csv').open(newline='',encoding='utf-8') as stream:
            self.raw=list(csv.DictReader(stream))

    def reject_edit(self,key,value):
        raw=copy.deepcopy(self.raw)
        raw[0][key]=value
        with self.assertRaises(ValueError):
            plot.validate_rows(raw)

    def test_standard_library_import(self):
        self.assertIsNone(plot.pdfmetrics)
        self.assertIsNone(plot.canvas)

    def test_all_102_cases_and_coincident_points_retained(self):
        tables=plot.load_observations(plot.ARTIFACT/'results/campaign')
        for name,rows in tables.items():
            self.assertEqual(len(rows),102)
            self.assertEqual([r['n'] for r in rows],[r['n'] for r in self.raw])
        rows=tables['frontiers.dat']
        self.assertLess(len({(r['component'],r['contract']) for r in rows}),102)
        for name in tables:
            columns=('contract','component','n','k') if name=='frontiers.dat' else ('producer','checker','n','k')
            expected=(plot.ARTIFACT/'results/summary'/name).read_text(encoding='utf-8')
            self.assertEqual(plot.dat_text(tables[name],columns),expected)

    def test_missing_duplicate_and_unknown_cases_rejected(self):
        with self.assertRaises(ValueError): plot.validate_rows(self.raw[:-1])
        raw=copy.deepcopy(self.raw);raw[-1]=raw[0]
        with self.assertRaises(ValueError): plot.validate_rows(raw)
        self.reject_edit('case','../unknown')

    def test_wrong_case_metadata_rejected(self):
        for key,value in (('family','star'),('regime','filtered'),('n','7'),('k','6')):
            with self.subTest(key=key):self.reject_edit(key,value)

    def test_nonfinite_negative_zero_and_out_of_axes_times_rejected(self):
        for value in ('nan','inf','-1','0','0.00001','0.121','not-a-number'):
            with self.subTest(value=value):self.reject_edit('producer_cpu_s',value)

    def test_counts_frontiers_and_failed_cases_rejected(self):
        for key,value in (('root_frontier','1.5'),('root_frontier','-1'),('root_frontier','0'),
                          ('component_frontier','41'),('oracle_match','False'),('checker_accepted','False'),
                          ('plans','True'),('point_regret','-1')):
            with self.subTest(key=key,value=value):self.reject_edit(key,value)
        raw=copy.deepcopy(self.raw);raw[0]['regret']='1'
        with self.assertRaises(ValueError):plot.validate_rows(raw)

    def test_malformed_columns_and_header_rejected(self):
        raw=copy.deepcopy(self.raw);raw[0]['extra']='1'
        with self.assertRaises(ValueError):plot.validate_rows(raw)
        raw=copy.deepcopy(self.raw);raw[0]['n']=None
        with self.assertRaises(ValueError):plot.validate_rows(raw)
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'cases.csv'
            path.write_text('case,case\nx,x\n',encoding='utf-8')
            with self.assertRaises(ValueError):plot.load_observations(directory)

    def test_render_points_and_geometry_independent_of_display_width(self):
        tables=plot.load_observations(plot.ARTIFACT/'results/campaign')
        histories=[]
        for display in (241.1475,430.00462):
            with patch.object(plot,'new_pdf',return_value=Mock()), \
                 patch.object(plot,'axes',side_effect=lambda *a,**kw:lambda x,y:(float(x),float(y))) as axes, \
                 patch.object(plot,'line_points') as points:
                plot.draw(241.1475*plot.PT,tables,Path('unused'),display)
                self.assertEqual([len(c.args[1]) for c in points.call_args_list],[102,102])
                self.assertTrue(all(c.kwargs['connect'] is False for c in points.call_args_list))
                expected_size=8*plot.PT*241.1475/display
                for call in axes.call_args_list:
                    self.assertAlmostEqual(call.kwargs['ticksize'],expected_size)
                    self.assertAlmostEqual(call.kwargs['labelsize'],expected_size)
                histories.append(([(c.args[1:],c.kwargs) for c in points.call_args_list],
                                  [c.args[1:8] for c in axes.call_args_list]))
        self.assertEqual(histories[0],histories[1])

    def test_invalid_display_width_and_protected_output_rejected(self):
        for value in (0,-1,float('nan'),float('inf')):
            with self.assertRaises(ValueError):plot.draw(240,{},Path('unused'),value)
        with self.assertRaises(ValueError):plot.prepare_output_dir(plot.ARTIFACT/'plots')


if __name__=='__main__':
    unittest.main(verbosity=2)
