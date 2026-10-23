#!/usr/bin/env python3
"""Actual Electron/Three.js A1 and Go2 desktop viewer gate for pinned vendor source assets."""
import json
import os
from pathlib import Path
import tempfile

from accept_phase import run_stage,ROOT


def event_from(log):
    for line in log.splitlines():
        try: msg=json.loads(line)
        except ValueError: continue
        if msg.get("event")=="desktop_viewer_s06_smoke":
            return msg
    return None


def main():
    dest=ROOT/"artifacts/R01/desktop"
    dest.mkdir(parents=True,exist_ok=True)
    env_base={"PATH":str(ROOT/".tools/node/bin")+":/usr/bin:/bin","LANG":"C.UTF-8"}
    cases=[
        ("a1",ROOT/"tests/fixtures/S06/a1_description",23,22),
        ("go2",ROOT/"tests/fixtures/S06/reference_models/go2_description",42,41),
    ]
    failed=[]
    for label,fixture,links,joints in cases:
        with tempfile.TemporaryDirectory(prefix="r01-"+label+"-",dir=ROOT/".tools") as home:
            env=dict(env_base,HOME=home,URDFTOOLS_SMOKE_ARTIFACT_DIR=str(dest),
                     URDFTOOLS_VIEWER_SMOKE=str(fixture),URDFTOOLS_VIEWER_S06_SMOKE=label)
            cmd=[str(ROOT/"apps/desktop/node_modules/electron/dist/electron"),
                 str(ROOT/"apps/desktop"),"--smoke","--ozone-platform=headless",
                 "--enable-unsafe-swiftshader","--use-gl=angle","--use-angle=swiftshader"]
            code,log=run_stage(cmd,env=env,timeout=150)
        (dest/(label+"-viewer.log")).write_text(log)
        e=event_from(log)
        passed=(code==0 and e is not None and e.get("model")==label
                and e.get("linkCount")==links and e.get("jointCount")==joints
                and e.get("assetsLoaded") is True and e.get("meshCount",0)>=5
                and e.get("jointPoseChanged") is True
                and e.get("collisionToggleVerified") is True
                and e.get("physicsUnchanged") is True
                and e.get("screenshotReady") is True
                and (dest/(label+"-viewer.png")).is_file()
                and (dest/(label+"-viewer-export.png")).is_file())
        report={"status":"passed" if passed else "failed","model":label,
                "code":code,"result":e}
        (dest/(label+"-report.json")).write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
        print(json.dumps({"model":label,"status":report["status"],"links":links,
                          "joints":joints,"renderer_event":e is not None}))
        if not passed:
            failed.append(label)
    return int(bool(failed))


if __name__=="__main__":
    raise SystemExit(main())
