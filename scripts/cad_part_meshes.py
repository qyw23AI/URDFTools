#!/usr/bin/env python3
"""Tessellate each placed STEP part for the interactive CAD selection stage."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'python'))
from urdftools.cad.exporter import _binary_stl
from urdftools.cad.step2urdf_adapter import load_step
import numpy as np


def main() -> None:
    source, destination = Path(sys.argv[1]), Path(sys.argv[2])
    destination.mkdir(parents=True, exist_ok=True)
    manifest = []
    for index, part in enumerate(load_step(str(source))):
        vertices, faces = part.mesh()
        filename = f'{index:04d}.stl'
        data = _binary_stl(vertices, faces, np.zeros(3))
        (destination / filename).write_bytes(data)
        manifest.append({'name': part.name, 'file': filename, 'size': len(data),
                         'color': list(part.color) if part.color is not None else None})
    print(json.dumps({'parts': manifest}, ensure_ascii=False))


if __name__ == '__main__':
    main()
