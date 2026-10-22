import copy
import hashlib
import json
from pathlib import Path
import sys
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'python'))
from urdftools.cad.wizard import (WizardError, canonical_configuration,
    default_configuration, inspect_conversion_draft, preview_urdf,
    validate_configuration)


class ConversionWizardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.draft = inspect_conversion_draft(ROOT / 'tests/fixtures/C00/two_part_mm.step')

    def configured(self):
        config = default_configuration(self.draft)
        joint = config['joints'][0]
        joint.update(type='revolute', axis=[0.0, 0.0, 1.0],
                     limits=[-1.2, 1.2], confirmed=True)
        return config

    def test_real_step_produces_unconfirmed_candidates(self):
        draft = self.draft
        self.assertEqual([p['name'] for p in draft['parts']], ['BasePart', 'OffsetPart'])
        self.assertEqual(draft['source_sha256'], hashlib.sha256((ROOT / 'tests/fixtures/C00/two_part_mm.step').read_bytes()).hexdigest())
        config = default_configuration(draft)
        self.assertEqual(validate_configuration(draft, config)['unconfirmed_joints'], ['OffsetPart_joint'])
        with self.assertRaisesRegex(WizardError, 'human confirmation'):
            preview_urdf(draft, config)

    def test_reuse_is_deterministic_and_joint_axis_changes_preview(self):
        first = self.configured()
        reused = json.loads(canonical_configuration(first))
        self.assertEqual(canonical_configuration(first), canonical_configuration(reused))
        a = preview_urdf(self.draft, first)
        b = preview_urdf(self.draft, reused)
        self.assertEqual(a, b)
        robot = ET.fromstring(a)
        self.assertEqual(len(robot.findall('link')), 2)
        joint = robot.find('joint')
        self.assertEqual(joint.get('type'), 'revolute')
        self.assertEqual(joint.find('axis').get('xyz'), '0 0 1')
        self.assertEqual(joint.find('limit').get('lower'), '-1.2')
        self.assertEqual(joint.find('limit').get('upper'), '1.2')
        self.assertAlmostEqual(float(joint.find('origin').get('xyz').split()[0]), 0.055)
        altered = copy.deepcopy(first)
        altered['joints'][0]['axis'] = [1.0, 0.0, 0.0]
        changed = ET.fromstring(preview_urdf(self.draft, altered))
        self.assertEqual(changed.find('joint/axis').get('xyz'), '1 0 0')
        self.assertNotEqual(a, preview_urdf(self.draft, altered))

    def test_two_cad_parts_can_be_grouped_into_one_link(self):
        config = {'schema_version': 1, 'source_sha256': self.draft['source_sha256'],
                  'root': 'body', 'links': [{'name': 'body', 'parts': ['BasePart', 'OffsetPart']}],
                  'joints': []}
        self.assertEqual(validate_configuration(self.draft, config)['joint_count'], 0)
        robot = ET.fromstring(preview_urdf(self.draft, config))
        self.assertEqual(len(robot.findall('link')), 1)
        self.assertEqual(len(robot.findall('link/visual')), 2)

    def test_rejects_stale_source_duplicate_part_and_cycle(self):
        config = self.configured()
        changed = copy.deepcopy(config)
        changed['source_sha256'] = '0' * 64
        with self.assertRaisesRegex(WizardError, 'does not match'):
            validate_configuration(self.draft, changed)
        changed = copy.deepcopy(config)
        changed['links'][1]['parts'] = ['BasePart']
        with self.assertRaisesRegex(WizardError, 'exactly one'):
            validate_configuration(self.draft, changed)
        changed = copy.deepcopy(config)
        changed['joints'][0]['parent'] = 'OffsetPart'
        with self.assertRaisesRegex(WizardError, 'relationship'):
            validate_configuration(self.draft, changed)

    def test_rejects_unbounded_and_nonfinite_joint(self):
        config = self.configured()
        config['joints'][0]['axis'] = [0, 0, 3]
        with self.assertRaisesRegex(WizardError, 'unit vector'):
            validate_configuration(self.draft, config)
        config['joints'][0]['axis'] = [0, 0, 1]
        config['joints'][0]['limits'] = [float('nan'), 1]
        with self.assertRaisesRegex(WizardError, 'finite'):
            validate_configuration(self.draft, config)


if __name__ == '__main__':
    unittest.main()
