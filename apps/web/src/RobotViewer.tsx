import { useEffect, useRef, useState } from 'react';
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { OBJLoader } from 'three/addons/loaders/OBJLoader.js';
import URDFLoader from 'urdf-loader';
import type { URDFRobot } from 'urdf-loader/src/URDFClasses.js';

export type RobotImport = {
  operation_id: string;
  package_map: Record<string, string[]>;
  selected_model: string | null;
  status: string;
  models: { path: string; name: string | null; status: string; resources: { uri: string; path?: string }[] }[];
};

type JointSetting = { name: string; kind: string; value: number; min: number; max: number; unit: string };
type Vec3Tuple = [number, number, number];
const INERTIA_KEYS = ['ixx', 'ixy', 'ixz', 'iyy', 'iyz', 'izz'] as const;
type InertiaKey = typeof INERTIA_KEYS[number];
type InertiaValues = Record<InertiaKey, number | null>;
type PhysicsRow = {
  name: string;
  inertialPresent: boolean;
  mass: number | null;
  comLocal: Vec3Tuple | null;
  comWorld: Vec3Tuple | null;
  inertia: InertiaValues;
};
type LinkTreeNode = {
  name: string;
  viaJoint?: { name: string; kind: string };
  children: LinkTreeNode[];
};
type SelectedObject = { type: 'link' | 'joint'; name: string };
type SelectionInfo = SelectedObject & { position: Vec3Tuple; dimensions: Vec3Tuple | null };

function assetUrl(operation: string, relative: string): string {
  return 'urdftools://asset/' + encodeURIComponent(operation) + '/bundle/' +
    relative.split('/').map(encodeURIComponent).join('/');
}
function directChild(parent: Element | null, tagName: string): Element | null {
  if (!parent) return null;
  for (const child of Array.from(parent.children)) {
    if (child.tagName.toLowerCase() === tagName) return child;
  }
  return null;
}
function numericAttribute(node: Element | null, name: string): number | null {
  const raw = node?.getAttribute(name);
  if (raw == null || raw.trim() === '') return null;
  const value = Number(raw);
  return Number.isFinite(value) ? value : null;
}
function vectorAttribute(node: Element | null, name: string): Vec3Tuple | null {
  const raw = node?.getAttribute(name);
  if (raw == null || raw.trim() === '') return null;
  const values = raw.trim().split(/\s+/).map(Number);
  if (values.length !== 3 || values.some(value => !Number.isFinite(value))) return null;
  return [values[0], values[1], values[2]];
}
function isURDFVisual(object: THREE.Object3D): boolean {
  return (object as THREE.Object3D & { isURDFVisual?: boolean }).isURDFVisual === true;
}
function isURDFCollider(object: THREE.Object3D): boolean {
  return (object as THREE.Object3D & { isURDFCollider?: boolean }).isURDFCollider === true;
}
function markedObjects(robot: URDFRobot, predicate: (object: THREE.Object3D) => boolean): THREE.Object3D[] {
  const result: THREE.Object3D[] = [];
  robot.traverse(object => { if (predicate(object)) result.push(object); });
  return result;
}
function effectivelyVisible(object: THREE.Object3D): boolean {
  let current: THREE.Object3D | null = object;
  while (current) {
    if (!current.visible) return false;
    current = current.parent;
  }
  return true;
}
function visibleMeshCount(robot: URDFRobot): number {
  let count = 0;
  robot.traverse(object => {
    if (object instanceof THREE.Mesh && effectivelyVisible(object)) count++;
  });
  return count;
}
function visualBoundsForLink(link: THREE.Object3D): THREE.Box3 | null {
  link.updateWorldMatrix(true, true);
  const bounds = new THREE.Box3();
  for (const child of link.children) {
    if (isURDFVisual(child)) bounds.expandByObject(child);
  }
  return bounds.isEmpty() ? null : bounds;
}
function overallVisualBounds(robot: URDFRobot): THREE.Box3 | null {
  robot.updateMatrixWorld(true);
  const bounds = new THREE.Box3();
  robot.traverse(object => {
    if (isURDFVisual(object)) bounds.expandByObject(object);
  });
  return bounds.isEmpty() ? null : bounds;
}
function tuple(vector: THREE.Vector3): Vec3Tuple {
  return [vector.x, vector.y, vector.z];
}
function readPhysicsRows(robot: URDFRobot): PhysicsRow[] {
  robot.updateMatrixWorld(true);
  return Object.entries(robot.links).map(([name, link]) => {
    const inertial = directChild(link.urdfNode, 'inertial');
    const mass = numericAttribute(directChild(inertial, 'mass'), 'value');
    const comLocal = vectorAttribute(directChild(inertial, 'origin'), 'xyz');
    const comWorld = comLocal
      ? tuple(link.localToWorld(new THREE.Vector3(comLocal[0], comLocal[1], comLocal[2])))
      : null;
    const inertiaNode = directChild(inertial, 'inertia');
    const inertia = Object.fromEntries(INERTIA_KEYS.map(key => [key, numericAttribute(inertiaNode, key)])) as InertiaValues;
    return { name, inertialPresent: inertial !== null, mass, comLocal, comWorld, inertia };
  });
}
function buildLinkTree(robot: URDFRobot): LinkTreeNode[] {
  const edges: { parent: string; child: string; name: string; kind: string }[] = [];
  const childNames = new Set<string>();
  for (const [name, joint] of Object.entries(robot.joints)) {
    const parent = directChild(joint.urdfNode, 'parent')?.getAttribute('link') || '';
    const child = directChild(joint.urdfNode, 'child')?.getAttribute('link') || '';
    if (parent && child && robot.links[parent] && robot.links[child]) {
      edges.push({ parent, child, name, kind: joint.jointType });
      childNames.add(child);
    }
  }
  const linkNames = Object.keys(robot.links);
  const roots = linkNames.filter(name => !childNames.has(name));
  const create = (name: string, ancestors: Set<string>): LinkTreeNode => {
    if (ancestors.has(name)) return { name, children: [] };
    const next = new Set(ancestors);
    next.add(name);
    const children = edges.filter(edge => edge.parent === name).map(edge => ({
      ...create(edge.child, next),
      viaJoint: { name: edge.name, kind: edge.kind }
    }));
    return { name, children };
  };
  return (roots.length ? roots : linkNames).map(name => create(name, new Set()));
}
function countTreeLinks(nodes: LinkTreeNode[]): number {
  return nodes.reduce((sum, node) => sum + 1 + countTreeLinks(node.children), 0);
}
function selectionInfo(robot: URDFRobot, selected: SelectedObject): SelectionInfo | null {
  const object = selected.type === 'link' ? robot.links[selected.name] : robot.joints[selected.name];
  if (!object) return null;
  robot.updateMatrixWorld(true);
  const position = tuple(object.getWorldPosition(new THREE.Vector3()));
  const bounds = selected.type === 'link' ? visualBoundsForLink(object) : null;
  return {
    ...selected,
    position,
    dimensions: bounds ? tuple(bounds.getSize(new THREE.Vector3())) : null
  };
}
function owningLinkName(object: THREE.Object3D): string | null {
  let current = object.parent;
  while (current) {
    if ((current as THREE.Object3D & { isURDFLink?: boolean }).isURDFLink === true) return current.name;
    current = current.parent;
  }
  return null;
}
function applyVisibility(robot: URDFRobot, visuals: boolean, collisions: boolean, isolatedLink: string | null) {
  const visualObjects = markedObjects(robot, isURDFVisual);
  const collisionObjects = markedObjects(robot, isURDFCollider);
  visualObjects.forEach(object => { object.visible = visuals && (!isolatedLink || owningLinkName(object) === isolatedLink); });
  collisionObjects.forEach(object => { object.visible = collisions && (!isolatedLink || owningLinkName(object) === isolatedLink); });
  return {
    visualCount: visualObjects.length,
    collisionCount: collisionObjects.length,
    visibleVisualCount: visualObjects.filter(object => object.visible).length,
    visibleCollisionCount: collisionObjects.filter(object => object.visible).length
  };
}
function styleCollisionMeshes(robot: URDFRobot): number {
  let count = 0;
  robot.traverse(object => {
    if (!(object instanceof THREE.Mesh)) return;
    let parent = object.parent;
    while (parent && !isURDFCollider(parent)) parent = parent.parent;
    if (!parent) return;
    const currentMaterials = Array.isArray(object.material) ? object.material : [object.material];
    if (currentMaterials.some(material => material.userData.urdfToolsCollisionStyle === true)) {
      count++;
      return;
    }
    const material = new THREE.MeshBasicMaterial({
      color: 0xff5b6e, transparent: true, opacity: 0.8, depthWrite: false, wireframe: true
    });
    material.userData.urdfToolsCollisionStyle = true;
    object.material = material;
    count++;
  });
  return count;
}
function formatVector(value: Vec3Tuple | null, unit: string): string {
  return value ? '(' + value.map(n => n.toFixed(3)).join(', ') + ') ' + unit : '未知（URDF 未显式提供）';
}
function physicsFingerprint(rows: PhysicsRow[]): string {
  return rows.map(row => [
    row.name,
    row.mass === null ? 'unknown' : String(row.mass),
    row.comLocal ? row.comLocal.join(',') : 'unknown',
    INERTIA_KEYS.map(key => row.inertia[key] === null ? '?' : String(row.inertia[key])).join(',')
  ].join(':')).join('|');
}

export function RobotViewer({ report }: { report: RobotImport }) {
  const host = useRef<HTMLDivElement>(null);
  const robotRef = useRef<URDFRobot | null>(null);
  const focusObjectRef = useRef<((selected: SelectedObject) => void) | null>(null);
  const resetViewRef = useRef<(() => void) | null>(null);
  const refreshModelAnalysisRef = useRef<((robot: URDFRobot) => void) | null>(null);
  const isolatedLinkRef = useRef<string | null>(null);
  const showComRef = useRef(true);
  const visualVisibleRef = useRef(true);
  const collisionVisibleRef = useRef(false);
  const [joints, setJoints] = useState<JointSetting[]>([]);
  const [linkTree, setLinkTree] = useState<LinkTreeNode[]>([]);
  const [physicsRows, setPhysicsRows] = useState<PhysicsRow[]>([]);
  const [error, setError] = useState('');
  const [assetsLoaded, setAssetsLoaded] = useState(false);
  const [meshCount, setMeshCount] = useState(0);
  const [visualCount, setVisualCount] = useState(0);
  const [collisionCount, setCollisionCount] = useState(0);
  const [collisionStyledMeshCount, setCollisionStyledMeshCount] = useState(0);
  const [visibleVisualCount, setVisibleVisualCount] = useState(0);
  const [visibleCollisionCount, setVisibleCollisionCount] = useState(0);
  const [comMarkerCount, setComMarkerCount] = useState(0);
  const [visibleComMarkerCount, setVisibleComMarkerCount] = useState(0);
  const [overallBounds, setOverallBounds] = useState<Vec3Tuple | null>(null);
  const [selectedObject, setSelectedObject] = useState<SelectedObject | null>(null);
  const [selection, setSelection] = useState<SelectionInfo | null>(null);
  const [visualVisible, setVisualVisible] = useState(true);
  const [collisionVisible, setCollisionVisible] = useState(false);
  const [showComMarkers, setShowComMarkers] = useState(true);
  const [isolatedLink, setIsolatedLink] = useState<string | null>(null);
  const [screenshotReady, setScreenshotReady] = useState(false);
  const [screenshotMessage, setScreenshotMessage] = useState('');
  const [viewResetCount, setViewResetCount] = useState(0);
  const [jointRotation, setJointRotation] = useState('');
  visualVisibleRef.current = visualVisible;
  collisionVisibleRef.current = collisionVisible;
  isolatedLinkRef.current = isolatedLink;
  showComRef.current = showComMarkers;
  const selected = report.models.find(model => model.path === report.selected_model);
  const ready = report.status === 'ready' && selected?.status === 'ready';

  useEffect(() => {
    if (!ready || !selected || !host.current) return;
    let disposed = false;
    let raf = 0;
    let renderer: THREE.WebGLRenderer | undefined;
    let controls: OrbitControls | undefined;
    const owned: THREE.Object3D[] = [];
    const element = host.current;
    robotRef.current = null;
    focusObjectRef.current = null;
    resetViewRef.current = null;
    refreshModelAnalysisRef.current = null;
    setJoints([]);
    setAssetsLoaded(false);
    setLinkTree([]);
    setPhysicsRows([]);
    setMeshCount(0);
    setVisualCount(0);
    setCollisionCount(0);
    setCollisionStyledMeshCount(0);
    setVisibleVisualCount(0);
    setVisibleCollisionCount(0);
    setComMarkerCount(0);
    setVisibleComMarkerCount(0);
    setOverallBounds(null);
    setSelectedObject(null);
    setSelection(null);
    setVisualVisible(true);
    setCollisionVisible(false);
    setShowComMarkers(true);
    setIsolatedLink(null);
    setScreenshotReady(false);
    setScreenshotMessage('');
    setViewResetCount(0);
    setError('');
    try {
      const scene = new THREE.Scene();
      scene.background = new THREE.Color(0x1b2636);
      const camera = new THREE.PerspectiveCamera(50, 1, 0.001, 1000);
      camera.up.set(0, 0, 1);
      camera.position.set(1.3, -1.5, 1.0);
      renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true });
      renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
      element.appendChild(renderer.domElement);
      controls = new OrbitControls(camera, renderer.domElement);
      controls.enableDamping = true;
      const grid = new THREE.GridHelper(2, 20, 0x6882a2, 0x354458);
      grid.rotation.x = Math.PI / 2;
      scene.add(grid, new THREE.AxesHelper(0.35), new THREE.HemisphereLight(0xffffff, 0x4d657b, 2));
      const sun = new THREE.DirectionalLight(0xffffff, 2);
      sun.position.set(3, -3, 6);
      scene.add(sun);
      const comGroup = new THREE.Group();
      comGroup.name = 'URDFTools COM markers';
      scene.add(comGroup);
      const comMarkers = new Map<string, THREE.Mesh>();
      const render = () => {
        if (disposed || !renderer || !controls) return;
        const width = Math.max(2, element.clientWidth);
        const height = Math.max(2, element.clientHeight);
        renderer.setSize(width, height, false);
        camera.aspect = width / height;
        camera.updateProjectionMatrix();
        controls.update();
        renderer.render(scene, camera);
        raf = requestAnimationFrame(render);
      };
      render();
      const fitView = (currentRobot: URDFRobot) => {
        if (!controls) return;
        currentRobot.updateMatrixWorld(true);
        const box = overallVisualBounds(currentRobot) ?? new THREE.Box3().setFromObject(currentRobot);
        const size = new THREE.Vector3();
        const center = new THREE.Vector3();
        if (box.isEmpty()) {
          center.set(0, 0, 0);
          size.set(0.3, 0.3, 0.3);
        } else {
          box.getSize(size);
          box.getCenter(center);
        }
        const radius = Math.max(0.15, size.length() / 2);
        camera.position.copy(center).add(new THREE.Vector3(radius * 2, -radius * 2, radius * 1.6));
        camera.near = Math.max(0.001, radius / 1000);
        camera.far = Math.max(20, radius * 100);
        camera.updateProjectionMatrix();
        controls.target.copy(center);
        controls.update();
      };
      const refreshAnalysis = (currentRobot: URDFRobot) => {
        if (disposed) return;
        currentRobot.updateMatrixWorld(true);
        setCollisionStyledMeshCount(styleCollisionMeshes(currentRobot));
        const rows = readPhysicsRows(currentRobot);
        setPhysicsRows(rows);
        const bounds = overallVisualBounds(currentRobot);
        setOverallBounds(bounds ? tuple(bounds.getSize(new THREE.Vector3())) : null);
        setMeshCount(visibleMeshCount(currentRobot));
        const knownComRows = rows.filter(row => row.comWorld !== null);
        const knownComNames = new Set(knownComRows.map(row => row.name));
        for (const row of knownComRows) {
          let marker = comMarkers.get(row.name);
          if (!marker) {
            marker = new THREE.Mesh(new THREE.SphereGeometry(0.012, 16, 12),
              new THREE.MeshBasicMaterial({ color: 0xffc857, depthTest: false, depthWrite: false }));
            marker.name = 'COM marker: ' + row.name;
            marker.userData.linkName = row.name;
            marker.renderOrder = 1000;
            comMarkers.set(row.name, marker);
            comGroup.add(marker);
          }
          const point = row.comWorld as Vec3Tuple;
          marker.position.set(point[0], point[1], point[2]);
          marker.visible = showComRef.current && (!isolatedLinkRef.current || isolatedLinkRef.current === row.name);
        }
        for (const [name, marker] of comMarkers) {
          if (knownComNames.has(name)) continue;
          comGroup.remove(marker);
          marker.geometry.dispose();
          const materials = Array.isArray(marker.material) ? marker.material : [marker.material];
          materials.forEach(material => material.dispose());
          comMarkers.delete(name);
        }
        setComMarkerCount(comMarkers.size);
        setVisibleComMarkerCount(Array.from(comMarkers.values()).filter(marker => marker.visible).length);
      };
      refreshModelAnalysisRef.current = refreshAnalysis;
      const recount = () => {
        const current = robotRef.current;
        if (!current || disposed) return;
        refreshAnalysis(current);
        setAssetsLoaded(true);
        resetViewRef.current?.();
      };
      const manager = new THREE.LoadingManager();
      manager.onLoad = recount;
      manager.onError = url => { if (!disposed) setError('网格加载失败：' + url); };
      const loader = new URDFLoader(manager);
      loader.parseCollision = true;
      loader.packages = Object.fromEntries(Object.entries(report.package_map).flatMap(([name, dirs]) =>
        dirs.length === 1 ? [[name, assetUrl(report.operation_id, dirs[0])]] : []));
      const defaultMeshLoader = loader.loadMeshCb.bind(loader);
      loader.loadMeshCb = (url, manager, material, complete) => {
        if (/\.obj(?:\?|$)/i.test(url)) {
          new OBJLoader(manager).load(url, object => { object.traverse(child => {
            if (child instanceof THREE.Mesh && material) child.material = material;
          }); complete(object); }, undefined, cause => complete(null as unknown as THREE.Object3D, cause instanceof Error ? cause : new Error(String(cause))));
        } else {
          defaultMeshLoader(url, manager, material, complete);
        }
      };
      loader.load(assetUrl(report.operation_id, selected.path), robot => {
        if (disposed) return;
        robotRef.current = robot;
        owned.push(robot);
        scene.add(robot);
        robot.updateMatrixWorld(true);
        setCollisionStyledMeshCount(styleCollisionMeshes(robot));
        resetViewRef.current = () => fitView(robot);
        resetViewRef.current();
        focusObjectRef.current = target => {
          const object = target.type === 'link' ? robot.links[target.name] : robot.joints[target.name];
          if (!object || !controls) return;
          robot.updateMatrixWorld(true);
          const visualBox = target.type === 'link' ? visualBoundsForLink(object) : null;
          const targetCenter = visualBox ? visualBox.getCenter(new THREE.Vector3()) : object.getWorldPosition(new THREE.Vector3());
          const offset = camera.position.clone().sub(controls.target);
          if (offset.length() < 0.1) offset.set(1, -1, 1);
          controls.target.copy(targetCenter);
          camera.position.copy(targetCenter).add(offset);
          controls.update();
        };
        const loaded: JointSetting[] = Object.entries(robot.joints).filter(([, joint]) =>
          ['revolute', 'continuous', 'prismatic'].includes(joint.jointType)).map(([name, joint]) => {
          const linear = joint.jointType === 'prismatic';
          const finite = joint.jointType !== 'continuous' &&
            Number.isFinite(joint.limit.lower) && Number.isFinite(joint.limit.upper) &&
            joint.limit.lower < joint.limit.upper;
          return { name, kind: joint.jointType, value: 0, min: finite ? joint.limit.lower : linear ? -0.5 : -Math.PI,
            max: finite ? joint.limit.upper : linear ? 0.5 : Math.PI, unit: linear ? 'm' : 'rad' };
        });
        setJoints(loaded);
        setLinkTree(buildLinkTree(robot));
        const counts = applyVisibility(robot, visualVisibleRef.current, collisionVisibleRef.current, isolatedLinkRef.current);
        setVisualCount(counts.visualCount);
        setCollisionCount(counts.collisionCount);
        setVisibleVisualCount(counts.visibleVisualCount);
        setVisibleCollisionCount(counts.visibleCollisionCount);
        refreshAnalysis(robot);
        resetViewRef.current?.();
      }, undefined, cause => { if (!disposed) setError('URDF 加载失败：' + String(cause)); });
    } catch (cause) {
      setError('三维渲染不可用：' + String(cause));
    }
    return () => {
      disposed = true;
      cancelAnimationFrame(raf);
      controls?.dispose();
      focusObjectRef.current = null;
      resetViewRef.current = null;
      refreshModelAnalysisRef.current = null;
      for (const root of owned) root.traverse(object => {
        if (object instanceof THREE.Mesh) {
          object.geometry?.dispose();
          const materials = Array.isArray(object.material) ? object.material : [object.material];
          materials.forEach(material => material?.dispose());
        }
      });
      renderer?.dispose();
      renderer?.domElement.remove();
      robotRef.current = null;
    };
  }, [report.operation_id, report.selected_model, ready]);

  useEffect(() => {
    const robot = robotRef.current;
    if (!robot) return;
    const counts = applyVisibility(robot, visualVisible, collisionVisible, isolatedLink);
    setVisualCount(counts.visualCount);
    setCollisionCount(counts.collisionCount);
    setVisibleVisualCount(counts.visibleVisualCount);
    setVisibleCollisionCount(counts.visibleCollisionCount);
    refreshModelAnalysisRef.current?.(robot);
  }, [visualVisible, collisionVisible, isolatedLink, showComMarkers]);

  function selectStructure(type: 'link' | 'joint', name: string) {
    const next = { type, name };
    setSelectedObject(next);
    const robot = robotRef.current;
    if (!robot) return;
    const info = selectionInfo(robot, next);
    setSelection(info);
    focusObjectRef.current?.(next);
  }
  function changeJoint(name: string, value: number) {
    const robot = robotRef.current;
    if (!robot || !Number.isFinite(value)) return;
    const setting = joints.find(joint => joint.name === name);
    if (!setting || value < setting.min || value > setting.max) return;
    robot.setJointValue(name, value);
    robot.updateMatrixWorld(true);
    setJointRotation(robot.joints[name].quaternion.toArray().map(number => number.toFixed(6)).join(','));
    setJoints(old => old.map(joint => joint.name === name ? { ...joint, value } : joint));
    refreshModelAnalysisRef.current?.(robot);
    if (selectedObject) setSelection(selectionInfo(robot, selectedObject));
  }
  function exportScreenshot() {
    try {
      const canvas = host.current?.querySelector('canvas');
      if (!canvas) throw new Error('三维画布尚未准备好');
      const dataUrl = canvas.toDataURL('image/png');
      if (!dataUrl.startsWith('data:image/png;base64,')) throw new Error('无法生成 PNG 图像');
      const anchor = document.createElement('a');
      anchor.href = dataUrl;
      anchor.download = 'URDFTools-viewer.png';
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      setScreenshotReady(true);
      setScreenshotMessage('PNG 已生成，已触发下载。');
    } catch (cause) {
      setError('截图导出失败：' + String(cause));
      setScreenshotReady(false);
    }
  }
  const knownMassCount = physicsRows.filter(row => row.mass !== null).length;
  const unknownMassCount = physicsRows.length - knownMassCount;
  const knownMassTotal = physicsRows.reduce((sum, row) => sum + (row.mass ?? 0), 0);
  const massComplete = physicsRows.length > 0 && unknownMassCount === 0;
  const comComplete = physicsRows.length > 0 && physicsRows.every(row => row.mass !== null && row.comWorld !== null);
  const totalCom = comComplete && knownMassTotal > 0 ? physicsRows.reduce((sum, row) => {
    const com = row.comWorld as Vec3Tuple;
    return [sum[0] + (row.mass as number) * com[0], sum[1] + (row.mass as number) * com[1],
      sum[2] + (row.mass as number) * com[2]] as Vec3Tuple;
  }, [0, 0, 0] as Vec3Tuple).map(value => value / knownMassTotal) as Vec3Tuple : null;
  const linkCount = countTreeLinks(linkTree);
  const selectedKey = selectedObject ? selectedObject.type + ':' + selectedObject.name : '';
  const selectedPosition = selection ? selection.position.map(number => number.toFixed(3)).join(',') : '';
  const selectedDimensions = selection?.dimensions ? selection.dimensions.map(number => number.toFixed(3)).join(',') : '';
  const boundsAttribute = overallBounds ? overallBounds.map(number => number.toFixed(3)).join(',') : '';
  if (!ready) return null;
  const renderLinkNode = (node: LinkTreeNode, depth: number): React.ReactNode => (
    <div className="tree-link" key={node.name} style={{ marginLeft: depth * 12 }}>
      <button type="button" data-structure-node={'link:' + node.name}
        aria-pressed={selectedObject?.type === 'link' && selectedObject.name === node.name}
        onClick={() => selectStructure('link', node.name)}>Link · {node.name}</button>
      {node.children.map(child => <div className="tree-edge" key={child.viaJoint?.name || child.name}>
        {child.viaJoint && <button type="button" data-structure-node={'joint:' + child.viaJoint.name}
          aria-pressed={selectedObject?.type === 'joint' && selectedObject.name === child.viaJoint.name}
          onClick={() => selectStructure('joint', child.viaJoint!.name)}>
          Joint · {child.viaJoint.name} ({child.viaJoint.kind})
        </button>}
        {renderLinkNode(child, depth + 1)}
      </div>)}
    </div>
  );
  return <section aria-label="三维机器人查看器" className="robot-viewer"
    data-mesh-count={meshCount} data-joint-quaternion={jointRotation} data-assets-loaded={String(assetsLoaded)}
    data-tree-link-count={linkCount} data-tree-joint-count={Object.keys(robotRef.current?.joints ?? {}).length}
    data-visual-count={visualCount} data-collision-count={collisionCount}
    data-collision-styled-mesh-count={collisionStyledMeshCount}
    data-visible-visual-count={visibleVisualCount} data-visible-collision-count={visibleCollisionCount}
    data-com-marker-count={comMarkerCount} data-visible-com-marker-count={visibleComMarkerCount}
    data-com-visible={String(showComMarkers)} data-isolated-link={isolatedLink ?? ''}
    data-screenshot-ready={String(screenshotReady)} data-view-reset-count={viewResetCount}
    data-collision-visible={String(collisionVisible)} data-visual-visible={String(visualVisible)}
    data-mass-known-count={knownMassCount} data-mass-unknown-count={unknownMassCount}
    data-total-known-mass={knownMassTotal.toFixed(3)} data-mass-complete={String(massComplete)}
    data-physics-fingerprint={physicsFingerprint(physicsRows)}
    data-overall-bounds={boundsAttribute} data-selected-node={selectedKey}
    data-selected-position={selectedPosition} data-selected-dimensions={selectedDimensions}>
    <h2>三维模型 · {selected?.name || selected?.path}</h2>
    <p>URDF 使用右手坐标与 Z 轴朝上。鼠标左键旋转、滚轮缩放、右键平移。红色 X、绿色 Y、蓝色 Z。</p>
    <div className="viewer-grid">
      <div>
        <div ref={host} className="robot-canvas" aria-label="机器人三维场景" />
        <p className="hint" data-assets-status>{assetsLoaded ? 'URDF 与网格资源加载完成' : '正在解析 URDF 并加载网格资源…'}</p>
        <fieldset className="viewer-toggles">
          <legend>模型显示</legend>
          <label><input type="checkbox" aria-label="显示视觉模型" checked={visualVisible}
            onChange={event => setVisualVisible(event.target.checked)} />视觉模型</label>
          <label><input type="checkbox" aria-label="显示碰撞体" checked={collisionVisible}
            onChange={event => setCollisionVisible(event.target.checked)} />碰撞体</label>
          <label><input type="checkbox" aria-label="显示已知质心" checked={showComMarkers}
            onChange={event => setShowComMarkers(event.target.checked)} />已知质心</label>
          <button type="button" aria-label="隔离选中 Link" disabled={selectedObject?.type !== 'link'}
            onClick={() => { if (selectedObject?.type === 'link') setIsolatedLink(current => current === selectedObject.name ? null : selectedObject.name); }}>
            {isolatedLink ? '解除隔离' : '隔离选中 Link'}
          </button>
          <button type="button" aria-label="重置视角" onClick={() => { resetViewRef.current?.(); setViewResetCount(count => count + 1); }}>重置视角</button>
          <button type="button" aria-label="导出三维截图" onClick={exportScreenshot}>导出 PNG</button>
          <span>黄色球表示 URDF 显式提供的质心位置。显示/隔离只改变场景，不修改 URDF 或物理参数。</span>
        </fieldset>
        {screenshotMessage && <p role="status" data-screenshot-message>{screenshotMessage}</p>}
        {error && <p role="alert">{error}</p>}
        <section aria-label="几何测量" className="analysis-panel">
          <h3>几何测量</h3>
          <p>整机视觉包围盒（近似，单位 m）：{overallBounds ? formatVector(overallBounds, 'm') : '尚无可测量的视觉几何'}</p>
          <p>网格：当前可见 {meshCount} 个 Mesh；视觉组 {visibleVisualCount}/{visualCount}；碰撞组 {visibleCollisionCount}/{collisionCount}。</p>
          {selection ? <div data-selection-info>
            <strong>{selection.type === 'link' ? 'Link' : 'Joint'} · {selection.name}</strong>
            <p>当前姿态下坐标：{formatVector(selection.position, 'm')}</p>
            <p>视觉包围盒尺寸：{selection.dimensions ? formatVector(selection.dimensions, 'm') : '关节无独立尺寸；或该 Link 没有视觉几何'}</p>
          </div> : <p>在结构树中选择 Link 或 Joint，可定位并查看坐标。</p>}
          <p className="hint">尺寸来自加载后的视觉网格包围盒，不是 CAD 精确尺寸；网格比例、单位错误仍需单独检查。</p>
        </section>
      </div>
      <div className="analysis-column">
        <section aria-label="机器人结构树" className="analysis-panel">
          <h3>结构树 · {linkCount} Link / {Object.keys(robotRef.current?.joints ?? {}).length} Joint</h3>
          {linkTree.length ? <div className="structure-tree">{linkTree.map(node => renderLinkNode(node, 0))}</div> : <p>尚无可显示的结构树。</p>}
        </section>
        <section aria-label="质量与惯量" className="analysis-panel">
          <h3>质量、质心与惯量</h3>
          <p>已知质量合计：{knownMassTotal.toFixed(3)} kg{massComplete ? '（所有 Link 均显式提供）' : '（部分合计；' + unknownMassCount + ' 个 Link 未显式提供质量）'}</p>
          <p>整机质心：{totalCom ? formatVector(totalCom, 'm') : '不可完整计算：至少一个 Link 的质量或质心位置未显式提供'}</p>
          <p className="hint">只读取 URDF 中明确写出的数值。缺失字段显示未知，不将 urdf-loader 的零默认值当作真实参数；惯量张量在其惯性坐标系下展示，未进行物理合理性验证。</p>
          <div className="physics-table-wrap"><table className="physics-table">
            <thead><tr><th>Link</th><th>质量</th><th>质心（Link 局部 / 当前世界）</th><th>惯量张量（kg·m²）</th></tr></thead>
            <tbody>{physicsRows.map(row => <tr key={row.name} data-physics-link={row.name}>
              <th scope="row">{row.name}</th>
              <td>{row.mass === null ? '未知（未显式提供）' : row.mass.toFixed(3) + ' kg · URDF'}</td>
              <td>{row.comLocal ? formatVector(row.comLocal, 'm') + ' / ' + formatVector(row.comWorld, 'm') : '未知（未显式提供）'}</td>
              <td><code>{INERTIA_KEYS.map(key => key + '=' + (row.inertia[key] === null ? '未知' : (row.inertia[key] as number).toExponential(2))).join(' · ')}</code></td>
            </tr>)}</tbody>
          </table></div>
        </section>
      </div>
    </div>
    <h3>关节控制（{joints.length}）</h3>
    {joints.length === 0 ? <p>当前模型没有可移动关节。</p> :
      <div className="joint-panel">{joints.map(joint => <label key={joint.name} className="joint-item">
        <span>{joint.name} · {joint.kind}</span>
        <input aria-label={joint.name} type="range" min={joint.min} max={joint.max} step={0.01}
          value={joint.value} onChange={event => changeJoint(joint.name, Number(event.target.value))} />
        <output>{joint.value.toFixed(2)} {joint.unit}</output>
      </label>)}</div>}
  </section>;
}