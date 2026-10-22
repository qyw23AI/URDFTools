#!/usr/bin/env python3
"""Run and retain the S02 local document workflow with original synthetic inputs."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'python'))
from urdftools.core.documents import (load_document, save_document, save_snapshot, load_snapshot,
                                      snapshot, DocumentHistory, content_hash)
from urdftools.core.models import ReplaceLink


def main():
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    output = ROOT / 'artifacts/S02/workflows' / stamp
    output.mkdir(parents=True)
    summary = {'origin': 'synthetic_fixture', 'license': 'CC0-1.0', 'reference_data_coverage': 0,
               'command': ['.venv/bin/python', 'scripts/s02_workflow.py'], 'documents': []}
    for name in ('double_link.json', 'quadruped.json'):
        source = ROOT / 'tests/fixtures/S02' / name
        doc = load_document(source)
        save_document(output / name, doc)
        restored = load_document(output / name)
        assert restored == doc
        snap = snapshot(doc)
        target = output / (source.stem + '.snapshot.json')
        save_snapshot(target, snap)
        assert load_snapshot(target) == snap
        total_mass = sum(link.inertial.mass.value for link in restored.links)
        assert total_mass == (3.25 if name == 'double_link.json' else 8.875)
        summary['documents'].append({'fixture': str(source.relative_to(ROOT)),
                                     'input_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
                                     'snapshot_hash': snap.content_hash, 'links': len(doc.links),
                                     'joints': len(doc.joints), 'total_mass_kg': total_mass,
                                     'roundtrip_equal': True, 'snapshot_roundtrip_equal': True})
    old = ROOT / 'tests/fixtures/S02/double_link_v1.json'
    migration = output / 'migrated.json'
    migration.write_bytes(old.read_bytes())
    migrated = load_document(migration, migrate=True)
    assert migrated == load_document(ROOT / 'tests/fixtures/S02/double_link.json')
    assert migration.with_name('migrated.json.v1.bak').read_bytes() == old.read_bytes()
    history = DocumentHistory(migrated)
    before = history.current
    data = before.document.links[1].model_dump()
    data['inertial']['mass']['value'] = 0.875
    transaction = history.propose((ReplaceLink(kind='replace_link', link=data),), actor='agent',
                                  base_id=before.id, base_hash=before.content_hash)
    (output / 'proposed.diff').write_text(history.diff(transaction))
    assert history.current == before
    after = history.apply(transaction, confirmed=True)
    assert after.document.links[1].inertial.mass.value == 0.875
    assert before.document.links[1].inertial.mass.value == 0.75
    assert before.content_hash != after.content_hash
    (output / 'transaction.json').write_text(history.transactions[0].model_dump_json(indent=2))
    save_snapshot(output / 'edited.snapshot.json', after)
    assert history.undo(base_id=after.id, base_hash=after.content_hash) == before
    assert history.redo(base_id=before.id, base_hash=before.content_hash) == after
    summary.update(migration_backup_equal=True, undo_redo_equal=True,
                   original_mass_kg=0.75, edited_mass_kg=0.875,
                   edited_content_hash=content_hash(after.document), status='passed')
    (output / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print('Retained workflow evidence:', output.relative_to(ROOT))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
