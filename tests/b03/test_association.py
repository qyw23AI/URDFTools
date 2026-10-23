import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))
from urdftools.reference.registry import ModelRegistry
from urdftools.results.catalog import ResultCatalog
from urdftools.results.jobs import ImportQueue, ImportFailure


class HumanoidAssociationTests(unittest.TestCase):
    def test_g1_h1_and_user_humanoid(self):
        files = [
            ("g1", ROOT / "tests/fixtures/S06/reference_models/g1_description/g1_29dof.urdf", "public_import"),
            ("h1", ROOT / "tests/fixtures/R02/h1_description/urdf/h1.urdf", "public_import"),
            ("user", ROOT / "tests/fixtures/E00/humanoid_valid.urdf", "user_upload"),
        ]
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            with ModelRegistry(base / "models") as registry, ImportQueue(base / "results") as queue:
                catalog = ResultCatalog(queue)
                models = []
                for name, urdf, origin in files:
                    model = registry.import_file(urdf, name=name, version="fixed-1", category="humanoid",
                                                 origin=origin, license_id="BSD-3-Clause" if origin == "public_import" else None)
                    models.append(model)
                    source = base / name
                    source.mkdir()
                    info = {"schema_version": 1, "run_id": f"synthetic-{name}", "robot_hash": model["sha256"],
                            "robot_category": "humanoid", "origin": "synthetic_fixture", "algorithm": "external-example",
                            "protocol": "local-smoke", "metrics": [{"path": "metrics.csv", "format": "csv", "units": {"success": "ratio"}}]}
                    (source / "experiment.json").write_text(json.dumps(info))
                    (source / "metrics.csv").write_text("metric,step,value,wall_time\nsuccess,1,0.5,10\n")
                    inventory = [{"path": p.name, "size": p.stat().st_size, "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
                                 for p in sorted(source.iterdir())]
                    job = queue.enqueue(source, {"bundle_id": name, "robot_hash": model["sha256"], "files": inventory})
                    self.assertEqual(queue.claim(name), job)
                    while queue.step(job, name) != "completed": pass
                    catalog.import_experiment(job)
                    self.assertFalse(catalog.link_model(f"synthetic-{name}", model["id"], registry)["reference_performance"])
                with self.assertRaises(ImportFailure):
                    catalog.link_model("synthetic-g1", models[1]["id"], registry)
                self.assertEqual(queue.db.execute("SELECT count(*) FROM result_models").fetchone()[0], 3)


if __name__ == "__main__":
    unittest.main()
