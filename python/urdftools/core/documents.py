"""Canonical persistence, explicit v1 migration, and shared validated edit history."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile
from uuid import uuid4

from pydantic import TypeAdapter

from .models import EditTransaction, Operation, RobotDocument, RobotSnapshot


def canonical(document: RobotDocument) -> bytes:
    # Defined as Python JSON, sorted object keys, ordered arrays, UTF-8, no NaN.
    return json.dumps(document.model_dump(mode='json'), sort_keys=True,
                      separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode('utf-8')


def content_hash(document):
    return hashlib.sha256(canonical(document)).hexdigest()


def snapshot(document, parent_id=None):
    document = RobotDocument.model_validate(document)
    return RobotSnapshot(id=uuid4(), content_hash=content_hash(document), parent_id=parent_id,
                         document=document, created_at=datetime.now(timezone.utc))


def atomic_write(path: Path, data: bytes):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.' + path.name, dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def save_document(path, document):
    atomic_write(Path(path), canonical(RobotDocument.model_validate(document)) + b'\n')


def parse_document(data):
    if isinstance(data, (bytes, str)):
        def unique(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError(f'duplicate JSON key: {key}')
                result[key] = value
            return result
        data = json.loads(data, object_pairs_hook=unique)
    # Only v1's explicit SI header is migrated. No guessed unit/frame defaults.
    if data.get('schema_version') == 1:
        data = dict(data)
        if data.pop('unit_system', None) != 'SI':
            raise ValueError('v1 migration requires explicit SI')
        data['units'] = 'SI'
        data['schema_version'] = 2
    return RobotDocument.model_validate(data)


def load_document(path, *, migrate=False):
    path = Path(path)
    original = path.read_bytes()
    document = parse_document(original)
    if migrate and json.loads(original)['schema_version'] == 1:
        backup = path.with_name(path.name + '.v1.bak')
        # Never silently overwrite an earlier backup.
        with backup.open('xb') as stream:
            stream.write(original)
            stream.flush()
            os.fsync(stream.fileno())
        save_document(path, document)
    return document


class ConflictError(ValueError):
    pass


class DocumentHistory:
    """In-memory core history. API/session persistence belongs to later phases.

    Proposals do not mutate history; UI and agent use identical operations and
    validation. Applying requires explicit confirmation and a current base ID/hash.
    """
    def __init__(self, document):
        self._snapshots = [snapshot(document)]
        self._cursor = 0
        self._transactions = []

    @property
    def current(self):
        return self._snapshots[self._cursor]

    @property
    def transactions(self):
        return tuple(self._transactions)

    def _check(self, base_id, base_hash):
        if (base_id, base_hash) != (self.current.id, self.current.content_hash):
            raise ConflictError('snapshot changed; rebase and preview again')

    def _evaluate(self, operations):
        data = self.current.document.model_dump(mode='json')
        for operation in operations:
            field, entity = ('links', operation.link) if operation.kind == 'replace_link' else ('joints', operation.joint)
            matches = [i for i, item in enumerate(data[field]) if item['id'] == str(entity.id)]
            if not matches:
                raise ValueError('operation target does not exist')
            data[field][matches[0]] = entity.model_dump(mode='json')
        return RobotDocument.model_validate(data)

    def propose(self, operations, *, actor, base_id, base_hash):
        self._check(base_id, base_hash)
        operations = TypeAdapter(tuple[Operation, ...]).validate_python(operations)
        preview = snapshot(self._evaluate(operations), self.current.id)
        return EditTransaction(id=uuid4(), base_snapshot=base_id, base_hash=base_hash,
                               operations=operations, preview_snapshot=preview,
                               validation='valid', actor=actor, confirmed_at=None)

    def diff(self, transaction):
        self._check(transaction.base_snapshot, transaction.base_hash)
        import difflib
        before = json.dumps(self.current.document.model_dump(mode='json'), indent=2, sort_keys=True).splitlines(True)
        after = json.dumps(transaction.preview_snapshot.document.model_dump(mode='json'), indent=2, sort_keys=True).splitlines(True)
        return ''.join(difflib.unified_diff(before, after, fromfile='base', tofile='preview'))

    def apply(self, transaction, *, confirmed=False):
        transaction = EditTransaction.model_validate(transaction)
        self._check(transaction.base_snapshot, transaction.base_hash)
        if confirmed is not True:
            raise ValueError('explicit product user confirmation required')
        expected = self._evaluate(transaction.operations)
        preview = transaction.preview_snapshot
        if preview.parent_id != self.current.id or preview.document != expected or preview.content_hash != content_hash(expected):
            raise ValueError('preview does not match validated operations')
        if any(s.id == preview.id for s in self._snapshots):
            raise ValueError('snapshot ID reused')
        applied = EditTransaction.model_validate({**transaction.model_dump(), 'confirmed_at': datetime.now(timezone.utc)})
        self._snapshots = self._snapshots[:self._cursor + 1] + [preview]
        self._cursor += 1
        self._transactions.append(applied)
        return preview

    def undo(self, *, base_id, base_hash):
        self._check(base_id, base_hash)
        if self._cursor == 0:
            raise ValueError('nothing to undo')
        self._cursor -= 1
        return self.current

    def redo(self, *, base_id, base_hash):
        self._check(base_id, base_hash)
        if self._cursor + 1 == len(self._snapshots):
            raise ValueError('nothing to redo')
        self._cursor += 1
        return self.current


def save_snapshot(path, value):
    value = RobotSnapshot.model_validate(value)
    atomic_write(Path(path), value.model_dump_json(indent=2).encode('utf-8') + b'\n')


def load_snapshot(path):
    return RobotSnapshot.model_validate_json(Path(path).read_bytes())
