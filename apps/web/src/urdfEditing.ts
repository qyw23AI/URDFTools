import { Euler, Quaternion, Vector3 } from 'three';
import type { RobotImport } from './RobotViewer';
export type NodeSelection = {type: 'link' | 'joint'; name: string};
export type SurfacePoint = {link: string; point: number[]; normal: number[]};
export const serialize = (doc: Document) => new XMLSerializer().serializeToString(doc);
export function parse(xml: string) {
  const doc = new DOMParser().parseFromString(xml, 'application/xml');
  if (doc.querySelector('parsererror') || doc.documentElement.tagName !== 'robot' || /<!DOCTYPE|<!ENTITY/i.test(xml)) throw new Error('URDF XML 格式不正确');
  return doc;
}
export function elements(doc: Document, tag: string) { return Array.from(doc.documentElement.children).filter(e=>e.tagName === tag); }
export function rootLink(doc: Document) {
  const children = new Set(elements(doc,'joint').map(j=>j.querySelector('child')?.getAttribute('link')));
  return elements(doc,'link').find(l=>!children.has(l.getAttribute('name')))?.getAttribute('name') || '';
}
export async function sourceXml(report: RobotImport, absolute = false) {
  const model = report.models.find(m=>m.path === report.selected_model);
  if (!model) throw new Error('请先选择模型');
  const url = (path: string) => 'urdftools://asset/' + report.operation_id + '/bundle/' + path.split('/').map(encodeURIComponent).join('/');
  const response = await fetch(url(model.path));
  if (!response.ok) throw new Error('无法读取 URDF');
  const xml = await response.text();
  if (!absolute) return xml;
  const doc = parse(xml);
  for (const node of Array.from(doc.querySelectorAll('mesh, texture'))) {
    const uri = node.getAttribute('filename');
    const resource = model.resources.find(r=>r.uri === uri);
    if (!resource?.path) throw new Error('找不到资源：' + uri);
    node.setAttribute('filename',url(resource.path));
  }
  return serialize(doc);
}
export function locate(xml: string, selected: NodeSelection) {
  // Match XML start tags and exact attribute values, independent of attribute order/quotes.
  const pattern = new RegExp('<' + selected.type + '\\b[^>]*>', 'g');
  for (const match of xml.matchAll(pattern)) {
    const name = /\bname\s*=\s*(["'])(.*?)\1/.exec(match[0]);
    if (name?.[2] !== selected.name) continue;
    const start = match.index!;
    const endTag = '</' + selected.type + '>';
    const end = match[0].endsWith('/>') ? start + match[0].length : xml.indexOf(endTag,start) + endTag.length;
    return {start,end:Math.max(start + match[0].length,end)};
  }
  return null;
}
export function removeBranch(xml: string, selected: NodeSelection) {
  const doc=parse(xml), joints=elements(doc,'joint');
  const target=selected.type==='link' ? selected.name : joints.find(j=>j.getAttribute('name')===selected.name)?.querySelector('child')?.getAttribute('link');
  if (!target || target===rootLink(doc)) throw new Error('不能删除根 Link；可以直接编辑其代码');
  const removed=new Set([target]);
  let changed=true;
  while(changed) { changed=false; for(const j of joints) if(removed.has(j.querySelector('parent')?.getAttribute('link') || '')) {
    const child=j.querySelector('child')!.getAttribute('link')!; if(!removed.has(child)){removed.add(child);changed=true;}
  }}
  for(const link of elements(doc,'link')) if(removed.has(link.getAttribute('name')!)) link.remove();
  for(const j of joints) if(removed.has(j.querySelector('child')?.getAttribute('link') || '')) j.remove();
  return serialize(doc);
}
export function insertModule(xml: string, moduleXml: string) {
  const doc=parse(xml), module=parse(moduleXml), prefix='cad_' + crypto.randomUUID().slice(0,8) + '_';
  const root=rootLink(module);
  const names=new Map(elements(module,'link').map(l=>[l.getAttribute('name')!,prefix+l.getAttribute('name')]));
  for(const element of Array.from(module.documentElement.children)) {
    if(element.hasAttribute('name')) element.setAttribute('name',prefix+element.getAttribute('name'));
    for(const ref of Array.from(element.querySelectorAll('parent, child'))) ref.setAttribute('link',names.get(ref.getAttribute('link')!)!);
    for(const ref of Array.from(element.querySelectorAll('mimic'))) ref.setAttribute('joint',prefix+ref.getAttribute('joint'));
    doc.documentElement.appendChild(doc.importNode(element,true));
  }
  const joint=doc.createElement('joint');joint.setAttribute('name',prefix+'placement');joint.setAttribute('type','fixed');
  for(const [tag,attr,value] of [['parent','link',rootLink(parse(xml))],['child','link',prefix+root],['origin','xyz','0.4 0 0']]) {
    const e=doc.createElement(tag);e.setAttribute(attr,value);joint.appendChild(e);
  }
  doc.documentElement.appendChild(joint);
  return {xml:serialize(doc),child:prefix+root,joint:prefix+'placement'};
}
export function connectModule(xml: string, jointName: string, parent: SurfacePoint, child: SurfacePoint, type: 'fixed'|'continuous', axis: string) {
  if(parent.link===child.link) throw new Error('请选择两个不同模块');
  const doc=parse(xml), joint=elements(doc,'joint').find(j=>j.getAttribute('name')===jointName);
  if(!joint || joint.querySelector('child')?.getAttribute('link')!==child.link) throw new Error('请在新模块上选择第二个连接点');
  const rotation=new Quaternion().setFromUnitVectors(new Vector3().fromArray(child.normal).normalize(),new Vector3().fromArray(parent.normal).normalize().negate());
  const offset=new Vector3().fromArray(parent.point).sub(new Vector3().fromArray(child.point).applyQuaternion(rotation));
  // URDF RPY = extrinsic XYZ = Three intrinsic ZYX.
  const angles=new Euler().setFromQuaternion(rotation,'ZYX');
  const origin=joint.querySelector('origin')!;
  origin.setAttribute('xyz',offset.toArray().join(' '));origin.setAttribute('rpy',[angles.x,angles.y,angles.z].join(' '));
  joint.querySelector('parent')!.setAttribute('link',parent.link);joint.setAttribute('type',type);
  joint.querySelector('axis')?.remove();
  if(type==='continuous') {const e=doc.createElement('axis');e.setAttribute('xyz',axis);joint.appendChild(e);}
  return serialize(doc);
}
