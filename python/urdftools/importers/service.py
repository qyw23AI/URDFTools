import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import struct
import tempfile
from dataclasses import dataclass
from uuid import UUID, uuid4
import xml.etree.ElementTree as ET
import zipfile


class ImportFailure(ValueError):
    def __init__(self, code, location, message):
        self.finding = dict(code=code, location=str(location), message=str(message), severity='error')
        super().__init__(message)


@dataclass(frozen=True)
class Limits:
    files: int = 10000
    total_bytes: int = 512 * 1024 * 1024
    file_bytes: int = 64 * 1024 * 1024
    xml_bytes: int = 4 * 1024 * 1024
    zip_ratio: int = 200


def xml(path, limit):
    if path.stat().st_size > limit:
        raise ValueError('XML size limit exceeded')
    data = path.read_bytes()
    if len(data) > limit or b'<!DOCTYPE' in data.upper() or b'<!ENTITY' in data.upper():
        raise ValueError('XML size limit or forbidden DTD/entity declaration')
    # Reject UTF-16/32 to keep the declaration check unambiguous.
    return ET.fromstring(data.decode('utf-8-sig'))


def safe_name(name):
    parts = PurePosixPath(name).parts
    if not parts or name.startswith('/') or '\\' in name or ':' in name or '\x00' in name or '..' in parts:
        raise ImportFailure('unsafe_path', name, 'Path must stay inside the imported bundle')
    return PurePosixPath(*parts).as_posix()


def mesh_check(path, limit):
    kind = path.suffix.lower()
    data = path.read_bytes()
    if not data:
        raise ValueError('Empty mesh')
    if kind == '.obj':
        lines = data.decode('utf-8-sig').splitlines()
        vertices = []
        faces = []
        for line in lines:
            fields = line.split()
            if fields and fields[0] == 'v':
                xyz = [float(v) for v in fields[1:4]]
                if len(xyz) != 3 or not all(math.isfinite(v) for v in xyz):
                    raise ValueError('Invalid OBJ vertex')
                vertices.append(xyz)
            if fields and fields[0] == 'f':
                ids = [int(v.split('/')[0]) for v in fields[1:]]
                if len(ids) < 3 or any(i == 0 or i > len(vertices) or i < -len(vertices) for i in ids):
                    raise ValueError('Invalid OBJ face indices')
                faces.append(ids)
        if not vertices or not faces:
            raise ValueError('OBJ requires vertices and faces')
        return {'format': 'obj', 'vertices': len(vertices), 'faces': len(faces)}
    if kind == '.stl':
        if len(data) >= 84 and len(data) == 84 + 50 * struct.unpack_from('<I', data, 80)[0]:
            count = struct.unpack_from('<I', data, 80)[0]
            if not count or any(not all(math.isfinite(x) for x in struct.unpack_from('<12f', data, 84+i*50)) for i in range(count)):
                raise ValueError('Invalid binary STL')
            return {'format': 'stl', 'triangles': count}
        text = data.decode('ascii')
        vertices = re.findall(r'\bvertex\s+(\S+)\s+(\S+)\s+(\S+)', text)
        if not text.lstrip().startswith('solid') or 'endsolid' not in text or not vertices or len(vertices) % 3 or any(not math.isfinite(float(v)) for xyz in vertices for v in xyz):
            raise ValueError('Invalid ASCII STL')
        return {'format': 'stl', 'triangles': len(vertices)//3}
    if kind == '.dae':
        tree = xml(path, limit)
        if tree.tag.split('}')[-1] != 'COLLADA' or not any(n.tag.split('}')[-1] == 'geometry' for n in tree.iter()):
            raise ValueError('DAE requires COLLADA geometry')
        textures = []
        for image in (node for node in tree.iter() if node.tag.split('}')[-1] == 'image'):
            for node in image:
                if node.tag.split('}')[-1] != 'init_from' or not node.text:
                    continue
                name = node.text.strip()
                if '://' in name or Path(name).is_absolute() or '\\' in name or not name:
                    raise ValueError('DAE texture must use a local relative path')
                texture = (path.parent / name).resolve()
                if not texture.is_file():
                    raise ValueError('DAE texture missing: ' + name)
                textures.append(name)
        return {'format': 'dae', 'validation': 'geometry and local textures present', 'textures': textures}
    raise ValueError('Unsupported mesh format: ' + kind)


class ImportService:
    def __init__(self, storage, limits=Limits()):
        self.storage = Path(storage)
        self.storage.mkdir(parents=True, exist_ok=True)
        self.limits = limits

    def _copy(self, source, target):
        count = total = 0
        inventory = []

        def write(name, stream):
            nonlocal count, total
            name = safe_name(name)
            count += 1
            if count > self.limits.files:
                raise ImportFailure('file_limit', name, 'Too many files')
            path = target / name
            path.parent.mkdir(parents=True, exist_ok=True)
            sha = hashlib.sha256()
            size = 0
            with path.open('xb') as out:
                while block := stream.read(65536):
                    size += len(block)
                    total += len(block)
                    if size > self.limits.file_bytes or total > self.limits.total_bytes:
                        raise ImportFailure('size_limit', name, 'Import byte limit exceeded')
                    out.write(block)
                    sha.update(block)
            inventory.append(dict(path=name, sha256=sha.hexdigest(), size=size))

        if source.suffix.lower() == '.zip' and source.is_file():
            with os.fdopen(os.open(source, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK), 'rb') as archive_source, zipfile.ZipFile(archive_source) as archive:
                entries = archive.infolist()
                if len(entries) > self.limits.files:
                    raise ImportFailure('file_limit', source.name, 'Too many ZIP entries')
                seen = set()
                for item in entries:
                    name = safe_name(item.filename)
                    mode = item.external_attr >> 16
                    if stat.S_ISLNK(mode) or (stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR)):
                        raise ImportFailure('special_file', name, 'ZIP links and special files are forbidden')
                    if name in seen:
                        raise ImportFailure('duplicate_path', name, 'Duplicate ZIP path')
                    seen.add(name)
                    if item.flag_bits & 1 or item.file_size > self.limits.file_bytes or item.file_size > max(1, item.compress_size) * self.limits.zip_ratio:
                        raise ImportFailure('zip_limit', name, 'Encrypted, oversized or excessive ratio ZIP member')
                    if not item.is_dir():
                        with archive.open(item) as stream:
                            write(name, stream)
        else:
            def copy_fd(name, fd):
                with os.fdopen(fd, 'rb') as stream:
                    before = os.fstat(stream.fileno())
                    if not stat.S_ISREG(before.st_mode):
                        raise ImportFailure('special_file', name, 'Only regular files are accepted')
                    write(name, stream)
                    after = os.fstat(stream.fileno())
                    if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (after.st_size, after.st_mtime_ns, after.st_ctime_ns):
                        raise ImportFailure('source_changed', name, 'Source changed during copying; retry import')

            if source.is_dir():
                root_fd = os.open(source, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
                try:
                    def fail_walk(error):
                        raise error
                    for directory, dirs, files, directory_fd in os.fwalk('.', dir_fd=root_fd, follow_symlinks=False, onerror=fail_walk):
                        for name in dirs + files:
                            mode = os.stat(name, dir_fd=directory_fd, follow_symlinks=False).st_mode
                            if stat.S_ISLNK(mode):
                                raise ImportFailure('symlink', name, 'Symlinks are forbidden in imports')
                            if not (stat.S_ISREG(mode) or stat.S_ISDIR(mode)):
                                raise ImportFailure('special_file', name, 'Only regular files and folders are accepted')
                        for name in sorted(files):
                            relative = (Path(directory) / name).as_posix()
                            copy_fd(relative, os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory_fd))
                finally:
                    os.close(root_fd)
            elif source.suffix.lower() == '.urdf':
                # A single file is scoped to itself; choose its folder to include resources.
                copy_fd(source.name, os.open(source, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK))
            else:
                raise ImportFailure('source_type', source.name, 'Choose a folder, URDF or ZIP')
        return inventory

    def ingest(self, source):
        source = Path(source).absolute()
        copy_source = source
        if source.is_file() and source.suffix.lower() == '.urdf':
            # Common ROS layout: robot/urdf/model.urdf + robot/meshes/*.
            # Importing only the XML loses DAE textures and the sibling meshes.
            if source.parent.name.lower() == 'urdf' and (source.parent.parent / 'meshes').is_dir():
                copy_source = source.parent.parent
            elif (source.parent / 'meshes').is_dir():
                copy_source = source.parent
        operation = str(uuid4())
        report = dict(operation_id=operation, status='failed', source_name=source.name,
                      models=[], findings=[], assets=[], package_map={}, selected_model=None)
        with tempfile.TemporaryDirectory(prefix='.import-', dir=self.storage) as temp:
            stage = Path(temp)
            bundle = stage / 'bundle'
            bundle.mkdir()
            try:
                if source.is_symlink():
                    raise ImportFailure('symlink', source.name, 'Source symlink is forbidden')
                if copy_source.is_dir() and self.storage.resolve().is_relative_to(copy_source.resolve()):
                    raise ImportFailure('storage_overlap', source.name, 'Import storage must be outside the source folder')
                report['assets'] = self._copy(copy_source, bundle)
                packages = {}
                for manifest in sorted(bundle.rglob('package.xml')):
                    try:
                        name = xml(manifest, self.limits.xml_bytes).findtext('name')
                        if not name or not re.fullmatch(r'[A-Za-z0-9_-]+', name):
                            raise ValueError('Invalid package name')
                        packages.setdefault(name, []).append(manifest.parent)
                    except (ValueError, ET.ParseError) as exc:
                        report['findings'].append(dict(code='package_xml', location=manifest.relative_to(bundle).as_posix(), message=str(exc), severity='error'))
                # Some published robot folders use package:// without a
                # package.xml. Bind only packages whose referenced files have
                # one unambiguous root inside the copied bundle.
                for model_file in sorted(bundle.rglob('*.urdf')):
                    try:
                        tree = xml(model_file, self.limits.xml_bytes)
                    except (ValueError, ET.ParseError, OSError):
                        continue
                    for element in tree.iter():
                        if element.tag not in ('mesh', 'texture'):
                            continue
                        uri = element.get('filename', '')
                        if not uri.startswith('package://'):
                            continue
                        package, separator, relative = uri[10:].partition('/')
                        if not separator or package in packages:
                            continue
                        try:
                            safe_relative = safe_name(relative)
                        except ImportFailure:
                            continue
                        candidates = [directory for directory in (bundle, *bundle.rglob('*'))
                                      if directory.is_dir() and (directory / safe_relative).is_file()]
                        if len(candidates) == 1:
                            packages[package] = candidates
                report['package_map'] = {name: [p.relative_to(bundle).as_posix() for p in paths] for name, paths in packages.items()}
                for model in sorted(bundle.rglob('*')):
                    if model.suffix.lower() == '.urdf' and model.is_file():
                        report['models'].append(self._model(model, bundle, packages))
                if not report['models']:
                    raise ImportFailure('no_models', source.name, 'No URDF models found')
                if source.is_file() and source.suffix.lower() == '.urdf' and copy_source != source:
                    selected_path = source.relative_to(copy_source).as_posix()
                    chosen = next((item for item in report['models'] if item['path'] == selected_path), None)
                    if chosen is None:
                        raise ImportFailure('selected_model_missing', selected_path, 'Chosen URDF was not included')
                    report['selected_model'] = selected_path
                    report['status'] = chosen['status']
                elif len(report['models']) > 1:
                    report['status'] = 'selection_required'
                else:
                    report['selected_model'] = report['models'][0]['path']
                    report['status'] = report['models'][0]['status']
                if report['findings']:
                    report['status'] = 'failed'
            except (OSError, ValueError, zipfile.BadZipFile, RuntimeError) as exc:
                report['findings'].append(exc.finding if isinstance(exc, ImportFailure) else dict(code='import_failed', location=source.name, message=str(exc), severity='error'))
                shutil.rmtree(bundle)
                bundle.mkdir()
                report['assets'] = []
            (stage / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
            stage.rename(self.storage / operation)
        return report

    def _model(self, path, bundle, packages):
        result = dict(path=path.relative_to(bundle).as_posix(), name=None, status='ready', resources=[], findings=[])
        try:
            tree = xml(path, self.limits.xml_bytes)
            if tree.tag != 'robot' or not tree.get('name') or not tree.findall('link'):
                raise ValueError('URDF must have a robot name and at least one link')
            result['name'] = tree.get('name')
            for index, node in enumerate(tree.iter()):
                if node.tag not in ('mesh', 'texture'):
                    continue
                uri = node.get('filename', '')
                location = f"{result['path']}#element[{index}]/{node.tag}@filename"
                resource = dict(uri=uri, location=location)
                result['resources'].append(resource)
                try:
                    if uri.startswith('package://'):
                        package, sep, relative = uri[10:].partition('/')
                        if not sep or len(packages.get(package, [])) != 1:
                            raise ImportFailure('package_unresolved', location, 'Package missing or ambiguous: ' + package)
                        candidate = packages[package][0] / safe_name(relative)
                    else:
                        if '://' in uri or Path(uri).is_absolute() or '\\' in uri or ':' in uri or not uri:
                            raise ImportFailure('resource_path', location, 'Only local relative or package:// resources accepted')
                        candidate = path.parent / uri
                    resolved = candidate.resolve()
                    if not resolved.is_relative_to(bundle.resolve()):
                        raise ImportFailure('resource_escape', location, 'Resource escapes imported bundle')
                    if not resolved.is_file():
                        raise ImportFailure('missing_resource', location, 'Resource not found: ' + uri)
                    resource['path'] = resolved.relative_to(bundle).as_posix()
                    if node.tag == 'mesh':
                        # DAE geometry files can be much larger than an URDF or package XML.
                        # Copying already enforced file_bytes; retain that cap for mesh XML
                        # instead of incorrectly rejecting vendor meshes above xml_bytes.
                        resource['inspection'] = mesh_check(resolved, self.limits.file_bytes)
                    else:
                        resource['inspection'] = {'validation': 'presence only; texture decoding deferred'}
                except (OSError, ValueError, ET.ParseError) as exc:
                    result['findings'].append(exc.finding if isinstance(exc, ImportFailure) else dict(code='damaged_resource', location=location, message=str(exc), severity='error'))
        except (OSError, ValueError, ET.ParseError) as exc:
            result['findings'].append(dict(code='invalid_urdf', location=result['path'], message=str(exc), severity='error'))
        if result['findings']:
            result['status'] = 'failed'
        return result

    def select(self, operation, model):
        operation = str(UUID(operation))
        path = self.storage / operation / 'report.json'
        report = json.loads(path.read_text())
        match = next((m for m in report['models'] if m['path'] == model), None)
        if match is None:
            raise ValueError('Model is not part of this import')
        report['selected_model'] = model
        report['status'] = 'failed' if report['findings'] else match['status']
        temporary = path.with_suffix('.tmp')
        temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2))
        temporary.replace(path)
        return report
