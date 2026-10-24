"""Immutable URDF editing and actual CAD mesh import. Never writes source inputs."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import uuid
import xml.etree.ElementTree as ET
from urllib.parse import urlparse, unquote
import zipfile


def validate(xml):
    if len(xml) > 8 * 1024 * 1024 or '<!DOCTYPE' in xml.upper() or '<!ENTITY' in xml.upper():
        raise ValueError('URDF 过大或包含不支持的 XML 声明')
    robot = ET.fromstring(xml)
    if robot.tag != 'robot':
        raise ValueError('根元素必须是 robot')
    links = [x.get('name') for x in robot.findall('link')]
    joints = robot.findall('joint')
    names = [x.get('name') for x in joints]
    if not links or any(not n for n in links + names) or len(set(links)) != len(links) or len(set(names)) != len(names):
        raise ValueError('Link/Joint 名称缺失或重复')
    parents = {}
    for joint in joints:
        p, c = joint.find('parent'), joint.find('child')
        if p is None or c is None or p.get('link') not in links or c.get('link') not in links:
            raise ValueError('关节引用不存在的 Link')
        child, parent = c.get('link'), p.get('link')
        if child in parents or child == parent:
            raise ValueError('每个 Link 只能有一个父关节，且不能连接自身')
        parents[child] = parent
    if len(set(links) - parents.keys()) != 1:
        raise ValueError('URDF 必须有一个根 Link；删除关节时请删除其子树或重新连接')
    for link in links:
        seen = set()
        while link in parents:
            if link in seen:
                raise ValueError('关节不能形成环')
            seen.add(link)
            link = parents[link]
    return robot


def read_report(store, operation):
    if str(uuid.UUID(operation)) != operation:
        raise ValueError('无效导入编号')
    return json.loads((store / operation / 'report.json').read_text())


def prepare(store, xml, output, baseline):
    robot = validate(xml)
    record = read_report(store, baseline['operation_id']) if baseline else None
    copied = {}
    def resource(operation, relative):
        source_record = read_report(store, operation)
        assets = {a['path']: a for a in source_record['assets']}
        if relative not in assets:
            raise ValueError('引用的资源不在导入清单中：' + relative)
        if operation not in copied:
            for rel, asset in assets.items():
                if Path(rel).suffix.lower() == '.urdf':
                    continue
                source = store / operation / 'bundle' / rel
                if not source.resolve().is_relative_to((store / operation / 'bundle').resolve()):
                    raise ValueError('资源路径越界')
                data = source.read_bytes()
                if len(data) != asset['size'] or hashlib.sha256(data).hexdigest() != asset['sha256']:
                    raise ValueError('来源资源已变化')
                dest = output / 'assets' / operation / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(data)
            copied[operation] = True
        return 'assets/' + operation + '/' + relative
    for node in list(robot.iter('mesh')) + list(robot.iter('texture')):
        uri = node.get('filename', '')
        parsed = urlparse(uri)
        if parsed.scheme == 'urdftools' and parsed.netloc == 'asset':
            operation, container, relative = unquote(parsed.path).lstrip('/').split('/', 2)
            if container != 'bundle':
                raise ValueError('无效资源地址')
        elif record:
            model = next(m for m in record['models'] if m['path'] == baseline['selected_model'])
            mapped = next((r.get('path') for r in model['resources'] if r['uri'] == uri), None)
            relative = mapped or str(Path(model['path']).parent / uri)
            operation = record['operation_id']
        else:
            raise ValueError('缺少资源来源，请先导入模型')
        node.set('filename', resource(operation, relative))
    output.mkdir(parents=True, exist_ok=True)
    ET.indent(robot, space='  ')
    (output / 'model.urdf').write_text(ET.tostring(robot, encoding='unicode'), encoding='utf-8')
    return {'path': str(output / 'model.urdf')}


def cad(source, output, unit):
    output.mkdir(parents=True, exist_ok=True)
    ext = source.suffix.lower()
    if ext in ('.step', '.stp'):
        from build123d import import_step, export_stl
        shape = import_step(str(source))
        if not export_stl(shape, str(output / 'part.stl')):
            raise ValueError('CAD 网格转换失败')
        mesh, scale = 'part.stl', '0.001 0.001 0.001'
        shutil.copy2(source, output / ('source' + ext))
    elif ext in ('.stl', '.obj'):
        mesh = 'part' + ext
        shutil.copy2(source, output / mesh)
        scale = '0.001 0.001 0.001' if unit == 'mm' else '1 1 1'
    else:
        raise ValueError('支持 STEP、STL 和 OBJ')
    robot = ET.Element('robot', name='cad_module')
    link = ET.SubElement(robot, 'link', name='part')
    visual = ET.SubElement(link, 'visual')
    geometry = ET.SubElement(visual, 'geometry')
    ET.SubElement(geometry, 'mesh', filename=mesh, scale=scale)
    robot.append(ET.Comment('CAD visual geometry only. Mass, inertia and collision are unspecified.'))
    ET.indent(robot, space='  ')
    (output / 'model.urdf').write_text(ET.tostring(robot, encoding='unicode'))
    return {'path': str(output / 'model.urdf')}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['prepare', 'cad', 'export'])
    parser.add_argument('request')
    args = parser.parse_args()
    req = json.loads(Path(args.request).read_text())
    if args.action == 'prepare':
        result = prepare(Path(req['store']), req['xml'], Path(req['output']), req.get('baseline'))
    elif args.action == 'cad':
        result = cad(Path(req['source']), Path(req['output']), req['unit'])
    else:
        store = Path(req['store'])
        record = read_report(store, req['operation'])
        with zipfile.ZipFile(req['output'], 'w', zipfile.ZIP_DEFLATED) as archive:
            for asset in record['assets']:
                file = store / req['operation'] / 'bundle' / asset['path']
                if not file.resolve().is_relative_to((store / req['operation'] / 'bundle').resolve()):
                    raise ValueError('资源路径越界')
                data = file.read_bytes()
                if hashlib.sha256(data).hexdigest() != asset['sha256']:
                    raise ValueError('导出资源发生变化')
                archive.writestr(asset['path'], data)
        result = {'path': req['output']}
    print(json.dumps(result))

if __name__ == '__main__':
    main()
