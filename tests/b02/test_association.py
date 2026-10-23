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
from urdftools.results.jobs import ImportFailure, ImportQueue


class RealUrdfAssociationTests(unittest.TestCase):
    def test_a1_go2_and_user_model_require_exact_hash(self):
        sources = [
            ("a1", ROOT / "tests/fixtures/S06/a1_description/a1.urdf", "public_import"),
            ("go2", ROOT / "tests/fixtures/S06/reference_models/go2_description/urdf/go2_description.urdf", "public_import"),
            ("user", ROOT / "tests/fixtures/E00/quadruped_valid.urdf", "user_upload"),
        ]
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            with ModelRegistry(base / "models") as registry, ImportQueue(base / "results") as queue:
                catalog = ResultCatalog(queue)
                linked = []
                for name, urdf, origin in sources:
                    model = registry.import_file(urdf, name=name, version="pinned-1", category="quadruped",
                                                 origin=origin, license_id="BSD-3-Clause" if origin == "public_import" else None)
                    source = base / name
                    source.mkdir()
                    info = {"schema_version": 1, "run_id": f"synthetic-{name}", "robot_hash": model["sha256"],
                            "robot_category": "quadruped", "origin": "synthetic_fixture", "algorithm": "external-example",
                            "protocol": "local-smoke", "license": "CC0-1.0",
                            "metrics": [{"path": "metrics.csv", "format": "csv", "units": {"success": "ratio"}}]}
                    (source / "experiment.json").write_text(json.dumps(info))
                    (source / "metrics.csv").write_text("metric,step,value,wall_time\nsuccess,1,0.5,10\n")
                    files = [{"path": p.name, "size": p.stat().st_size, "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
                             for p in sorted(source.iterdir())]
                    job = queue.enqueue(source, {"bundle_id": f"synthetic-{name}", "robot_hash": model["sha256"], "files": files})
                    self.assertEqual(queue.claim(name), job)
                    while queue.step(job, name) != "completed": pass
                    catalog.import_experiment(job)
                    association = catalog.link_model(f"synthetic-{name}", model["id"], registry)
                    self.assertFalse(association["reference_performance"])
                    self.assertEqual(association["model_sha"], model["sha256"])
                    linked.append(association)
                with self.assertRaises(ImportFailure):
                    catalog.link_model("synthetic-a1", linked[1]["model_id"], registry)
                self.assertEqual(queue.db.execute("SELECT count(*) FROM result_models").fetchone()[0], 3)


if __name__ == "__main__":
    unittest.main()
