#!/usr/bin/env python3
"""Build a freshly exported ROS 2 package with the real colcon/ament toolchain."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'python'))
from urdftools.cad.exporter import write_package_zip
from urdftools.cad.wizard import default_configuration, inspect_conversion_draft
from urdftools.importers import ImportService


def main():
    source = ROOT/'tests/fixtures/C00/two_part_mm.step'
    draft = inspect_conversion_draft(source)
    config = default_configuration(draft)
    config['joints'][0].update(type='revolute', axis=[1, 0, 0], limits=[-1.2, 1.2], effort=10, velocity=2, confirmed=True)
    densities = {part['name']: 2700 for part in draft['parts']}
    colcon = shutil.which('colcon')
    if not colcon:
        raise RuntimeError('colcon is unavailable; ROS package gate cannot pass')
    with tempfile.TemporaryDirectory(prefix='c03-colcon-') as folder:
        work = Path(folder)
        archive = work/'robot.zip'
        write_package_zip(source, config, densities, archive)
        with zipfile.ZipFile(archive) as package:
            package.extractall(work/'src')
        command = [colcon, '--log-base', str(work/'log'), 'build', '--packages-select', 'urdftools_robot',
                   '--base-paths', str(work/'src'), '--build-base', str(work/'build'),
                   '--install-base', str(work/'install')]
        result = subprocess.run(command, cwd=work, capture_output=True, text=True, timeout=180)
        print(result.stdout)
        print(result.stderr, file=sys.stderr)
        if result.returncode:
            return result.returncode
        installed = work/'install/urdftools_robot/share/urdftools_robot'
        imported = ImportService(work/'imports').ingest(installed)
        if imported['status'] != 'ready' or len(imported['models'][0]['resources']) != 2:
            raise AssertionError(f'Installed ROS package failed URDF reimport: {imported}')
        if not all((installed/'meshes'/f'{part}.stl').is_file() for part in densities):
            raise AssertionError('Installed ROS package lost a mesh')
        print(json.dumps({'status':'passed','package':'urdftools_robot','installed_meshes':2,
                          'installed_import_status':imported['status']}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
