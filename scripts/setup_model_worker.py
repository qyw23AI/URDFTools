#!/usr/bin/env python3
"""Install or verify the isolated, exactly version-pinned build123d worker."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
PYTHON=ROOT/'.tools/model-venv/bin/python'
SEED=ROOT/'.tools/python/bin/python'
LOCK=ROOT/'model-requirements.lock'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify',action='store_true')
    parser.add_argument('--offline',action='store_true')
    args=parser.parse_args()
    if not LOCK.is_file() or not SEED.is_file():
        print('Pinned runtime or model lock missing',file=sys.stderr);return 2
    env={key:value for key,value in os.environ.items() if key not in ('PYTHONPATH','PYTHONHOME','LD_LIBRARY_PATH')}
    env.update({'PYTHONPATH':'','PYTHONNOUSERSITE':'1','PIP_NO_INPUT':'1','PIP_DISABLE_PIP_VERSION_CHECK':'1'})
    if not PYTHON.is_file():
        if args.verify: print('Model worker missing',file=sys.stderr);return 2
        subprocess.run([str(SEED),'-m','venv',str(PYTHON.parents[1])],env=env,check=True)
    if not args.verify:
        command=[str(PYTHON),'-m','pip','install','-r',str(LOCK)]
        if args.offline: command+=['--no-index','--find-links',str(ROOT/'.tools/model-wheels')]
        subprocess.run(command,env=env,cwd=ROOT,check=True)
    check=subprocess.run([str(PYTHON),'-m','pip','check'],env=env,cwd=ROOT,capture_output=True,text=True)
    if check.returncode:
        print(check.stdout+check.stderr,file=sys.stderr);return 2
    freeze=subprocess.run([str(PYTHON),'-m','pip','freeze'],env=env,cwd=ROOT,capture_output=True,text=True,check=True)
    installed={line.lower() for line in freeze.stdout.splitlines() if line and not line.startswith('#')}
    expected={line.lower() for line in LOCK.read_text().splitlines() if line and not line.startswith('#')}
    if installed!=expected:
        print(json.dumps({'status':'failed','missing':sorted(expected-installed),'extra':sorted(installed-expected)}),file=sys.stderr)
        return 2
    version=subprocess.run([str(PYTHON),'-c','import build123d;print(build123d.__version__)'],env=env,cwd=ROOT,capture_output=True,text=True)
    if version.returncode or version.stdout.strip()!='0.13.0':
        print(version.stderr or version.stdout,file=sys.stderr);return 2
    print(json.dumps({'status':'ready','build123d':'0.13.0','locked_packages':len(expected)}))
    return 0

if __name__=='__main__':
    raise SystemExit(main())
