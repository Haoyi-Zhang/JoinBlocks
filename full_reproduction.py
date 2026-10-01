#!/usr/bin/env python3
"""Run every retained scientific campaign and semantic comparison offline."""
from __future__ import annotations
import argparse, json, os, shlex, subprocess, sys, time
from pathlib import Path

SOURCE_ROOT = Path(__file__).resolve().parent


def run(root: Path, name: str, args: list[str], records: list[dict]) -> None:
    logs=root/'logs'; logs.mkdir(parents=True,exist_ok=True)
    env=dict(os.environ); env.update({'PYTHONHASHSEED':'0','LC_ALL':'C.UTF-8','LANG':'C.UTF-8'})
    start=time.time()
    with (logs/f'{name}.stdout').open('w',encoding='utf-8') as out, (logs/f'{name}.stderr').open('w',encoding='utf-8') as err:
        cp=subprocess.run(args,stdout=out,stderr=err,env=env,check=False,cwd=SOURCE_ROOT)
    rec={'name':name,'command':shlex.join(args),'returncode':cp.returncode,'wall_seconds_observed':round(time.time()-start,6)}
    records.append(rec)
    # Persist attempted stages even when one fails; never report a truncated run as complete.
    partial={'schema_version':1,'offline':True,'commands':records,
             'completed':False,'all_returncodes_zero':all(r['returncode']==0 for r in records)}
    (root/'manifest.json').write_text(json.dumps(partial,sort_keys=True,indent=2)+'\n')
    if cp.returncode:
        raise SystemExit(f"{name} failed; inspect {logs/name}.stderr")


def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--output',type=Path,required=True); ap.add_argument('--python',default=sys.executable)
    a=ap.parse_args(); root=a.output.resolve()
    if root.exists() and any(root.iterdir()): raise SystemExit('output directory must be absent or empty')
    root.mkdir(parents=True,exist_ok=True)
    py=a.python; records=[]
    campaign=root/'campaign'; att=root/'attestation'; controls=root/'controls'; summary=root/'summary'; inputs=root/'inputs'; topology=root/'topology'; tests=root/'tests'
    example=root/'example-certificate.json'
    commands=[
      ('tests',[py,'test_protocol.py','--output',str(tests)]),
      ('audit-tests',[py,'audit_test_protocol.py','--output',str(root/'audit-tests'),'--retained','results/audit-tests']),
      ('campaign',[py,'reproduce.py','--output',str(campaign)]),
      ('attestation',[py,'attestation_campaign.py','--output',str(att)]),
      ('controls',[py,'controls.py','--output',str(controls)]),
      ('summary',[py,'summarize.py','--results',str(campaign),'--output',str(summary)]),
      ('inputs',[py,'generate_inputs.py',str(inputs)]),
      ('topology',[py,'topology_campaign.py','--output',str(topology)]),
      ('invariance',[py,'invariance_campaign.py','--output',str(root/'invariance')]),
      ('attestation-overhead',[py,'attestation_overhead.py','--results',str(att),'--output',str(att/'overhead.json'),'--expect-snapshots','306','--expect-rows','33204']),
      ('bibliography-audit',[py,'audit_bibliography.py','--paper','../paper','--ledger','docs/literature.json','--output',str(root/'bibliography-audit.json')]),
      ('example-produce',[py,'produce.py',str(inputs/'star-4-4-balanced-101.json'),str(example)]),
      ('retained-tests-compare',[py,'compare_tests.py','results/tests',str(tests)]),
      ('retained-core-compare',[py,'validate_reproduction.py','--campaign',str(campaign),'--attestation',str(att),'--controls',str(controls),'--summary',str(summary),'--inputs',str(inputs),'--example-certificate',str(example)]),
      ('retained-topology-compare',[py,'compare_topology.py','results/topology',str(topology)]),
      ('retained-invariance-compare',[py,'invariance_campaign.py','--compare','results/invariance',str(root/'invariance')]),
      ('chain',[py,'verify_chain.py',str(inputs/'star-4-4-balanced-101.json'),'results/attestation/examples/star-4-4-balanced-101-w0.snapshot.json','results/attestation/examples/star-4-4-balanced-101-w0.attestation.json',str(campaign/'certificates/star-4-4-balanced-101.json')]),
    ]
    # STANDALONE-BIBLIOGRAPHY-GATE
    paper_source = __import__("pathlib").Path(__file__).resolve().parent.parent / "paper"
    if not paper_source.is_dir():
        commands = [item for item in commands if "audit_bibliography.py" not in repr(item)]
    for name,args in commands: run(root,name,args,records)
    manifest={
      'schema_version':1,'offline':True,'completed':True,'commands':records,
      'all_returncodes_zero':all(r['returncode']==0 for r in records),
      'observational_timing_warning':'wall_seconds_observed is not used for semantic comparison or scientific claims.'
    }
    (root/'manifest.json').write_text(json.dumps(manifest,sort_keys=True,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(manifest,sort_keys=True,indent=2))

if __name__=='__main__': main()
