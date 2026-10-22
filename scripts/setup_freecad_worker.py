#!/usr/bin/env python3
"""Verify and extract the official FreeCAD AppImage into ignored local .tools."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from freecad_bridge import APPIMAGE, APPIMAGE_SHA256, APPDIR, ROOT, sha


def main():
    if not APPIMAGE.is_file() or sha(APPIMAGE)!=APPIMAGE_SHA256:
        print('FreeCAD AppImage missing or hash mismatch',file=sys.stderr)
        return 2
    if (APPDIR/'AppRun').is_file():
        print(json.dumps({'status':'ready','appdir':str(APPDIR),'appimage_sha256':APPIMAGE_SHA256}))
        return 0
    APPIMAGE.chmod(APPIMAGE.stat().st_mode | 0o100)
    with tempfile.TemporaryDirectory(prefix='freecad-extract-',dir=ROOT/'.tools') as folder:
        run=subprocess.run([str(APPIMAGE),'--appimage-extract'],cwd=folder,capture_output=True,text=True,timeout=300)
        extracted=Path(folder)/'squashfs-root'
        if run.returncode or not (extracted/'AppRun').is_file():
            print(f'FreeCAD extraction failed: {run.stderr[-1000:]}',file=sys.stderr)
            return 2
        extracted.rename(APPDIR)
    print(json.dumps({'status':'ready','appdir':str(APPDIR),'appimage_sha256':APPIMAGE_SHA256}))
    return 0

if __name__=='__main__':
    raise SystemExit(main())
