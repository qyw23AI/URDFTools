import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from uuid import uuid4

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "python"))

from pydantic import ValidationError
from urdftools.core.models import (RobotDocument, RobotSnapshot, ParameterEvidence, ReplaceLink,
                                   ReplaceJoint, EditTransaction, ProjectManifest)
from urdftools.core.documents import (canonical, content_hash, parse_document, save_document,
                                      load_document, snapshot, DocumentHistory, ConflictError)
from urdftools.core.assets import register_asset, verify_asset

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / 'tests/fixtures/S02'


def raw(name='double_link.json'):
    return json.loads((FIXTURES / name).read_text())


def document(name='double_link.json'):
    return parse_document((FIXTURES / name).read_bytes())


class DomainTests(unittest.TestCase):
    def test_two_link_parse_save_numeric_roundtrip(self):
        doc = document()
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'robot.json'
            save_document(target, doc)
            restored = load_document(target)
            self.assertEqual(restored, doc)
            self.assertEqual(content_hash(restored), content_hash(doc))
        self.assertEqual(len(restored.links), 2)
        self.assertEqual(restored.links[0].inertial.mass.value, 2.5)
        self.assertEqual([x.value for x in restored.joints[0].origin.xyz], [0.125, -0.25, 0.5])
        self.assertEqual([x.value for x in restored.links[1].inertial.tensor], [0.013, -0.001, 0.002, 0.022, -0.003, 0.03])
        self.assertEqual(restored.extensions[0].payload, '<fixture keep="yes"/>')

    def test_quadruped_tree_roundtrip_and_mass(self):
        doc = document('quadruped.json')
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'quadruped.json'
            save_document(path, doc)
            restored = load_document(path)
        self.assertEqual((len(restored.links), len(restored.joints)), (9, 8))
        self.assertAlmostEqual(sum(l.inertial.mass.value for l in restored.links), 8.875)
        self.assertEqual(sum(j.parent_id == restored.links[0].id for j in restored.joints), 4)
        self.assertEqual(restored, doc)
        self.assertEqual([p.value for p in restored.joints[7].origin.xyz], [0., 0., -0.25])

    def test_unknown_is_not_zero(self):
        limit = document().joints[0].limits.effort
        self.assertIsNone(limit.value)
        zero = copy.deepcopy(limit.model_dump())
        zero['value'] = 0.
        with self.assertRaises(ValidationError):
            ParameterEvidence.model_validate(zero)
        zero['provenance']['source_kind'] = 'default'
        self.assertEqual(ParameterEvidence.model_validate(zero).value, 0.)
        zero['value'] = None
        with self.assertRaises(ValidationError):
            ParameterEvidence.model_validate(zero)

    def test_nonfinite_every_numeric_location(self):
        for value in (float('nan'), float('inf'), -float('inf')):
            for field in ('mass', 'origin', 'tensor', 'axis', 'limit', 'uncertainty'):
                with self.subTest(value=value, field=field):
                    data = raw()
                    inertial = data['links'][0]['inertial']
                    if field == 'mass': inertial['mass']['value'] = value
                    if field == 'origin': inertial['origin']['xyz'][1]['value'] = value
                    if field == 'tensor': inertial['tensor'][2]['value'] = value
                    if field == 'axis': data['joints'][0]['axis'][2]['value'] = value
                    if field == 'limit': data['joints'][0]['limits']['lower']['value'] = value
                    if field == 'uncertainty': inertial['mass']['uncertainty'] = [0., value]
                    with self.assertRaises(ValidationError):
                        RobotDocument.model_validate(data)

    def test_numeric_strings_and_boolean_not_physical_values(self):
        for value in (True, '2.5'):
            data = raw()
            data['links'][0]['inertial']['mass']['value'] = value
            with self.assertRaises(ValidationError): RobotDocument.model_validate(data)

    def test_graph_invalid(self):
        for case in ('empty', 'duplicate_uuid', 'duplicate_name', 'dangling', 'self_loop', 'multiple_parents', 'cycle', 'disconnected_cycle'):
            with self.subTest(case=case):
                data = raw('quadruped.json')
                if case == 'empty': data['links'], data['joints'] = [], []
                if case == 'duplicate_uuid': data['links'][1]['id'] = data['links'][0]['id']
                if case == 'duplicate_name': data['links'][1]['name'] = data['links'][0]['name']
                if case == 'dangling': data['joints'][0]['child_id'] = str(uuid4())
                if case == 'self_loop': data['joints'][0]['child_id'] = data['joints'][0]['parent_id']
                if case == 'multiple_parents': data['joints'][1]['child_id'] = data['joints'][0]['child_id']
                if case == 'cycle':
                    extra = copy.deepcopy(data['joints'][1]); extra['id'] = str(uuid4()); extra['name'] = 'cycle'
                    extra['parent_id'] = data['links'][2]['id']; extra['child_id'] = data['links'][0]['id']
                    extra['origin']['relative_to'] = extra['parent_id']; data['joints'].append(extra)
                if case == 'disconnected_cycle':
                    data['joints'][0]['parent_id'] = data['links'][2]['id']
                    data['joints'][0]['origin']['relative_to'] = data['links'][2]['id']
                with self.assertRaises(ValidationError): RobotDocument.model_validate(data)

    def test_explicit_si_and_frames(self):
        for case in ('unit', 'handedness', 'parent_frame', 'com_frame', 'axis_norm', 'missing_axis', 'limit_order'):
            data = raw()
            if case == 'unit': data['links'][0]['inertial']['mass']['unit'] = 'm'
            if case == 'handedness': data['handedness'] = 'left'
            if case == 'parent_frame': data['joints'][0]['origin']['relative_to'] = data['links'][1]['id']
            if case == 'com_frame': data['links'][0]['inertial']['origin']['relative_to'] = data['links'][1]['id']
            if case == 'axis_norm': data['joints'][0]['axis'][0]['value'] = 2.
            if case == 'missing_axis': data['joints'][0]['axis'] = None
            if case == 'limit_order': data['joints'][0]['limits']['lower']['value'] = 9.
            with self.subTest(case=case), self.assertRaises(ValidationError): RobotDocument.model_validate(data)

    def test_large_finite_axis_rejected_as_validation_error(self):
        data = raw()
        data['joints'][0]['axis'][0]['value'] = 1e308
        with self.assertRaises(ValidationError):
            RobotDocument.model_validate(data)

    def test_mimic_reference_and_cycle(self):
        for case in ('dangling', 'cycle', 'compatible'):
            data = raw('quadruped.json')
            multiplier = copy.deepcopy(data['joints'][0]['axis'][1])
            offset = copy.deepcopy(data['joints'][0]['limits']['lower']); offset['value'] = 0.
            data['joints'][0]['mimic'] = dict(joint_id=data['joints'][1]['id'], multiplier=multiplier, offset=offset)
            if case == 'dangling': data['joints'][0]['mimic']['joint_id'] = str(uuid4())
            if case == 'cycle': data['joints'][1]['mimic'] = dict(joint_id=data['joints'][0]['id'], multiplier=multiplier, offset=offset)
            if case == 'compatible': self.assertIsNotNone(RobotDocument.model_validate(data).joints[0].mimic)
            else:
                with self.assertRaises(ValidationError): RobotDocument.model_validate(data)

    def test_old_schema_migration_preserves_backup_and_numbers(self):
        original = (FIXTURES / 'double_link_v1.json').read_bytes()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'old.json'; path.write_bytes(original)
            migrated = load_document(path, migrate=True)
            self.assertEqual(path.with_name('old.json.v1.bak').read_bytes(), original)
            self.assertEqual(json.loads(path.read_bytes())['schema_version'], 2)
            self.assertEqual(migrated, document())
            self.assertEqual(load_document(path, migrate=True), migrated)
            self.assertEqual(path.with_name('old.json.v1.bak').read_bytes(), original)

    def test_migration_does_not_guess_or_destroy(self):
        for version, units in ((1, 'mm'), (99, 'SI')):
            data = raw('double_link_v1.json'); data['schema_version'] = version; data['unit_system'] = units
            with self.assertRaises(ValueError): parse_document(json.dumps(data))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'old.json'; path.write_bytes((FIXTURES / 'double_link_v1.json').read_bytes())
            backup = path.with_name('old.json.v1.bak'); backup.write_bytes(b'prior backup')
            before = path.read_bytes()
            with self.assertRaises(FileExistsError): load_document(path, migrate=True)
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(backup.read_bytes(), b'prior backup')

    def test_duplicate_keys_and_extra_fields_rejected(self):
        with self.assertRaises(ValueError): parse_document('{"schema_version":2,"schema_version":1}')
        data = raw(); data['training_command'] = 'forbidden'
        with self.assertRaises(ValidationError): parse_document(data)

    def test_snapshot_is_deeply_immutable_and_hash_verified(self):
        snap = snapshot(document())
        with self.assertRaises(ValidationError): snap.document.links[0].inertial.mass.value = 3.
        with self.assertRaises(TypeError): snap.document.links[0] = snap.document.links[1]
        data = snap.model_dump(mode='json'); data['document']['links'][0]['inertial']['mass']['value'] = 99.
        with self.assertRaises(ValidationError): RobotSnapshot.model_validate(data)
        self.assertEqual(content_hash(snap.document), snap.content_hash)
        data = snap.document.model_dump(mode='json')
        reordered = dict(reversed(list(data.items())))
        self.assertEqual(canonical(RobotDocument.model_validate(reordered)), canonical(snap.document))

    def test_timestamp_and_uncertainty(self):
        data = raw(); data['provenance']['recorded_at'] = '2026-10-22T00:00:00'
        with self.assertRaises(ValidationError): parse_document(data)
        data = raw(); data['links'][0]['inertial']['mass']['uncertainty'] = [3., 2.]
        with self.assertRaises(ValidationError): parse_document(data)

    def test_project_manifest(self):
        snap = snapshot(document())
        manifest = dict(schema_version=2, id=uuid4(), title='fixture project', robot_snapshot_ids=[snap.id],
                        active_snapshot=snap.id, source_assets=[], settings={'display_angle_unit':'deg'})
        self.assertEqual(ProjectManifest.model_validate(manifest).active_snapshot, snap.id)
        manifest['active_snapshot'] = uuid4()
        with self.assertRaises(ValidationError): ProjectManifest.model_validate(manifest)


class TransactionTests(unittest.TestCase):
    def setUp(self):
        self.history = DocumentHistory(document())

    def base(self):
        s = self.history.current
        return dict(base_id=s.id, base_hash=s.content_hash)

    def propose(self, actor='agent', name='edited'):
        data = self.history.current.document.links[1].model_dump(); data['name'] = name
        op = ReplaceLink(kind='replace_link', link=data)
        return self.history.propose((op,), actor=actor, **self.base())

    def test_preview_confirm_undo_redo_numeric_history(self):
        original = self.history.current
        tx = self.propose()
        self.assertEqual(self.history.current, original)
        self.assertIn('+      "name": "edited"', self.history.diff(tx))
        with self.assertRaises(ValueError): self.history.apply(tx)
        current = self.history.apply(tx, confirmed=True)
        self.assertEqual(current.document.links[1].name, 'edited')
        self.assertEqual(current.document.links[1].inertial, original.document.links[1].inertial)
        self.assertIsNotNone(self.history.transactions[0].confirmed_at)
        self.assertEqual(self.history.undo(**self.base()), original)
        self.assertEqual(self.history.redo(**self.base()), current)

    def test_ui_and_agent_same_validation_and_result(self):
        agent = self.propose('agent'); ui = self.propose('ui')
        self.assertEqual(agent.preview_snapshot.content_hash, ui.preview_snapshot.content_hash)
        self.assertEqual(agent.preview_snapshot.document, ui.preview_snapshot.document)
        data = self.history.current.document.joints[0].model_dump()
        data['child_id'] = uuid4()
        op = ReplaceJoint(kind='replace_joint', joint=data)
        for actor in ('ui', 'agent'):
            with self.assertRaises(ValidationError): self.history.propose((op,), actor=actor, **self.base())
        self.assertEqual(len(self.history.transactions), 0)

    def test_confirmation_requires_boolean_true_without_mutation(self):
        for value in ('false', 'true', 1, [], None, False):
            with self.subTest(value=value):
                self.history = DocumentHistory(document())
                original = self.history.current
                tx = self.propose()
                with self.assertRaises(ValueError):
                    self.history.apply(tx, confirmed=value)
                self.assertEqual(self.history.current, original)
                self.assertEqual(self.history.transactions, ())
        self.assertEqual(self.history.apply(tx, confirmed=True), tx.preview_snapshot)

    def test_stale_conflicting_transaction(self):
        first, stale = self.propose(), self.propose(name='stale')
        self.history.apply(first, confirmed=True)
        before = self.history.current
        with self.assertRaises(ConflictError): self.history.apply(stale, confirmed=True)
        self.assertEqual(self.history.current, before)

    def test_preview_tampering_rejected(self):
        tx = self.propose()
        data = tx.model_dump()
        data['preview_snapshot'] = snapshot(document(), self.history.current.id)
        forged = EditTransaction.model_validate(data)
        with self.assertRaises(ValueError): self.history.apply(forged, confirmed=True)
        self.assertEqual(self.history.current.document, document())

    def test_undo_branch_discards_redo_not_original(self):
        original = self.history.current
        self.history.apply(self.propose(), confirmed=True)
        self.history.undo(**self.base())
        self.history.apply(self.propose(name='branch'), confirmed=True)
        with self.assertRaises(ValueError): self.history.redo(**self.base())
        self.assertEqual(original.document.links[1].name, 'arm')
        self.assertEqual(self.history.current.document.links[1].name, 'branch')

    def test_json_operation_and_transaction_flow(self):
        data = self.history.current.document.joints[0].model_dump(mode='json')
        data['origin']['xyz'][0]['value'] = 0.375
        tx = self.history.propose([{'kind': 'replace_joint', 'joint': data}], actor='ui', **self.base())
        encoded = json.loads(tx.model_dump_json())
        current = self.history.apply(encoded, confirmed=True)
        self.assertEqual(current.document.joints[0].origin.xyz[0].value, 0.375)
        before = current
        with self.assertRaises(ValidationError):
            self.history.propose([{'kind': 'run_training'}], actor='agent', **self.base())
        self.assertEqual(self.history.current, before)

    def test_failed_multi_operation_is_atomic(self):
        doc = self.history.current.document
        good = doc.links[0].model_dump(); good['name'] = 'renamed'
        bad = doc.joints[0].model_dump(); bad['child_id'] = uuid4()
        with self.assertRaises(ValidationError):
            self.history.propose((ReplaceLink(kind='replace_link', link=good), ReplaceJoint(kind='replace_joint', joint=bad)), actor='ui', **self.base())
        self.assertEqual(self.history.current.document, doc)


class AssetTests(unittest.TestCase):
    def test_asset_hash_real_bytes_and_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'original.bin'; payload = b'original CAD fixture\x00\xff'; path.write_bytes(payload)
            asset = register_asset(directory, 'original.bin', mime='application/octet-stream', license_id='CC0-1.0')
            self.assertEqual(asset.sha256, hashlib.sha256(payload).hexdigest())
            self.assertEqual(asset.size, len(payload))
            self.assertEqual(verify_asset(directory, asset), asset)
            path.write_bytes(b'changed')
            with self.assertRaises(ValueError): verify_asset(directory, asset)

    def test_paths_and_symlink_escape(self):
        with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryDirectory() as outside:
            target = Path(outside) / 'private'; target.write_bytes(b'outside')
            (Path(directory) / 'escape').symlink_to(target)
            for path in ('../private', '/etc/passwd', 'a/../b', 'a\\b', 'C:/private', './a', 'a//b', 'escape'):
                with self.subTest(path=path), self.assertRaises(ValueError): register_asset(directory, path, mime='text/plain')

    def test_asset_refs_geometry_and_material_validation(self):
        data = raw()
        frame = copy.deepcopy(data['links'][0]['inertial']['origin'])
        geometry = dict(id=str(uuid4()), kind='mesh', origin=frame, dimensions=[], asset_id=str(uuid4()), scale=[1., 1., 1.], material_id=None, provenance=data['provenance'])
        data['links'][0]['visual'] = [geometry]
        with self.assertRaises(ValidationError): parse_document(data)
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / 'mesh.obj').write_bytes(b'v 0 0 0\n')
            asset = register_asset(directory, 'mesh.obj', mime='model/obj')
            data['assets'] = [asset.model_dump(mode='json')]; geometry['asset_id'] = str(asset.id)
            self.assertEqual(parse_document(data).links[0].visual[0].scale, (1., 1., 1.))
            geometry['scale'] = [-1., 1., 1.]
            with self.assertRaises(ValidationError): parse_document(data)
            geometry['scale'] = [1., 1., 1.]; geometry['material_id'] = str(uuid4())
            with self.assertRaises(ValidationError): parse_document(data)


class ContractTests(unittest.TestCase):
    def test_generated_contracts_no_drift(self):
        result = subprocess.run([str(ROOT / '.venv/bin/python'), 'scripts/generate_contracts.py', '--check'], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_typescript_actual_documents_and_negative_types_compile(self):
        # Compile actual Python-normalized fixtures against generated TS types.
        with tempfile.TemporaryDirectory(dir=ROOT / 'tests/s02') as directory:
            path = Path(directory) / 'contracts.ts'
            lines = ["import type {RobotDocument, ParameterEvidence, EditTransaction} from '../../../packages/contracts/index';"]
            for i, name in enumerate(('double_link.json', 'quadruped.json')):
                lines.append(f'const d{i} = {json.dumps(document(name).model_dump(mode="json"), ensure_ascii=False)} satisfies RobotDocument;')
            lines += [
                '// @ts-expect-error schema version is fixed', 'const badVersion: RobotDocument["schema_version"] = 99;',
                '// @ts-expect-error SI units are explicit', 'const badUnit: ParameterEvidence["unit"] = "mm";',
                '// @ts-expect-error source kind is closed', 'const badSource: ParameterEvidence["provenance"]["source_kind"] = "guessed";',
                '// @ts-expect-error deep immutable tuple', 'd0.links[0].inertial!.origin.xyz = [];',
                'declare const readonlyDoc: RobotDocument;', '// @ts-expect-error immutable domain contract', 'readonlyDoc.links[0].name = "mutated";',
                '// @ts-expect-error only defined operations accepted', 'const badOperation: EditTransaction["operations"][number]["kind"] = "run_training";',
            ]
            path.write_text('\n'.join(lines))
            result = subprocess.run([str(ROOT / '.tools/node/bin/node'), str(ROOT / 'node_modules/typescript/bin/tsc'), '--strict', '--noEmit', '--skipLibCheck', '--target', 'ES2022', '--moduleResolution', 'bundler', '--module', 'ESNext', str(path)], cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
