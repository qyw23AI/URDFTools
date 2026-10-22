#!/usr/bin/env python3
"""Create/verify isolated MuJoCo worker from the hash-pinned simulation lock."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT/'.tools/python/bin/python'
ENV = ROOT/'.tools/sim-venv'
PYTHON = ENV/'bin/python'
WHEELS = ROOT/'.tools/sim-wheels'
LOCK = ROOT/'sim-requirements.lock'


def call(argv, env):
    print('+', ' '.join(map(str, argv)), flush=True)
    subprocess.run(list(map(str, argv)), cwd=ROOT, env=env, check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--offline', action='store_true')
    args = parser.parse_args()
    if not SEED.is_file() or not LOCK.is_file():
        print('Pinned Python runtime or simulation lock missing', file=sys.stderr)
        return 2
    home = ROOT/'.tools/sim-home'
    home.mkdir(parents=True, exist_ok=True)
    env = {'PATH': str(ROOT/'.tools/python/bin')+':/usr/bin:/bin', 'HOME':str(home),
           'LANG':'C.UTF-8', 'PYTHONNOUSERSITE':'1', 'PIP_CONFIG_FILE':os.devnull,
           'PIP_NO_INPUT':'1','PIP_DISABLE_PIP_VERSION_CHECK':'1'}
    if not PYTHON.is_file():
        call([SEED,'-m','venv',ENV],env)
    WHEELS.mkdir(parents=True,exist_ok=True)
    pip = [PYTHON,'-m','pip']
    if not args.offline:
        call(pip+['download','--require-hashes','--only-binary=:all:','--dest',WHEELS,'-r',LOCK],env)
    elif not list(WHEELS.glob('*.whl')):
        print('Offline simulation wheelhouse is empty',file=sys.stderr)
        return 2
    call(pip+['install','--require-hashes','--only-binary=:all:','--no-index','--find-links',WHEELS,'-r',LOCK],env)
    call(pip+['check'],env)
    probe = subprocess.run([str(PYTHON),'-c',
        "import mujoco,numpy,json;print(json.dumps({'mujoco':mujoco.__version__,'numpy':numpy.__version__}))"],
        cwd=ROOT,env=env,text=True,capture_output=True)
    if probe.returncode:
        print(probe.stderr,file=sys.stderr)
        return 2
    report=json.loads(probe.stdout.strip())
    print(json.dumps(report))
    return 0 if report=={'mujoco':'3.16.0','numpy':'2.5.4'} else 2


if __name__=='__main__':
    raise SystemExit(main())
