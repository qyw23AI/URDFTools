# S06 real reference-model fixtures

S06 desktop end-to-end uses `reference_models/` (Go2 folder and G1 29-DoF ZIP); `reference_models.json` records upstream model IDs, source commit, content hashes, copyright/license and wrapper differences. The extra `a1_description/` and `g1_description/` directories below are optional standalone fixtures and **not** what the S06 desktop smoke loads. None are installed by the app or claimed to be physically validated RL reference configurations.


These test assets are sourced from Unitree Robotics’ public unitreerobotics/unitree_ros repository at commit 5994d4faef0a9cadd3287f8de0199a67eeb2a259. The repository LICENSE is BSD 3-Clause and is copied into each model folder. Source: https://github.com/unitreerobotics/unitree_ros

- a1_description/: upstream A1 URDF, package metadata and mesh assets. Upstream package.xml has <license>TODO</license>; the repository-level BSD-3-Clause LICENSE is retained and recorded, but that package metadata defect is not silently rewritten.
- g1_description/: upstream G1 29-DoF URDF and only the mesh files it references. A minimal package.xml was added as test packaging metadata so the importer can recognize the package; the URDF and referenced meshes are copied byte-for-byte.
- manifest.json: pinned commit, license and source URDF hashes, and link/joint/mesh counts.

The models are for import/viewer regression only; no claim is made that their vendor parameters are suitable for any particular RL task.
