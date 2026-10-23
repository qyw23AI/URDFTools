"""K00 numerical smoke for installed built-in skill manifests."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'python'))
import json
from urdftools.evaluation.skills import discover_skills, run_skill

root = Path(__file__).resolve().parents[1]
catalog = discover_skills(root / "skills")
inputs = {
    "inertia_basics": {"mass_matrix": {"tensor_kg_m2": [[2,0,0],[0,3,0],[0,0,4]]}},
    "frame_basics": {"frame_rotation": {"rotation": [[0,-1,0],[1,0,0],[0,0,1]]}},
    "contact_basics": {"friction_cone": {"normal_force_n": 10, "tangential_force_n": 3, "friction_coefficient": .5}},
    "statistics_basics": {"sample_summary": {"samples": [2,3,4,5]}}
}
reports = {name: run_skill(catalog[name], data) for name, data in inputs.items()}
assert len(reports) == 4 and all(r["passed"] for r in reports.values())
print(json.dumps({"fixture": "original synthetic numerical inputs", "results": reports}, indent=2))
