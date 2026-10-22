# Vendored step2urdf CAD adapter

- Upstream: https://github.com/edsamsankey/step2urdf
- Pinned commit: `3845072d29c0cdbd12a9b3c65808440163e32130` (2026-09-20)
- Upstream package version: `0.1.0` from its `pyproject.toml`
- Vendored file: upstream `cad.py` copied byte-for-byte to `python/urdftools/cad/step2urdf_adapter.py`
- Source SHA-256: `1be7423e3de2e7e14ba7d1fc0849d579c610cad91e493397f5c69fe24ae080cc`
- License: upstream MIT text retained verbatim in this directory. Its copyright line still contains the upstream placeholder `YOUR NAME HERE`; this provenance concern is recorded for the later Q01 third-party license audit, not silently rewritten.
- Runtime dependency: `cadquery-ocp-novtk==8.0.1.1.0` with NumPy `2.3.4`; the CAD worker is isolated from the application's base `.venv`.
- Unit contract from upstream adapter: returned geometry coordinates are millimetres. C00 adds an independent hierarchy/unit/provenance reader; do not treat the adapter's flattened part list as an assembly hierarchy.
