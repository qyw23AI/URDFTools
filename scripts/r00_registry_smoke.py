#!/usr/bin/env python3
"""Actual R00 CLI workflow with persistent two-version store, no internet required."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
FIXTURE=ROOT/"tests/fixtures/E00"
with tempfile.TemporaryDirectory(prefix="urdftools-r00-") as tmp:
    store=Path(tmp)/"catalog"
    models=[]
    for index,name in enumerate(("quadruped_valid","quadruped_axis_context_mismatch"),start=1):
        path=FIXTURE/(name+".urdf")
        call=[str(ROOT/".venv/bin/python"),"scripts/r00_registry_cli.py","--store",str(store),
              "import","--urdf",str(path),"--name","test-quadruped",
              "--version",str(index),"--category","quadruped",
              "--origin","synthetic_fixture","--license-id","CC0-1.0",
              "--expected-sha256",hashlib.sha256(path.read_bytes()).hexdigest()]
        result=subprocess.run(call,text=True,capture_output=True,cwd=ROOT,timeout=20)
        assert result.returncode==0,result.stderr
        models.append(json.loads(result.stdout)["model"])
    results=subprocess.run([str(ROOT/".venv/bin/python"),"scripts/r00_registry_cli.py",
                           "--store",str(store),"list"],cwd=ROOT,text=True,
                           capture_output=True,timeout=20)
    assert results.returncode==0,results.stderr
    listed=json.loads(results.stdout)["models"]
    assert len(listed)==2
    assert len({m["id"] for m in listed})==2
    assert all(not m["bundling_permitted"] and not m["reference_performance"] for m in listed)
    print(json.dumps({"status":"passed","models":len(listed),"distinct_versions":2,
                      "immutable_assets":all((store/"blobs"/m["sha256"][:2]/m["sha256"]).is_file()
                                             for m in listed),
                      "license_auto_bundling":False,"reference_performance":False}))
