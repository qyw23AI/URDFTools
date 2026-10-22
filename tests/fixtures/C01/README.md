# C01 mass-property fixtures

All STEP files are self-authored analytic B-rep test inputs, generated with the isolated OCP worker by `scripts/generate_c01_fixtures.py`. They are not robot vendor assets.

- `box_mm.step`: one 20×10×5 mm box; used to compare volume, mass and diagonal inertia against the closed-form cuboid formula.
- `offset_double_sphere_mm.step`: two radius-10 mm spheres at x=0 and x=50 mm; used to test mass-weighted center of mass and the parallel-axis theorem.
- `rotated_box_mm.step`: the same box rotated 45° around Z and translated (100, -20, 30) mm; used to test non-diagonal inertia and the rotation/translation matrix.
- `manifest.json`: expected geometry, OCP version, input hashes and byte sizes.

All fixture lengths are declared in millimetres. Tests apply explicit densities in kg/m³. Missing density must yield unknown mass/inertia, never a zero-mass assertion.
