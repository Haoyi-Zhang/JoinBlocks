#!/usr/bin/env python3
"""Run bibliography and evidence-comparison tests separately from the scientific suite."""
from __future__ import annotations
import argparse,inspect,json,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parent

def flatten(suite):
    for item in suite:
        if isinstance(item,unittest.TestSuite):yield from flatten(item)
        else:yield item

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--retained',type=Path)
    args=parser.parse_args()
    if args.retained and args.retained.resolve()==args.output.resolve():
        parser.error('retained and output directories must differ')
    args.output.mkdir(parents=True,exist_ok=True)
    suite=unittest.TestLoader().discover(str(ROOT/'audit_tests'))
    inventory=[]
    for test in flatten(suite):
        method=getattr(type(test),test._testMethodName)
        inventory.append({'id':test.id(),'source':str(Path(inspect.getsourcefile(method)).relative_to(ROOT)),
                          'line':inspect.getsourcelines(method)[1],
                          'input':('temporary, explicitly fictitious bibliography fixture' if 'bibliography' in test.id() else 'temporary invariance campaign; corrupted fresh comparison copy')})
    (args.output/'inventory.json').write_text(json.dumps(inventory,indent=2)+'\n')
    with (args.output/'unittest.log').open('w') as stream:
        result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
    summary={'tests_run':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),
             'skipped':len(result.skipped),'successful':result.wasSuccessful(),
             'scope':'Bibliography and invariance-comparison adapter tests; separate from 68 scientific methods.'}
    (args.output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary))
    if args.retained:
        for name in ('inventory.json','summary.json'):
            if json.loads((args.retained/name).read_text())!=json.loads((args.output/name).read_text()):
                raise RuntimeError('retained audit-test '+name+' differs')
        print('retained audit inventory and summary match')
    return 0 if result.wasSuccessful() else 1
if __name__=='__main__':raise SystemExit(main())
