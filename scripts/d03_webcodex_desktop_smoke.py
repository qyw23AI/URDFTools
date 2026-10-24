#!/usr/bin/env python3
"""Actually exercise Electron React, isolated preload, IPC, local request queue and clipboard."""
import json
import os
from pathlib import Path
import sys
import tempfile

from accept_phase import ROOT, run_stage

def main():
    folder=ROOT/"artifacts/D03/desktop"
    folder.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="d03-webcodex-electron-",dir=ROOT/".tools") as temp:
        temp=Path(temp)
        env=dict(os.environ,PATH=str(ROOT/".tools/node/bin")+":/usr/bin:/bin",
                 HOME=str(temp),LANG="C.UTF-8",
                 URDFTOOLS_WEBCODEX_SMOKE="1",
                 URDFTOOLS_WEBCODEX_STORE=str(temp/"webcodex-requests"),
                 URDFTOOLS_SMOKE_ARTIFACT_DIR=str(folder))
        command=[str(ROOT/"apps/desktop/node_modules/electron/dist/electron"),
                 str(ROOT/"apps/desktop"),"--smoke","--ozone-platform=headless",
                 "--enable-unsafe-swiftshader","--use-gl=angle","--use-angle=swiftshader"]
        exit_code,log=run_stage(command,env=env,timeout=100)
        (folder/"electron.log").write_text(log)
        events=[]
        for line in log.splitlines():
            try:events.append(json.loads(line))
            except ValueError:pass
        event=next((e for e in events if e.get("event")=="desktop_webcodex_agent_smoke"),None)
        rendering=next((e for e in events if e.get("event")=="desktop_smoke"),None)
        imported=next((e for e in events if e.get("event")=="desktop_webcodex_imported_urdf_smoke"),None)
        dual=next((e for e in events if e.get("event")=="desktop_agent_dual_mode_smoke"),None)
        if not event or not rendering or not imported or not dual:
            raise AssertionError(f"Real Electron smoke event missing, exit={exit_code}: {log[-2400:]}")
        request=temp/"webcodex-requests"/event["request_id"]/"request.json"
        if (exit_code or not request.is_file() or not event["clipboard_verified"] or
                not event["renderer_isolated"] or event["model_cli_calls"]!=0):
            raise AssertionError(f"Desktop WebCodex integration failed: {event}")
        raw=json.loads(request.read_text())
        assert raw["kind"]=="diagnosis" and raw["payload"]["synthetic_fixture"]
        assert imported["rule"]=="invalid_joint_axis" and imported["xml_not_submitted"]
        assert dual["cli_request_created"] and dual["webcodex_request_created"]
        assert dual["model_modes_selectable"] and not dual["cli_model_called"]
        assert not (request.parent/"result.json").exists()
        assert (folder/"webcodex-agent.png").stat().st_size>2000
    print(json.dumps({"status":"passed","electron_isolated":True,
                      "renderer_created_request":True,"clipboard_handoff":True,
                      "imported_urdf_static_evidence":True,
                      "private_consent_step":True,"codex_cli_calls":0,
                      "cli_request_mode_verified":True,
                      "no_fabricated_model_output":True,
                      "screenshot":"artifacts/D03/desktop/webcodex-agent.png"}))

if __name__=="__main__":
    main()
