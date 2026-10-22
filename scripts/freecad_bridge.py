#!/usr/bin/env python3
"""Run pinned local FreeCADCmd to export an FCStd document to STEP safely."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
APPIMAGE=ROOT/'.tools/FreeCAD_1.1.4-Linux-x86_64-py311.AppImage'
APPIMAGE_SHA256='f6dc6ba676e5ac96a565ebc8d657232f94c6158e85b4352141bd1a46f6b43434'
APPDIR=ROOT/'.tools/freecad-appdir'
WORKER=ROOT/'scripts/freecad_worker.py'


def sha(path):
    digest=hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda:source.read(1024*1024),b''):
            digest.update(block)
    return digest.hexdigest()


def invoke(action, source, output):
    if not APPIMAGE.is_file() or sha(APPIMAGE)!=APPIMAGE_SHA256:
        raise ValueError('Official FreeCAD 1.1.4 AppImage is missing or hash mismatch')
    if not (APPDIR/'AppRun').is_file():
        raise ValueError('FreeCAD AppImage is not extracted; run scripts/setup_freecad_worker.py')
    if output.exists() or os.path.lexists(output):
        raise ValueError('Output already exists; refusing overwrite')
    if action=='export' and (source.suffix.lower()!='.fcstd' or not source.is_file()):
        raise ValueError('Existing .FCStd source required')
    output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='freecad-bridge-') as folder:
        work=Path(folder)
        request=work/'request.json';result=work/'result.json'
        temporary=work/('output.FCStd' if action=='fixture' else 'output.step')
        request.write_text(json.dumps({'action':action,'source':str(source),'output':str(temporary)}))
        env={key:value for key,value in os.environ.items() if key not in ('PYTHONPATH','PYTHONHOME','LD_LIBRARY_PATH')}
        env.update({'URDFTOOLS_FREECAD_REQUEST':str(request),'URDFTOOLS_FREECAD_RESULT':str(result),
                    'HOME':str(work),'QT_QPA_PLATFORM':'offscreen'})
        command=[str(APPDIR/'AppRun'),'--console',str(WORKER)]
        process=subprocess.run(command,env=env,cwd=work,capture_output=True,text=True,timeout=180)
        if not result.is_file():
            raise RuntimeError(f'FreeCAD did not produce result; exit={process.returncode}; stderr={process.stderr[-1000:]}')
        report=json.loads(result.read_text())
        if report['status']=='failed' or not temporary.is_file():
            raise RuntimeError(f'FreeCAD export failed: {report}; stderr={process.stderr[-1000:]}')
        if action=='export':
            sys.path.insert(0,str(ROOT/'python'))
            from urdftools.cad.step_reader import inspect_step
            inspection=inspect_step(temporary)
            if len(inspection['parts']) < 1:
                raise RuntimeError('Exported STEP has no inspected part')
            report['reimport']={'part_count':len(inspection['parts']),
                                'source_length_unit':inspection['units']['source_length_unit'],
                                'adapter_status':inspection['adapter']['status']}
            if report['reimport']['source_length_unit']!='mm':
                raise RuntimeError('STEP units not normalized to mm')
        try:
            os.link(temporary,output)
        except FileExistsError as exc:
            raise ValueError('Output appeared during conversion; no overwrite') from exc
        report['output']=str(output)
        report['output_sha256']=sha(output)
        return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source',type=Path,nargs='?')
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--make-fixture',action='store_true',help='create an original two-part FCStd fixture')
    args=parser.parse_args()
    try:
        if not args.make_fixture and args.source is None:
            parser.error('source FCStd is required')
        result=invoke('fixture' if args.make_fixture else 'export',args.source,args.output)
        print(json.dumps(result,ensure_ascii=False))
        return 0
    except (OSError,ValueError,RuntimeError,subprocess.TimeoutExpired) as exc:
        print(json.dumps({'status':'failed','reason':str(exc)},ensure_ascii=False),file=sys.stderr)
        return 2

if __name__=='__main__':
    raise SystemExit(main())
