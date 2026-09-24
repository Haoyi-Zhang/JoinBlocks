#!/usr/bin/env python3
"""Regenerate the fixed synthetic suite into a fresh directory (no downloads)."""
import argparse
from pathlib import Path
from src.generate import write_inputs
p=argparse.ArgumentParser(description=__doc__);p.add_argument('output',type=Path);a=p.parse_args()
if a.output.exists() and any(a.output.iterdir()):raise SystemExit('Choose a fresh directory.')
write_inputs(a.output)
print('Generated 102 declared instances.')
