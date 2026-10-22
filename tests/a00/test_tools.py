import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'python'))
from urdftools.agent.tools import AgentToolError,preview_recipe,apply_preview,tool_catalog
from urdftools.modeling.core import apply_project


def recipe(width=20):
    return {'schema_version':1,'parts':[{'name':'Body','material':'user declared',
      'density_kg_m3':2700,'profile':{'kind':'rectangle','width_mm':width,'height_mm':10},
      'operation':{'kind':'extrude','distance_mm':5},'placement_mm':[0,0,0]}]}


def suggestion(revision=1,width=30):
    return {'schema_version':1,'action':'replace_recipe','expected_revision':revision,
      'recipe':recipe(width),'rationale':'Make the main body wider for review.'}


class AgentToolTests(unittest.TestCase):
    def test_isolated_preview_and_explicit_apply(self):
        with tempfile.TemporaryDirectory() as temporary:
            project=Path(temporary)/'project'
            initial=apply_project(project,recipe(),expected_revision=0)
            pointer=(project/'current.json').read_bytes()
            proposal=preview_recipe(project,suggestion())
            self.assertEqual(proposal['status'],'preview_only')
            self.assertEqual(proposal['diff']['changed_parts'],['Body'])
            self.assertGreater(proposal['report']['parts'][0]['mass_kg'],initial['report']['parts'][0]['mass_kg'])
            self.assertEqual((project/'current.json').read_bytes(),pointer)
            self.assertTrue((Path(proposal['proposal_path'])/'Body.step').is_file())
            with self.assertRaisesRegex(AgentToolError,'human confirmation'):
                apply_preview(project,proposal['proposal_id'],human_confirmed=False)
            self.assertEqual((project/'current.json').read_bytes(),pointer)
            applied=apply_preview(project,proposal['proposal_id'],human_confirmed=True)
            self.assertEqual(applied['revision'],2)
            self.assertGreater(applied['report']['parts'][0]['mass_kg'],initial['report']['parts'][0]['mass_kg'])
            self.assertTrue((Path(initial['package'])/'Body.step').is_file())
            with self.assertRaisesRegex(AgentToolError,'advanced since preview'):
                apply_preview(project,proposal['proposal_id'],human_confirmed=True)

    def test_invalid_and_privileged_fields_rejected_without_mutation(self):
        with tempfile.TemporaryDirectory() as temporary:
            project=Path(temporary)/'project';apply_project(project,recipe(),expected_revision=0)
            pointer=(project/'current.json').read_bytes()
            bad=copy.deepcopy(suggestion());bad['shell']='rm -rf /'
            with self.assertRaisesRegex(AgentToolError,'declared schema'):
                preview_recipe(project,bad)
            bad=copy.deepcopy(suggestion());bad['recipe']['parts'][0]['network_url']='https://example.com'
            with self.assertRaisesRegex(AgentToolError,'undeclared fields'):
                preview_recipe(project,bad)
            bad=copy.deepcopy(suggestion());bad['recipe']['parts'][0]['modifiers']=[{'kind':'execute_python','script':'touch /tmp/pwned'}]
            with self.assertRaisesRegex(AgentToolError,'undeclared fields'):
                preview_recipe(project,bad)
            bad=copy.deepcopy(suggestion());bad['recipe']['parts'][0]['profile']['width_mm']=-1
            with self.assertRaisesRegex(AgentToolError,'CAD preview rejected'):
                preview_recipe(project,bad)
            self.assertEqual((project/'current.json').read_bytes(),pointer)
            self.assertEqual(len(list((project/'proposals').iterdir())),0)

    def test_tampered_proposal_and_catalog(self):
        with tempfile.TemporaryDirectory() as temporary:
            project=Path(temporary)/'project';apply_project(project,recipe(),expected_revision=0)
            proposal=preview_recipe(project,suggestion())
            self.assertEqual([item['name'] for item in tool_catalog()],['preview_recipe'])
            path=Path(proposal['proposal_path'])/'recipe.json'
            path.write_text(json.dumps(recipe(40)))
            with self.assertRaisesRegex(AgentToolError,'changed after preview'):
                apply_preview(project,proposal['proposal_id'],human_confirmed=True)
            self.assertEqual(json.loads((project/'current.json').read_text())['revision'],1)

if __name__=='__main__':unittest.main()
