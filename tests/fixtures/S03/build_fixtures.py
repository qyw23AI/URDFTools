"""Original CC0 synthetic import fixtures; rerunnable, no downloaded models."""
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parent

def put(name, text):
    path = ROOT / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)

mesh = 'v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n'
put('中文机器人/示例包/package.xml', '<package><name>demo_robot</name></package>')
put('中文机器人/示例包/meshes/三角.obj', mesh)
put('中文机器人/示例包/urdf/01好模型.urdf', '''<robot name="中文样机"><link name="base"><visual><geometry><mesh filename="package://demo_robot/meshes/三角.obj"/></geometry></visual><collision><geometry><mesh filename="../meshes/三角.obj"/></geometry></collision></link></robot>''')
put('中文机器人/示例包/urdf/02缺失.urdf', '<robot name="缺失网格"><link name="base"><visual><geometry><mesh filename="../meshes/不存在.stl"/></geometry></visual></link></robot>')
put('damaged/bad.obj', 'v NaN 0 0\nf 1 2 3\n')
put('damaged/bad.urdf', '<robot name="damaged"><link name="base"><visual><geometry><mesh filename="bad.obj"/></geometry></visual></link></robot>')
put('malformed/bad.urdf', '<robot name="broken"><link>')
put('entity/bad.urdf', '<!DOCTYPE robot [<!ENTITY secret SYSTEM "file:///etc/passwd">]><robot name="&secret;"/>')
with zipfile.ZipFile(ROOT / 'valid.zip', 'w', zipfile.ZIP_DEFLATED) as z:
    for p in sorted((ROOT / '中文机器人').rglob('*')):
        if p.is_file():
            z.write(p, p.relative_to(ROOT / '中文机器人').as_posix())
for name, member in [('traversal.zip', '../escaped.urdf'), ('absolute.zip', '/tmp/escaped.urdf'), ('backslash.zip', '..\\escaped.urdf')]:
    with zipfile.ZipFile(ROOT / name, 'w') as z:
        z.writestr(member, '<robot name="escape"><link name="base"/></robot>')
with zipfile.ZipFile(ROOT / 'symlink.zip', 'w') as z:
    item = zipfile.ZipInfo('escape')
    item.create_system = 3
    item.external_attr = 0o120777 << 16
    z.writestr(item, '/etc/passwd')
put('corrupt.zip', 'This is deliberately not a ZIP')
