"""Real Electron STEP-to-validated-URDF-ZIP export smoke."""
import json
import tempfile
from accept_phase import run_stage, ROOT


def main():
    output = ROOT/'artifacts/C03/desktop'
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='c03-desktop-', dir=ROOT/'.tools') as home:
        env = {'PATH': str(ROOT/'.tools/node/bin')+':/usr/bin:/bin', 'HOME': home,
               'LANG': 'C.UTF-8', 'URDFTOOLS_SMOKE_ARTIFACT_DIR': str(output),
               'URDFTOOLS_CAD_WIZARD_SMOKE': str(ROOT/'tests/fixtures/C00/two_part_mm.step'),
               'URDFTOOLS_CAD_EXPORT_SMOKE': str(output/'robot.zip'),
               'URDFTOOLS_CAD_DRAFT_SMOKE': '1', 'URDFTOOLS_FONT_SMOKE': '1'}
        command = [str(ROOT/'apps/desktop/node_modules/electron/dist/electron'),
                   str(ROOT/'apps/desktop'), '--smoke', '--ozone-platform=headless',
                   '--enable-unsafe-swiftshader', '--use-gl=angle', '--use-angle=swiftshader']
        code, log = run_stage(command, env=env, timeout=180)
        restore_env = dict(env)
        restore_env.pop('URDFTOOLS_CAD_WIZARD_SMOKE')
        restore_env.pop('URDFTOOLS_CAD_EXPORT_SMOKE')
        restore_env.pop('URDFTOOLS_CAD_DRAFT_SMOKE')
        restore_env.pop('URDFTOOLS_FONT_SMOKE')
        restore_env['URDFTOOLS_CAD_DRAFT_RESTORE_SMOKE'] = '1'
        restore_env['URDFTOOLS_FONT_RESTORE_SMOKE'] = '1'
        restore_code, restore_log = run_stage(command, env=restore_env, timeout=150)
    log += '\n' + restore_log
    (output/'electron.log').write_text(log)
    events = []
    for line in log.splitlines():
        try: events.append(json.loads(line))
        except ValueError: pass
    event = next((item for item in events if item.get('event') == 'desktop_cad_export_smoke'), None)
    draft = next((item for item in events if item.get('event') == 'desktop_cad_draft_smoke'), None)
    restored = next((item for item in events if item.get('event') == 'desktop_cad_draft_restore_smoke'), None)
    fonts = next((item for item in events if item.get('event') == 'desktop_font_scale_smoke'), None)
    passed = (code == 0 and restore_code == 0 and event is not None and event.get('zipBytes', 0) > 1000 and
              draft is not None and draft.get('saved') and restored is not None and restored.get('cachedSource') and
              fonts is not None and (output/'cad-export.png').is_file() and (output/'cad-font-scale.png').is_file())
    (output/'report.json').write_text(json.dumps({'status': 'passed' if passed else 'failed',
        'exit_code': code, 'restore_exit_code': restore_code, 'command': command,
        'export_event': event, 'draft_event': draft, 'restore_event': restored, 'font_event': fonts}, ensure_ascii=False, indent=2)+'\n')
    print(log[-9000:])
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
