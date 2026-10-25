import type { NodeSelection, SurfacePoint } from './urdfEditing';
import { useEffect, useRef, useState } from 'react';
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { OBJLoader } from 'three/addons/loaders/OBJLoader.js';
import { ColladaLoader } from 'three/addons/loaders/ColladaLoader.js';
import URDFLoader from 'urdf-loader';
import type { URDFRobot } from 'urdf-loader/src/URDFClasses.js';
import { FloatingPanel } from './FloatingPanel';
import { StructureGraph } from './StructureGraph';

export type RobotImport = {
  operation_id: string;
  package_map: Record<string, string[]>;
  selected_model: string | null;
  status: string;
  assets?: { path: string; size: number; sha256: string }[];
  models: { path: string; name: string | null; status: string; resources: { uri: string; path?: string }[] }[];
};

type JointSetting = { name: string; kind: string; value: number; min: number; max: number;
  previewMin: number; previewMax: number; hasLimit: boolean; useLimit: boolean; unit: string };
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
export type CompareEntry = { id: string; report: RobotImport };
type GravityResult = Awaited<ReturnType<NonNullable<Window['urdftools']>['viewerSettle']>>;
type GravityPose = { position: THREE.Vector3; quaternion: THREE.Quaternion; joints: Record<string, number> };
type PassiveGravityPose = GravityPose & { robot: URDFRobot };
type PassiveRobot = { id: string; robot: URDFRobot; report: RobotImport };

function hasImageAssets(report: RobotImport): boolean {
  return Boolean(report.assets?.some(asset => /\.(png|jpe?g|bmp|webp)$/i.test(asset.path)));
}
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
function gravitySupportBounds(robot: URDFRobot): THREE.Box3 | null {
  robot.updateMatrixWorld(true);
  const feet = new THREE.Box3();
  robot.traverse(object => {
    if (isURDFVisual(object) && effectivelyVisible(object) &&
        /(?:foot|toe|sole|paw|wheel)/i.test(owningLinkName(object) ?? ''))
      feet.expandByObject(object);
  });
  if (!feet.isEmpty()) return feet;
  const fallback = overallVisualBounds(robot);
  return fallback;
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
// Match RViz/gz-math's equivalent uniform-density box: diagonalize the full
// symmetric inertia tensor, then express the box in the principal-axis frame.
function principalInertiaBox(row: PhysicsRow): { dimensions: Vec3Tuple; rotation: THREE.Quaternion } | null {
  const { ixx, ixy, ixz, iyy, iyz, izz } = row.inertia;
  const mass = row.mass;
  if (!(mass && mass > 0) || [ixx, ixy, ixz, iyy, iyz, izz].some(value => value === null)) return null;
  const a = [[ixx!, ixy!, ixz!], [ixy!, iyy!, iyz!], [ixz!, iyz!, izz!]];
  const vectors = [[1, 0, 0], [0, 1, 0], [0, 0, 1]];
  for (let iteration = 0; iteration < 32; iteration++) {
    let p = 0; let q = 1;
    for (const [i, j] of [[0, 1], [0, 2], [1, 2]])
      if (Math.abs(a[i][j]) > Math.abs(a[p][q])) { p = i; q = j; }
    if (Math.abs(a[p][q]) < 1e-14) break;
    const tau = (a[q][q] - a[p][p]) / (2 * a[p][q]);
    const tangent = (tau < 0 ? -1 : 1) / (Math.abs(tau) + Math.sqrt(1 + tau * tau));
    const cosine = 1 / Math.sqrt(1 + tangent * tangent);
    const sine = tangent * cosine;
    const off = a[p][q];
    a[p][p] -= tangent * off;
    a[q][q] += tangent * off;
    a[p][q] = a[q][p] = 0;
    for (let k = 0; k < 3; k++) {
      if (k !== p && k !== q) {
        const left = a[k][p]; const right = a[k][q];
        a[k][p] = a[p][k] = cosine * left - sine * right;
        a[k][q] = a[q][k] = sine * left + cosine * right;
      }
      const left = vectors[k][p]; const right = vectors[k][q];
      vectors[k][p] = cosine * left - sine * right;
      vectors[k][q] = sine * left + cosine * right;
    }
  }
  const moments = [a[0][0], a[1][1], a[2][2]];
  if (moments.some(value => !Number.isFinite(value) || value <= 0)) return null;
  const squared = [moments[1] + moments[2] - moments[0],
    moments[0] + moments[2] - moments[1], moments[0] + moments[1] - moments[2]]
    .map(value => 6 * value / mass);
  if (squared.some(value => !Number.isFinite(value) || value <= 0)) return null;
  const axes = [0, 1, 2].map(index => new THREE.Vector3(vectors[0][index], vectors[1][index], vectors[2][index]));
  if (new THREE.Vector3().crossVectors(axes[0], axes[1]).dot(axes[2]) < 0) axes[2].negate();
  return { dimensions: squared.map(Math.sqrt) as Vec3Tuple,
    rotation: new THREE.Quaternion().setFromRotationMatrix(new THREE.Matrix4().makeBasis(...axes as [THREE.Vector3, THREE.Vector3, THREE.Vector3])) };
}
function inertiaBox(row: PhysicsRow, link: THREE.Object3D): THREE.Mesh | null {
  const equivalent = principalInertiaBox(row);
  if (!equivalent) return null;
  // The imported mybot imu_link encodes a 1 cm sensor with an inertia equivalent
  // to a 0.775 m cube. Hide only this known placeholder sensor envelope.
  if (row.name === 'imu_link' && row.mass !== null && row.mass <= 0.001 &&
      equivalent.dimensions.every(size => size > 0.7)) return null;
  const marker = new THREE.Mesh(new THREE.BoxGeometry(1, 1, 1),
    new THREE.MeshBasicMaterial({ color: 0x268cf5, transparent: true, opacity: 0.18,
      depthWrite: false, side: THREE.DoubleSide }));
  marker.name = 'Equivalent inertia box: ' + row.name;
  marker.userData.urdfToolsInertia = true;
  marker.userData.linkName = row.name;
  marker.scale.set(...equivalent.dimensions);
  marker.position.set(...(row.comLocal ?? [0, 0, 0]));
  const inertialOrigin = directChild(directChild((link as THREE.Object3D & {urdfNode?: Element}).urdfNode ?? null,
    'inertial'), 'origin');
  const rpy = vectorAttribute(inertialOrigin, 'rpy');
  if (rpy) marker.rotation.set(rpy[0], rpy[1], rpy[2], 'ZYX');
  marker.quaternion.multiply(equivalent.rotation);
  marker.add(new THREE.LineSegments(new THREE.EdgesGeometry(new THREE.BoxGeometry(1, 1, 1)),
    new THREE.LineBasicMaterial({ color: 0x6db9ff, transparent: true, opacity: 0.7 })));
  link.add(marker);
  return marker;
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
function applyMeshMaterial(scene: THREE.Object3D, urdfMaterial: THREE.Material | null): THREE.Object3D {
  const color = (urdfMaterial as THREE.Material & { color?: THREE.Color } | null)?.color;
  if (!color) return scene;
  scene.traverse(object => {
    if (!(object instanceof THREE.Mesh)) return;
    const update = (source: THREE.Material): THREE.Material => {
      const meshMaterial = source as THREE.Material & { color?: THREE.Color; map?: THREE.Texture | null };
      if (meshMaterial.map || !meshMaterial.color) return source;
      const replacement = source.clone() as typeof meshMaterial;
      replacement.color = color.clone();
      return replacement;
    };
    object.material = Array.isArray(object.material) ? object.material.map(update) : update(object.material);
  });
  return scene;
}
function styleVisualMaterials(robot: URDFRobot, loadTextures: boolean): number {
  let litMeshes = 0;
  robot.traverse(object => {
    if (!(object instanceof THREE.Mesh)) return;
    let ancestor = object.parent;
    while (ancestor && !isURDFVisual(ancestor)) ancestor = ancestor.parent;
    if (!ancestor) return;
    const lit = (source: THREE.Material): THREE.Material => {
      if (source.userData.urdfToolsVisualStyle === true) return source;
      const visual = source as THREE.Material & { color?: THREE.Color; map?: THREE.Texture | null;
        vertexColors?: boolean; roughness?: number; metalness?: number };
      const color = visual.color?.clone() ?? new THREE.Color(0xffffff);
      // A textured DAE must not force unrelated untextured STL parts into unlit shading.
      if ((!loadTextures || !visual.map) && color.r > 0.9 && color.g > 0.9 && color.b > 0.9)
        color.setHex(0x747b83);
      // The desktop WebGL path renders lit Three.js materials nearly white on some
      // imported DAE/STL meshes. A basic material preserves the source texture;
      // untextured geometry receives stable per-face shading from its normals.
      const useMap = loadTextures && !!visual.map;
      let shadedVertices = visual.vertexColors === true;
      if (!useMap && !shadedVertices && object.geometry.getAttribute('normal')) {
        const normals = object.geometry.getAttribute('normal');
        const colors = new Float32Array(normals.count * 3);
        const light = new THREE.Vector3(0.42, -0.48, 0.77).normalize();
        for (let index = 0; index < normals.count; index++) {
          const facing = Math.max(0, normals.getX(index) * light.x +
            normals.getY(index) * light.y + normals.getZ(index) * light.z);
          const shade = 0.48 + 0.52 * facing;
          colors[index * 3] = colors[index * 3 + 1] = colors[index * 3 + 2] = shade;
        }
        if (!object.geometry.getAttribute('color'))
          object.geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3));
        shadedVertices = true;
      }
      const replacement = new THREE.MeshBasicMaterial({
        color,
        map: useMap ? visual.map : null,
        transparent: source.transparent,
        opacity: source.opacity,
        side: source.side,
        depthWrite: source.depthWrite,
        alphaTest: source.alphaTest,
        vertexColors: shadedVertices
      });
      replacement.name = source.name;
      replacement.userData.urdfToolsVisualStyle = true;
      return replacement;
    };
    object.material = Array.isArray(object.material) ? object.material.map(lit) : lit(object.material);
    object.castShadow = true;
    litMeshes++;
  });
  return litMeshes;
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

export function RobotViewer({ report, compareReports = [], textureEnabled = {}, showJointGizmos = false, onSelect, onSurfacePick, picking = false }: {
  report: RobotImport; compareReports?: CompareEntry[]; textureEnabled?: Record<string, boolean>; showJointGizmos?: boolean; onSelect?: (selected: NodeSelection) => void;
  onSurfacePick?: (point: SurfacePoint) => void; picking?: boolean;
}) {
  const pickCallback = useRef(onSurfacePick); pickCallback.current = onSurfacePick;
  const pickingRef = useRef(picking); pickingRef.current = picking;
  useEffect(() => { if (picking) { setGravityEnabled(false); setIsolatedLink(null); } }, [picking]);
  const host = useRef<HTMLDivElement>(null);
  const robotRef = useRef<URDFRobot | null>(null);
  const focusObjectRef = useRef<((selected: SelectedObject) => void) | null>(null);
  const resetViewRef = useRef<(() => void) | null>(null);
  const followGravityRef = useRef<((robot: URDFRobot) => void) | null>(null);
  const refreshModelAnalysisRef = useRef<((robot: URDFRobot) => void) | null>(null);
  const isolatedLinkRef = useRef<string | null>(null);
  const showComRef = useRef(true);
  const showInertiaRef = useRef(false);
  const showShadowsRef = useRef(true);
  const compareRobotsRef = useRef<URDFRobot[]>([]);
  const passiveModelsRef = useRef<PassiveRobot[]>([]);
  const preGravityPassiveRef = useRef<PassiveGravityPose[]>([]);
  const updateShadowRef = useRef<(() => void) | null>(null);
  const visualVisibleRef = useRef(true);
  const collisionVisibleRef = useRef(false);
  const selectedObjectRef = useRef<SelectedObject | null>(null);
  const gravityRef = useRef(false);
  const placeOnGroundRef = useRef<(() => void) | null>(null);
  const updateHighlightRef = useRef<(() => void) | null>(null);
  const gravityRequestRef = useRef(0);
  const gravityAnimationRef = useRef(0);
  const jointSettingsRef = useRef<Map<string, JointSetting>>(new Map());
  const preGravityPoseRef = useRef<GravityPose | null>(null);
  const [joints, setJoints] = useState<JointSetting[]>([]);
  const [linkTree, setLinkTree] = useState<LinkTreeNode[]>([]);
  const [physicsRows, setPhysicsRows] = useState<PhysicsRow[]>([]);
  const [error, setError] = useState('');
  const [assetsLoaded, setAssetsLoaded] = useState(false);
  const [meshCount, setMeshCount] = useState(0);
  const [meshFilesLoaded, setMeshFilesLoaded] = useState(0);
  const [textureCount, setTextureCount] = useState(0);
  const [litMeshCount, setLitMeshCount] = useState(0);
  const [angleUnit, setAngleUnit] = useState<'rad' | 'deg'>('rad');
  const [visualCount, setVisualCount] = useState(0);
  const [collisionCount, setCollisionCount] = useState(0);
  const [collisionStyledMeshCount, setCollisionStyledMeshCount] = useState(0);
  const [visibleVisualCount, setVisibleVisualCount] = useState(0);
  const [visibleCollisionCount, setVisibleCollisionCount] = useState(0);
  const [comMarkerCount, setComMarkerCount] = useState(0);
  const [visibleComMarkerCount, setVisibleComMarkerCount] = useState(0);
  const [inertiaMarkerCount, setInertiaMarkerCount] = useState(0);
  const [visibleInertiaMarkerCount, setVisibleInertiaMarkerCount] = useState(0);
  const [compareLoadedCount, setCompareLoadedCount] = useState(0);
  const [, setGroundRevision] = useState(0);
  const [compareVisibleVisualCount, setCompareVisibleVisualCount] = useState(0);
  const [compareVisibleCollisionCount, setCompareVisibleCollisionCount] = useState(0);
  const [overallBounds, setOverallBounds] = useState<Vec3Tuple | null>(null);
  const [selectedObject, setSelectedObject] = useState<SelectedObject | null>(null);
  const [selection, setSelection] = useState<SelectionInfo | null>(null);
  const [visualVisible, setVisualVisible] = useState(true);
  const [collisionVisible, setCollisionVisible] = useState(false);
  const [showComMarkers, setShowComMarkers] = useState(true);
  const [showInertiaMarkers, setShowInertiaMarkers] = useState(false);
  const [showShadows, setShowShadows] = useState(true);
  const [isolatedLink, setIsolatedLink] = useState<string | null>(null);
  const [screenshotReady, setScreenshotReady] = useState(false);
  const [screenshotMessage, setScreenshotMessage] = useState('');
  const [viewResetCount, setViewResetCount] = useState(0);
  const [jointRotation, setJointRotation] = useState('');
  const [jointGizmoCount, setJointGizmoCount] = useState(0);
  const [panels, setPanels] = useState({ display: true, structure: true, joints: true, physics: true, measure: true });
  const [gravityEnabled, setGravityEnabled] = useState(false);
  const [gravityMessage, setGravityMessage] = useState('');
  const [visualGroundMin, setVisualGroundMin] = useState<number | null>(null);
  visualVisibleRef.current = visualVisible;
  collisionVisibleRef.current = collisionVisible;
  isolatedLinkRef.current = isolatedLink;
  showComRef.current = showComMarkers;
  showInertiaRef.current = showInertiaMarkers;
  showShadowsRef.current = showShadows;
  selectedObjectRef.current = selectedObject;
  gravityRef.current = gravityEnabled;
  useEffect(() => { if (selectedObject) onSelect?.(selectedObject); }, [selectedObject, onSelect]);
  const selected = report.models.find(model => model.path === report.selected_model);
  const ready = report.status === 'ready' && selected?.status === 'ready';
  const currentModelId = `${report.operation_id}:${report.selected_model}`;
  const loadMainTextures = textureEnabled[currentModelId] ?? hasImageAssets(report);
  const comparisonKey = compareReports.map(entry => entry.id + ':' + entry.report.operation_id + ':' + entry.report.selected_model + ':' + String(textureEnabled[entry.id] ?? hasImageAssets(entry.report))).join('|');

  useEffect(() => {
    if (!ready || !selected || !host.current) return;
    let disposed = false;
    let raf = 0;
    let renderer: THREE.WebGLRenderer | undefined;
    let controls: OrbitControls | undefined;
    let onPointerDown: ((event: PointerEvent) => void) | undefined;
    let onPointerMove: ((event: PointerEvent) => void) | undefined;
    let onPointerUp: ((event: PointerEvent) => void) | undefined;
    let onPointerCancel: (() => void) | undefined;
    const jointMarkers = new Map<string, THREE.Mesh>();
    const inertiaMarkers = new Map<string, THREE.Mesh>();
    const passiveRobots: PassiveRobot[] = [];
    const textureBlobUrls: string[] = [];
    let floor: THREE.Mesh | undefined;
    let shadowFloor: THREE.Mesh | undefined;
    let linkOutline: THREE.Box3Helper | undefined;
    let jointAxisMarker: THREE.Group | undefined;
    let jointAxisRadius = 0.055;
    const owned: THREE.Object3D[] = [];
    const gizmos: THREE.AxesHelper[] = [];
    const element = host.current;
    robotRef.current = null;
    focusObjectRef.current = null;
    resetViewRef.current = null;
    followGravityRef.current = null;
    refreshModelAnalysisRef.current = null;
    setJoints([]);
    setCompareLoadedCount(0);
    setCompareVisibleVisualCount(0);
    setCompareVisibleCollisionCount(0);
    setInertiaMarkerCount(0);
    setVisibleInertiaMarkerCount(0);
    setAssetsLoaded(false);
    setLinkTree([]);
    setPhysicsRows([]);
    setMeshCount(0);
    setMeshFilesLoaded(0);
    setLitMeshCount(0);
    setTextureCount(0);
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
    setIsolatedLink(null);
    setScreenshotReady(false);
    setScreenshotMessage('');
    setViewResetCount(0);
    setGravityEnabled(false);
    setGravityMessage('');
    setVisualGroundMin(null);
    gravityRequestRef.current++;
    cancelAnimationFrame(gravityAnimationRef.current);
    preGravityPoseRef.current = null;
    preGravityPassiveRef.current = [];
    passiveModelsRef.current = [];
    setError('');
    try {
      const scene = new THREE.Scene();
      scene.background = new THREE.Color(0x252b32);
      const camera = new THREE.PerspectiveCamera(50, 1, 0.001, 1000);
      camera.up.set(0, 0, 1);
      camera.position.set(1.3, -1.5, 1.0);
      renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true });
      renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
      renderer.toneMapping = THREE.ACESFilmicToneMapping;
      renderer.toneMappingExposure = 0.72;
      renderer.shadowMap.enabled = true;
      renderer.shadowMap.type = THREE.PCFSoftShadowMap;
      element.appendChild(renderer.domElement);
      controls = new OrbitControls(camera, renderer.domElement);
      controls.enableDamping = true;
      const raycaster = new THREE.Raycaster();
      const pointer = new THREE.Vector2();
      const jointLimits = new Map<string, JointSetting>();
      jointSettingsRef.current = jointLimits;
      let press: { x: number; y: number; joint: string | null; value: number; dragged: boolean } | null = null;
      const pick = (event: PointerEvent) => {
        const bounds = renderer!.domElement.getBoundingClientRect();
        pointer.set((event.clientX - bounds.left) / bounds.width * 2 - 1,
          -(event.clientY - bounds.top) / bounds.height * 2 + 1);
        raycaster.setFromCamera(pointer, camera);
      };
      const select = (next: SelectedObject) => {
        selectedObjectRef.current = next;
        setSelectedObject(next);
        if (robotRef.current) setSelection(selectionInfo(robotRef.current, next));
        jointMarkers.forEach((marker, name) => (marker.material as THREE.MeshBasicMaterial).color.setHex(
          next.type === 'joint' && next.name === name ? 0xf34747 : 0xffbf56));
      };
      const applyJoint = (name: string, value: number) => {
        const current = robotRef.current;
        const limit = jointLimits.get(name);
        if (!current || !limit || gravityRef.current) return;
        const clamped = Math.max(limit.useLimit ? limit.min : limit.previewMin,
          Math.min(limit.useLimit ? limit.max : limit.previewMax, value));
        current.setJointValue(name, clamped);
        current.updateMatrixWorld(true);
        if (!gravityRef.current) placeOnGroundRef.current?.();
        setJointRotation(current.joints[name].quaternion.toArray().map(number => number.toFixed(6)).join(','));
        setJoints(old => old.map(joint => joint.name === name ? { ...joint, value: clamped } : joint));
        limit.value = clamped;
        refreshModelAnalysisRef.current?.(current);
        if (selectedObjectRef.current) setSelection(selectionInfo(current, selectedObjectRef.current));
      };
      onPointerDown = (event: PointerEvent) => {
        if (event.button !== 0 || !robotRef.current) return;
        pick(event);
        const markerHit = raycaster.intersectObjects(Array.from(jointMarkers.values()), false)[0];
        const joint = pickingRef.current ? undefined : markerHit?.object.userData.jointName as string | undefined;
        press = { x: event.clientX, y: event.clientY, joint: joint || null,
          value: joint ? jointLimits.get(joint)?.value || 0 : 0, dragged: false };
        if (joint) { select({ type: 'joint', name: joint });
          if (!gravityRef.current) { controls!.enabled = false; renderer!.domElement.setPointerCapture(event.pointerId); } }
      };
      onPointerMove = (event: PointerEvent) => {
        if (!press?.joint) return;
        const setting = jointLimits.get(press.joint);
        if (!setting) return;
        const delta = event.clientX - press.x;
        if (Math.abs(delta) > 3) press.dragged = true;
        if (press.dragged) applyJoint(press.joint, press.value + delta * (setting.unit === 'm' ? 0.002 : 0.01));
      };
      onPointerUp = (event: PointerEvent) => {
        if (!press || event.button !== 0) return;
        const moved = Math.hypot(event.clientX - press.x, event.clientY - press.y);
        const wasMarker = !!press.joint;
        press = null;
        controls!.enabled = true;
        if (renderer!.domElement.hasPointerCapture(event.pointerId)) renderer!.domElement.releasePointerCapture(event.pointerId);
        if (wasMarker || moved > 5 || !robotRef.current) return;
        pick(event);
        const hit = raycaster.intersectObject(robotRef.current, true).find(item =>
          item.object instanceof THREE.Mesh && effectivelyVisible(item.object));
        const link = hit && owningLinkName(hit.object);
        if (!link || !hit) return;
        if (pickingRef.current) {
          const frame = robotRef.current.links[link];
          const point = frame.worldToLocal(hit.point.clone());
          const normal = (hit.face?.normal.clone() || new THREE.Vector3(0,0,1))
            .applyNormalMatrix(new THREE.Matrix3().getNormalMatrix(hit.object.matrixWorld))
            .transformDirection(frame.matrixWorld.clone().invert());
          pickCallback.current?.({link, point:point.toArray(), normal:normal.toArray()});
          select({type:'link',name:link}); return;
        }
        const incoming = Object.entries(robotRef.current.joints).find(([, item]) =>
          directChild(item.urdfNode, 'child')?.getAttribute('link') === link && jointLimits.has(item.name));
        select(incoming ? { type: 'joint', name: incoming[0] } : { type: 'link', name: link });
      };
      renderer.domElement.addEventListener('pointerdown', onPointerDown);
      renderer.domElement.addEventListener('pointermove', onPointerMove);
      renderer.domElement.addEventListener('pointerup', onPointerUp);
      onPointerCancel = () => { press = null; if (controls) controls.enabled = true; };
      renderer.domElement.addEventListener('pointercancel', onPointerCancel);
      const grid = new THREE.GridHelper(10, 100, 0x6882a2, 0x354458);
      grid.rotation.x = Math.PI / 2;
      grid.position.z = 0.001;
      floor = new THREE.Mesh(new THREE.PlaneGeometry(200, 200),
        new THREE.MeshBasicMaterial({ color: 0x30363b, toneMapped: false }));
      floor.position.z = 0;
      floor.receiveShadow = false;
      shadowFloor = new THREE.Mesh(new THREE.PlaneGeometry(200, 200),
        new THREE.ShadowMaterial({ color: 0x000000, opacity: 0.48 }));
      shadowFloor.position.z = 0.0004;
      shadowFloor.receiveShadow = true;
      scene.add(floor, shadowFloor, grid, new THREE.AxesHelper(0.35), new THREE.HemisphereLight(0xffffff, 0x5c6470, 0.45));
      linkOutline = new THREE.Box3Helper(new THREE.Box3(), 0xf34747);
      linkOutline.visible = false;
      scene.add(linkOutline);
      // The marker lives in scene space so its mesh never changes the robot's
      // bounds or intercepts a click intended for a link or joint handle.
      jointAxisMarker = new THREE.Group();
      jointAxisMarker.name = 'Selected revolute joint axis';
      const axisRing = new THREE.Mesh(new THREE.TorusGeometry(1, 0.055, 10, 64),
        new THREE.MeshBasicMaterial({ color: 0xf34747, depthTest: false, depthWrite: false, toneMapped: false }));
      axisRing.name = 'Rotation axis ring';
      axisRing.renderOrder = 1100;
      const axisArrow = new THREE.ArrowHelper(new THREE.Vector3(0, 0, 1),
        new THREE.Vector3(0, 0, 0), 3, 0x219bff, 0.85, 0.45);
      axisArrow.name = 'Positive rotation axis';
      axisArrow.traverse(object => {
        object.renderOrder = 1101;
        if (object instanceof THREE.Mesh || object instanceof THREE.Line) {
          const materials = Array.isArray(object.material) ? object.material : [object.material];
          materials.forEach(material => { material.depthTest = false; material.depthWrite = false; });
        }
      });
      jointAxisMarker.add(axisRing, axisArrow);
      jointAxisMarker.visible = false;
      scene.add(jointAxisMarker);
      const axisOrigin = new THREE.Vector3();
      const axisDirection = new THREE.Vector3();
      const axisQuaternion = new THREE.Quaternion();
      const markerNormal = new THREE.Vector3(0, 0, 1);
      const updateJointAxisMarker = () => {
        const selectedNow = selectedObjectRef.current;
        const current = robotRef.current;
        const joint = selectedNow?.type === 'joint' ? current?.joints[selectedNow.name] : undefined;
        if (!jointAxisMarker || !joint || !['revolute', 'continuous'].includes(joint.jointType)) {
          if (jointAxisMarker) jointAxisMarker.visible = false;
          delete element.dataset.jointAxisName;
          delete element.dataset.jointAxisOrigin;
          delete element.dataset.jointAxisDirection;
          return;
        }
        joint.getWorldPosition(axisOrigin);
        joint.getWorldQuaternion(axisQuaternion);
        axisDirection.copy(joint.axis).applyQuaternion(axisQuaternion).normalize();
        if (axisDirection.lengthSq() < 0.5) {
          jointAxisMarker.visible = false;
          delete element.dataset.jointAxisName;
          delete element.dataset.jointAxisOrigin;
          delete element.dataset.jointAxisDirection;
          return;
        }
        jointAxisMarker.position.copy(axisOrigin);
        jointAxisMarker.quaternion.setFromUnitVectors(markerNormal, axisDirection);
        jointAxisMarker.scale.setScalar(jointAxisRadius);
        jointAxisMarker.visible = true;
        element.dataset.jointAxisName = joint.name;
        element.dataset.jointAxisOrigin = axisOrigin.toArray().map(value => value.toFixed(5)).join(',');
        element.dataset.jointAxisDirection = axisDirection.toArray().map(value => value.toFixed(5)).join(',');
      };
      const updateHighlight = () => {
        const selectedNow = selectedObjectRef.current;
        const current = robotRef.current;
        const link = selectedNow?.type === 'link' && current?.links[selectedNow.name];
        const bounds = link ? visualBoundsForLink(link) : null;
        if (linkOutline) {
          linkOutline.visible = !!bounds;
          if (bounds) linkOutline.box.copy(bounds);
        }
      };
      updateHighlightRef.current = updateHighlight;
      const sun = new THREE.DirectionalLight(0xffffff, 1.35);
      sun.position.set(3, -3, 6);
      sun.castShadow = true;
      sun.shadow.mapSize.set(2048, 2048);
      sun.shadow.bias = -0.0001;
      sun.shadow.normalBias = 0.006;
      sun.shadow.camera.left = -3; sun.shadow.camera.right = 3;
      sun.shadow.camera.top = 3; sun.shadow.camera.bottom = -3;
      scene.add(sun);
      updateShadowRef.current = () => {
        if (shadowFloor) shadowFloor.visible = showShadowsRef.current;
        sun.castShadow = showShadowsRef.current;
      };
      updateShadowRef.current();
      const comMarkers = new Map<string, THREE.Mesh>();
      let lastGroundSync = 0;
      const render = () => {
        if (disposed || !renderer || !controls) return;
        const now = performance.now();
        if (!gravityRef.current && passiveRobots.length && now - lastGroundSync > 200) {
          lastGroundSync = now;
          const models = [robotRef.current, ...passiveRobots.map(item => item.robot)]
            .filter((item): item is URDFRobot => !!item);
          const needsGrounding = models.some(item => {
            const bounds = overallVisualBounds(item);
            return bounds && Math.abs(bounds.min.z) > 0.005;
          });
          if (needsGrounding) {
            layoutComparison();
            setGroundRevision(revision => revision + 1);
          }
        }
        const width = Math.max(2, element.clientWidth);
        const height = Math.max(2, element.clientHeight);
        renderer.setSize(width, height, false);
        camera.aspect = width / height;
        camera.updateProjectionMatrix();
        controls.update();
        updateJointAxisMarker();
        renderer.render(scene, camera);
        raf = requestAnimationFrame(render);
      };
      render();
      const layoutComparison = () => {
        const all = [robotRef.current, ...passiveRobots.map(item => item.robot)].filter((item): item is URDFRobot => !!item);
        if (all.length < 2) return;
        const boxes = all.map(item => overallVisualBounds(item));
        const widths = boxes.map(box => box?.getSize(new THREE.Vector3()).x ?? 0.4);
        const gap = 0.36;
        let cursor = -(widths.reduce((sum, width) => sum + width, 0) + gap * (all.length - 1)) / 2;
        all.forEach((item, index) => {
          const box = boxes[index];
          if (box) item.position.x += cursor + widths[index] / 2 - box.getCenter(new THREE.Vector3()).x;
          item.updateMatrixWorld(true);
          const grounded = overallVisualBounds(item);
          if (grounded && Number.isFinite(grounded.min.z)) item.position.z -= grounded.min.z;
          item.updateMatrixWorld(true);
          cursor += widths[index] + gap;
        });
      };
      const fitView = (currentRobot: URDFRobot) => {
        if (!controls) return;
        currentRobot.updateMatrixWorld(true);
        const box = overallVisualBounds(currentRobot) ?? new THREE.Box3().setFromObject(currentRobot);
        for (const passive of passiveRobots) {
          const extra = overallVisualBounds(passive.robot);
          if (extra) box.union(extra);
        }
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
        camera.position.copy(center).add(new THREE.Vector3(radius * 1.5, -radius * 1.5, radius * 1.2));
        camera.near = Math.max(0.001, radius / 1000);
        camera.far = Math.max(20, radius * 100);
        camera.updateProjectionMatrix();
        controls.target.copy(center);
        controls.update();
      };
      followGravityRef.current = currentRobot => {
        if (!controls) return;
        const bounds = overallVisualBounds(currentRobot);
        if (!bounds) return;
        const centerZ = bounds.getCenter(new THREE.Vector3()).z;
        const delta = (centerZ - controls.target.z) * 0.12;
        camera.position.z += delta;
        controls.target.z += delta;
        controls.update();
      };
      const placeOnGround = () => {
        const current = robotRef.current;
        if (!current || gravityRef.current) return;
        current.updateMatrixWorld(true);
        const box = overallVisualBounds(current);
        if (box && Number.isFinite(box.min.z)) {
          current.position.z -= box.min.z;
          current.updateMatrixWorld(true);
        }
      };
      placeOnGroundRef.current = placeOnGround;
      const refreshAnalysis = (currentRobot: URDFRobot) => {
        if (disposed) return;
        placeOnGround();
        currentRobot.updateMatrixWorld(true);
        setLitMeshCount(styleVisualMaterials(currentRobot, loadMainTextures));
        setCollisionStyledMeshCount(styleCollisionMeshes(currentRobot));
        const rows = readPhysicsRows(currentRobot);
        setPhysicsRows(rows);
        const bounds = overallVisualBounds(currentRobot);
        setOverallBounds(bounds ? tuple(bounds.getSize(new THREE.Vector3())) : null);
        jointAxisRadius = THREE.MathUtils.clamp((bounds?.getSize(new THREE.Vector3()).length() ?? 0.6) * 0.055, 0.035, 0.13);
        setMeshCount(visibleMeshCount(currentRobot));
        let mapped = 0;
        currentRobot.traverse(object => { if (object instanceof THREE.Mesh && !isURDFCollider(object.parent || object)) {
          const materials = Array.isArray(object.material) ? object.material : [object.material];
          if (materials.some(material => 'map' in material && material.map)) mapped++;
        } });
        setTextureCount(mapped);
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
            currentRobot.links[row.name].add(marker);
          }
          const point = row.comLocal as Vec3Tuple;
          marker.position.set(point[0], point[1], point[2]);
          marker.visible = showComRef.current && (!isolatedLinkRef.current || isolatedLinkRef.current === row.name);
        }
        for (const row of rows) {
          let marker = inertiaMarkers.get(row.name);
          if (!marker) {
            marker = inertiaBox(row, currentRobot.links[row.name]) ?? undefined;
            if (marker) inertiaMarkers.set(row.name, marker);
          }
          if (marker) marker.visible = showInertiaRef.current &&
            (!isolatedLinkRef.current || isolatedLinkRef.current === row.name);
        }
        let passiveInertiaCount = 0;
        let passiveVisibleInertia = 0;
        for (const item of passiveRobots) item.robot.traverse(object => {
          if (object.userData.urdfToolsInertia === true) {
            passiveInertiaCount++;
            if (object.visible) passiveVisibleInertia++;
          }
        });
        setInertiaMarkerCount(inertiaMarkers.size + passiveInertiaCount);
        setVisibleInertiaMarkerCount(Array.from(inertiaMarkers.values()).filter(marker => marker.visible).length + passiveVisibleInertia);
        for (const [name, marker] of comMarkers) {
          if (knownComNames.has(name)) continue;
          marker.removeFromParent();
          marker.geometry.dispose();
          const materials = Array.isArray(marker.material) ? marker.material : [marker.material];
          materials.forEach(material => material.dispose());
          comMarkers.delete(name);
        }
        setComMarkerCount(comMarkers.size);
        let passiveComCount = 0;
        for (const item of passiveRobots) item.robot.traverse(object => {
          if (object.userData.urdfToolsCom === true && object.visible) passiveComCount++;
        });
        setVisibleComMarkerCount(Array.from(comMarkers.values()).filter(marker => marker.visible).length + passiveComCount);
        updateHighlight();
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
      manager.onLoad = () => queueMicrotask(recount);
      manager.onError = url => { if (!disposed) setError('网格加载失败：' + url); };
      const loader = new URDFLoader(manager);
      loader.parseCollision = true;
      loader.packages = Object.fromEntries(Object.entries(report.package_map).flatMap(([name, dirs]) =>
        dirs.length === 1 ? [[name, assetUrl(report.operation_id, dirs[0])]] : []));
      // Resolve each URI against the import manifest before handing it to a model loader.
      // COLLADA resolves its own image paths; give it the canonical mesh directory.
      const resources = new Map(selected.resources.filter(item => item.path).map(item => [
        new URL(assetUrl(report.operation_id, selected.path.replace(/[^/]+$/, '') + item.uri)).href,
        assetUrl(report.operation_id, item.path!)
      ]));
      const defaultMeshLoader = loader.loadMeshCb.bind(loader);
      const daeCache = new Map<string, Promise<THREE.Object3D>>();
      loader.loadMeshCb = (url, manager, material, complete) => {
        const canonical = resources.get(new URL(url).href) || new URL(url).href;
        const done = (object: THREE.Object3D | null, cause?: Error) => {
          if (cause || !object) {
            if (!disposed) setError('网格无法显示：' + canonical + (cause ? ' · ' + cause.message : ''));
            complete(null as unknown as THREE.Object3D, cause || new Error('Empty mesh'));
            return;
          }
          if (!disposed) setMeshFilesLoaded(count => count + 1);
          complete(object);
        };
        if (/\.dae(?:\?|$)/i.test(canonical)) {
          let shared = daeCache.get(canonical);
          if (!shared) {
            const directory = canonical.slice(0, canonical.lastIndexOf('/') + 1);
            shared = new Promise<THREE.Object3D>((resolve, reject) => {
              new ColladaLoader(manager).setResourcePath(directory).load(canonical, dae => {
                let count = 0;
                dae.scene.traverse(child => { if (child instanceof THREE.Mesh) count++; });
                if (count) resolve(dae.scene);
                else reject(new Error('DAE contains no renderable mesh'));
              }, undefined, cause => reject(cause instanceof Error ? cause : new Error(String(cause))));
            });
            daeCache.set(canonical, shared);
          }
          void shared.then(scene => done(applyMeshMaterial(scene.clone(true), material)), cause =>
            done(null, cause instanceof Error ? cause : new Error(String(cause))));
        } else if (/\.obj(?:\?|$)/i.test(canonical)) {
          new OBJLoader(manager).load(canonical, object => { object.traverse(child => {
            if (child instanceof THREE.Mesh && material) child.material = material;
          }); done(object); }, undefined, cause => done(null, cause instanceof Error ? cause : new Error(String(cause))));
        } else {
          defaultMeshLoader(canonical, manager, material, done);
        }
      };
      // ImageLoader can fail on a custom protocol even when fetch() succeeds. Convert
      // verified imported images to local blob URLs before COLLADA asks for them.
      const imageAssets = loadMainTextures ? (report.assets || []).filter(asset => /\.(png|jpe?g|bmp|webp)$/i.test(asset.path)) : [];
      void Promise.allSettled(imageAssets.map(async asset => {
        const source = assetUrl(report.operation_id, asset.path);
        const response = await fetch(source);
        if (!response.ok) throw new Error(`${asset.path}: HTTP ${response.status}`);
        const data = await response.blob();
        if (data.size !== asset.size) throw new Error(`${asset.path}: 文件大小与导入记录不符`);
        const local = URL.createObjectURL(data);
        if (disposed) { URL.revokeObjectURL(local); return [new URL(source).href, ''] as const; }
        textureBlobUrls.push(local);
        return [new URL(source).href, local] as const;
      })).then(results => {
        if (disposed) return;
        const replacements = new Map<string, string>();
        for (const result of results) {
          if (result.status === 'fulfilled') replacements.set(...result.value);
          else setError('贴图读取失败：' + String(result.reason));
        }
        manager.setURLModifier(url => {
          if (!loadMainTextures && /\.(png|jpe?g|bmp|webp)(?:[?#]|$)/i.test(url))
            return 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4////fwAJ+wP9j6a6YQAAAABJRU5ErkJggg==';
          try { return replacements.get(new URL(url).href) || url; }
          catch { return url; }
        });
        loader.load(assetUrl(report.operation_id, selected.path), robot => {
        if (disposed) return;
        robotRef.current = robot;
        owned.push(robot);
        scene.add(robot);
        robot.traverse(object => { if (object instanceof THREE.Mesh && !isURDFCollider(object.parent || object)) object.castShadow = true; });
        if (showJointGizmos) for (const [name, joint] of Object.entries(robot.joints)) {
          const axes = new THREE.AxesHelper(0.08);
          axes.name = `Joint gizmo: ${name}`;
          joint.add(axes); gizmos.push(axes);
        }
        setJointGizmoCount(gizmos.length);
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
          const min = finite ? joint.limit.lower : linear ? -0.5 : -Math.PI;
          const max = finite ? joint.limit.upper : linear ? 0.5 : Math.PI;
          return { name, kind: joint.jointType, value: finite ? Math.max(min, Math.min(max, 0)) : 0, min, max,
            previewMin: Math.min(min, linear ? -1 : -2 * Math.PI),
            previewMax: Math.max(max, linear ? 1 : 2 * Math.PI),
            hasLimit: finite, useLimit: finite, unit: linear ? 'm' : 'rad' };
        });
        loaded.forEach(setting => {
          jointLimits.set(setting.name, setting);
          const joint = robot.joints[setting.name];
          robot.setJointValue(setting.name, setting.value);
          const marker = new THREE.Mesh(new THREE.SphereGeometry(0.022, 14, 10),
            new THREE.MeshBasicMaterial({ color: 0xffbf56, depthTest: false }));
          marker.userData.jointName = setting.name;
          marker.renderOrder = 1001;
          joint.add(marker);
          jointMarkers.set(setting.name, marker);
        });
        setJoints(loaded);
        setLinkTree(buildLinkTree(robot));
        const counts = applyVisibility(robot, visualVisibleRef.current, collisionVisibleRef.current, isolatedLinkRef.current);
        setVisualCount(counts.visualCount);
        setCollisionCount(counts.collisionCount);
        setVisibleVisualCount(counts.visibleVisualCount);
        setVisibleCollisionCount(counts.visibleCollisionCount);
        refreshAnalysis(robot);
        layoutComparison();
        resetViewRef.current?.();
      }, undefined, cause => { if (!disposed) setError('URDF 加载失败：' + String(cause)); });
      }).catch(cause => { if (!disposed) setError('模型显示失败：' + String(cause)); });
      for (const entry of compareReports) {
        const other = entry.report.models.find(model => model.path === entry.report.selected_model);
        if (entry.report.status !== 'ready' || other?.status !== 'ready') continue;
        const otherManager = new THREE.LoadingManager();
        const otherLoader = new URDFLoader(otherManager);
        otherLoader.parseCollision = true;
        otherLoader.packages = Object.fromEntries(Object.entries(entry.report.package_map).flatMap(([name, dirs]) =>
          dirs.length === 1 ? [[name, assetUrl(entry.report.operation_id, dirs[0])]] : []));
        const otherResources = new Map(other.resources.filter(item => item.path).map(item => [
          new URL(assetUrl(entry.report.operation_id, other.path.replace(/[^/]+$/, '') + item.uri)).href,
          assetUrl(entry.report.operation_id, item.path!)
        ]));
        const defaultOtherMesh = otherLoader.loadMeshCb.bind(otherLoader);
        const otherDaeCache = new Map<string, Promise<THREE.Object3D>>();
        otherLoader.loadMeshCb = (url, assetManager, material, complete) => {
          const canonical = otherResources.get(new URL(url).href) || new URL(url).href;
          const done = (object: THREE.Object3D | null, cause?: Error) => {
            if (cause || !object) {
              if (!disposed) setError(`对比模型 ${other.name || other.path} 的网格加载失败：${canonical}`);
              complete(null as unknown as THREE.Object3D, cause || new Error('Empty mesh'));
            } else complete(object);
          };
          if (/\.dae(?:\?|$)/i.test(canonical)) {
            let shared = otherDaeCache.get(canonical);
            if (!shared) {
              const directory = canonical.slice(0, canonical.lastIndexOf('/') + 1);
              shared = new Promise<THREE.Object3D>((resolve, reject) =>
                new ColladaLoader(assetManager).setResourcePath(directory).load(canonical, dae => resolve(dae.scene),
                  undefined, cause => reject(cause instanceof Error ? cause : new Error(String(cause)))));
              otherDaeCache.set(canonical, shared);
            }
            void shared.then(scene => done(applyMeshMaterial(scene.clone(true), material)), cause => done(null, cause));
          } else if (/\.obj(?:\?|$)/i.test(canonical)) {
            new OBJLoader(assetManager).load(canonical, object => {
              object.traverse(child => { if (child instanceof THREE.Mesh && material) child.material = material; });
              done(object);
            }, undefined, cause => done(null, cause instanceof Error ? cause : new Error(String(cause))));
          } else defaultOtherMesh(canonical, assetManager, material, done);
        };
        let otherRobot: URDFRobot | null = null;
        let finalized = false;
        otherManager.onError = url => { if (!disposed) setError(`对比模型资源加载失败：${url}`); };
        otherManager.onLoad = () => queueMicrotask(() => {
          if (disposed || finalized || !otherRobot) return;
          finalized = true;
          const robot = otherRobot;
          styleVisualMaterials(robot, textureEnabled[entry.id] ?? hasImageAssets(entry.report));
          styleCollisionMeshes(robot);
          // URDFLoader can attach passive meshes after LoadingManager's first onLoad.
          // Refresh their material once the asynchronous mesh callbacks have settled.
          for (const delay of [250, 1000]) window.setTimeout(() => {
            if (!disposed) {
              styleVisualMaterials(robot, textureEnabled[entry.id] ?? hasImageAssets(entry.report));
              layoutComparison();
            }
          }, delay);
          const rows = readPhysicsRows(robot);
          for (const row of rows) {
            const link = robot.links[row.name];
            if (!link) continue;
            if (row.comLocal) {
              const marker = new THREE.Mesh(new THREE.SphereGeometry(0.012, 16, 12),
                new THREE.MeshBasicMaterial({ color: 0xffc857, depthTest: false, depthWrite: false }));
              marker.position.set(...row.comLocal);
              marker.userData.urdfToolsCom = true;
              marker.visible = showComRef.current;
              link.add(marker);
            }
            const inertia = inertiaBox(row, link);
            if (inertia) inertia.visible = showInertiaRef.current;
          }
          applyVisibility(robot, visualVisibleRef.current, collisionVisibleRef.current, null);
          robot.updateMatrixWorld(true);
          passiveRobots.push({ id: entry.id, robot, report: entry.report });
          passiveModelsRef.current = [...passiveRobots];
          compareRobotsRef.current = passiveRobots.map(item => item.robot);
          layoutComparison();
          setCompareLoadedCount(passiveRobots.length);
          setCompareVisibleVisualCount(passiveRobots.reduce((sum, item) =>
            sum + markedObjects(item.robot, isURDFVisual).filter(object => object.visible).length, 0));
          setCompareVisibleCollisionCount(passiveRobots.reduce((sum, item) =>
            sum + markedObjects(item.robot, isURDFCollider).filter(object => object.visible).length, 0));
          if (robotRef.current) refreshAnalysis(robotRef.current);
          resetViewRef.current?.();
        });
        const images = (textureEnabled[entry.id] ?? hasImageAssets(entry.report)) ? (entry.report.assets || []).filter(asset => /\.(png|jpe?g|bmp|webp)$/i.test(asset.path)) : [];
        void Promise.allSettled(images.map(async asset => {
          const source = assetUrl(entry.report.operation_id, asset.path);
          const response = await fetch(source);
          if (!response.ok) throw new Error(`${asset.path}: HTTP ${response.status}`);
          const data = await response.blob();
          if (data.size !== asset.size) throw new Error(`${asset.path}: 贴图大小不符`);
          const local = URL.createObjectURL(data);
          if (disposed) { URL.revokeObjectURL(local); return [new URL(source).href, ''] as const; }
          textureBlobUrls.push(local);
          return [new URL(source).href, local] as const;
        })).then(results => {
          if (disposed) return;
          const replacements = new Map<string, string>();
          for (const result of results) {
            if (result.status === 'fulfilled') replacements.set(...result.value);
            else setError('对比模型贴图读取失败：' + String(result.reason));
          }
          otherManager.setURLModifier(url => {
            if (!(textureEnabled[entry.id] ?? hasImageAssets(entry.report)) && /\.(png|jpe?g|bmp|webp)(?:[?#]|$)/i.test(url))
              return 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4////fwAJ+wP9j6a6YQAAAABJRU5ErkJggg==';
            try { return replacements.get(new URL(url).href) || url; }
            catch { return url; }
          });
          otherLoader.load(assetUrl(entry.report.operation_id, other.path), robot => {
            if (disposed) return;
            otherRobot = robot;
            owned.push(robot);
            scene.add(robot);
          }, undefined, cause => { if (!disposed) setError(`对比模型 ${other.name || other.path} 加载失败：${String(cause)}`); });
        }).catch(cause => { if (!disposed) setError('对比模型显示失败：' + String(cause)); });
      }
    } catch (cause) {
      setError('三维渲染不可用：' + String(cause));
    }
    return () => {
      disposed = true;
      ++gravityRequestRef.current;
      cancelAnimationFrame(gravityAnimationRef.current);
      cancelAnimationFrame(raf);
      controls?.dispose();
      if (onPointerDown) renderer?.domElement.removeEventListener('pointerdown', onPointerDown);
      if (onPointerMove) renderer?.domElement.removeEventListener('pointermove', onPointerMove);
      if (onPointerUp) renderer?.domElement.removeEventListener('pointerup', onPointerUp);
      if (onPointerCancel) renderer?.domElement.removeEventListener('pointercancel', onPointerCancel);
      focusObjectRef.current = null;
      resetViewRef.current = null;
      followGravityRef.current = null;
      refreshModelAnalysisRef.current = null;
      placeOnGroundRef.current = null;
      updateHighlightRef.current = null;
      updateShadowRef.current = null;
      compareRobotsRef.current = [];
      passiveModelsRef.current = [];
      preGravityPassiveRef.current = [];
      linkOutline?.geometry.dispose(); if (linkOutline) (linkOutline.material as THREE.Material).dispose();
      jointAxisMarker?.traverse(object => {
        if (object instanceof THREE.Mesh || object instanceof THREE.Line) {
          object.geometry.dispose();
          const materials = Array.isArray(object.material) ? object.material : [object.material];
          materials.forEach(material => material.dispose());
        }
      });
      jointMarkers.forEach(marker => { marker.geometry.dispose(); (marker.material as THREE.Material).dispose(); });
      floor?.geometry.dispose(); if (floor) (floor.material as THREE.Material).dispose();
      shadowFloor?.geometry.dispose(); if (shadowFloor) (shadowFloor.material as THREE.Material).dispose();
      textureBlobUrls.forEach(url => URL.revokeObjectURL(url));
      for (const axes of gizmos) { axes.removeFromParent(); axes.geometry.dispose();
        const materials = Array.isArray(axes.material) ? axes.material : [axes.material];
        materials.forEach(material => material.dispose()); }
      for (const root of owned) root.traverse(object => {
        if (object instanceof THREE.Mesh || object instanceof THREE.LineSegments) {
          object.geometry?.dispose();
          const materials = Array.isArray(object.material) ? object.material : [object.material];
          materials.forEach(material => material?.dispose());
        }
      });
      renderer?.dispose();
      renderer?.domElement.remove();
      robotRef.current = null;
    };
  }, [report.operation_id, report.selected_model, ready, showJointGizmos, comparisonKey, loadMainTextures]);

  useEffect(() => {
    const robot = robotRef.current;
    if (!robot) return;
    const counts = applyVisibility(robot, visualVisible, collisionVisible, isolatedLink);
    let otherVisuals = 0;
    let otherCollisions = 0;
    for (const other of compareRobotsRef.current) {
      const otherCounts = applyVisibility(other, visualVisible, collisionVisible, null);
      otherVisuals += otherCounts.visibleVisualCount;
      otherCollisions += otherCounts.visibleCollisionCount;
      other.traverse(object => {
        if (object.userData.urdfToolsCom === true) object.visible = showComMarkers;
        if (object.userData.urdfToolsInertia === true) object.visible = showInertiaMarkers;
      });
    }
    updateShadowRef.current?.();
    setCompareVisibleVisualCount(otherVisuals);
    setCompareVisibleCollisionCount(otherCollisions);
    setVisualCount(counts.visualCount);
    setCollisionCount(counts.collisionCount);
    setVisibleVisualCount(counts.visibleVisualCount);
    setVisibleCollisionCount(counts.visibleCollisionCount);
    refreshModelAnalysisRef.current?.(robot);
  }, [visualVisible, collisionVisible, isolatedLink, showComMarkers, showInertiaMarkers, showShadows]);

  useEffect(() => {
    robotRef.current?.traverse(object => {
      if (object instanceof THREE.Mesh && typeof object.userData.jointName === 'string') {
        (object.material as THREE.MeshBasicMaterial).color.setHex(selectedObject?.type === 'joint' &&
          selectedObject.name === object.userData.jointName ? 0xf34747 : 0xffbf56);
      }
    });
    updateHighlightRef.current?.();
  }, [selectedObject]);

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
    if (!robot || !Number.isFinite(value) || gravityRef.current) return;
    const setting = joints.find(joint => joint.name === name);
    if (!setting || value < (setting.useLimit ? setting.min : setting.previewMin) ||
        value > (setting.useLimit ? setting.max : setting.previewMax)) return;
    robot.setJointValue(name, value);
    robot.updateMatrixWorld(true);
    if (!gravityRef.current) placeOnGroundRef.current?.();
    setJointRotation(robot.joints[name].quaternion.toArray().map(number => number.toFixed(6)).join(','));
    setJoints(old => old.map(joint => joint.name === name ? { ...joint, value } : joint));
    setSelectedObject({ type: 'joint', name });
    refreshModelAnalysisRef.current?.(robot);
    setSelection(selectionInfo(robot, { type: 'joint', name }));
  }
  function toggleJointLimit(name: string, enabled: boolean) {
    const setting = jointSettingsRef.current.get(name);
    const robot = robotRef.current;
    if (!setting || !setting.hasLimit || !robot?.joints[name] || gravityRef.current) return;
    setting.useLimit = enabled;
    robot.joints[name].ignoreLimits = !enabled;
    if (enabled) {
      setting.value = Math.max(setting.min, Math.min(setting.max, setting.value));
      robot.setJointValue(name, setting.value);
      robot.updateMatrixWorld(true);
      placeOnGroundRef.current?.();
      refreshModelAnalysisRef.current?.(robot);
    }
    setJoints(old => old.map(joint => joint.name === name ? { ...joint, useLimit: enabled, value: setting.value } : joint));
  }
  function toggleAllJointLimits() {
    const robot = robotRef.current;
    if (!robot || gravityRef.current) return;
    const eligible = joints.filter(joint => joint.hasLimit);
    if (!eligible.length) return;
    const enabled = !eligible.every(joint => joint.useLimit);
    for (const setting of jointSettingsRef.current.values()) {
      if (!setting.hasLimit || !robot.joints[setting.name]) continue;
      setting.useLimit = enabled;
      robot.joints[setting.name].ignoreLimits = !enabled;
      if (enabled) {
        setting.value = Math.max(setting.min, Math.min(setting.max, setting.value));
        robot.setJointValue(setting.name, setting.value);
      }
    }
    robot.updateMatrixWorld(true);
    placeOnGroundRef.current?.();
    setJoints(old => old.map(joint => {
      const setting = jointSettingsRef.current.get(joint.name);
      return setting?.hasLimit ? { ...joint, useLimit: enabled, value: setting.value } : joint;
    }));
    refreshModelAnalysisRef.current?.(robot);
    if (selectedObjectRef.current) setSelection(selectionInfo(robot, selectedObjectRef.current));
  }
  async function toggleGravity(enabled: boolean) {
    const robot = robotRef.current;
    if (!robot || !selected) return;
    const ticket = ++gravityRequestRef.current;
    cancelAnimationFrame(gravityAnimationRef.current);
    if (!enabled) {
      gravityRef.current = false;
      setGravityEnabled(false);
      setVisualGroundMin(null);
      const saved = preGravityPoseRef.current;
      if (saved) {
        robot.position.copy(saved.position);
        robot.quaternion.copy(saved.quaternion);
        for (const [name, value] of Object.entries(saved.joints)) robot.setJointValue(name, value);
        setJoints(old => old.map(joint => ({ ...joint, value: saved.joints[joint.name] ?? joint.value })));
      }
      preGravityPoseRef.current = null;
      for (const savedPassive of preGravityPassiveRef.current) {
        savedPassive.robot.position.copy(savedPassive.position);
        savedPassive.robot.quaternion.copy(savedPassive.quaternion);
        for (const [name, value] of Object.entries(savedPassive.joints))
          savedPassive.robot.setJointValue(name, value);
        savedPassive.robot.updateMatrixWorld(true);
      }
      preGravityPassiveRef.current = [];
      placeOnGroundRef.current?.();
      refreshModelAnalysisRef.current?.(robot);
      resetViewRef.current?.();
      setGravityMessage('已恢复重力前的关节姿态，脚底贴地。');
      return;
    }
    if (!window.urdftools?.viewerSettle) {
      setGravityMessage('桌面物理计算不可用。');
      return;
    }
    const pose = Object.fromEntries(joints.map(joint => [joint.name, Number(robot.joints[joint.name]?.jointValue[0] ?? joint.value)]));
    const limits = Object.fromEntries(joints.map(joint => [joint.name, jointSettingsRef.current.get(joint.name)?.useLimit ?? true]));
    preGravityPoseRef.current = { position: robot.position.clone(), quaternion: robot.quaternion.clone(), joints: pose };
    preGravityPassiveRef.current = passiveModelsRef.current.map(({ robot: other }) => ({
      robot: other, position: other.position.clone(), quaternion: other.quaternion.clone(),
      joints: Object.fromEntries(Object.entries(other.joints).filter(([, joint]) =>
        ['revolute', 'continuous', 'prismatic'].includes(joint.jointType)).map(([name, joint]) =>
        [name, Number(joint.jointValue[0] ?? 0)])),
    }));
    gravityRef.current = true;
    setGravityEnabled(true);
    setGravityMessage('正在用 MuJoCo 计算无驱动重力下沉…');
    try {
      const result = await window.urdftools.viewerSettle(report.operation_id, selected.path, pose, limits);
      if (ticket !== gravityRequestRef.current || robotRef.current !== robot) return;
      if ((result.ground_contacts < 1 && result.ground_clearance > 0.002) ||
          result.position.some(value => !Number.isFinite(value)) ||
          result.quaternion_wxyz.some(value => !Number.isFinite(value)))
        throw new Error('物理地面未与机器人碰撞，姿态未应用');
      const missing = joints.filter(joint => !(joint.name in result.joints));
      if (missing.length) throw new Error('仿真没有返回全部活动关节：' + missing.map(joint => joint.name).join(', '));
      if (!Array.isArray(result.frames) || result.frames.length < 2 ||
          result.frames.some(frame => !Number.isFinite(frame.time) || frame.position.length !== 3 ||
            frame.quaternion_wxyz.length !== 4 || [...frame.position, ...frame.quaternion_wxyz,
              ...Object.values(frame.joints)].some(value => !Number.isFinite(value))))
        throw new Error('仿真没有返回有效的逐帧轨迹');
      const passiveResults: { robot: URDFRobot; result: GravityResult; offset: THREE.Vector3; index: number }[] = [];
      for (const item of passiveModelsRef.current) {
        const model = item.report.selected_model;
        if (!model) throw new Error(`对比模型 ${item.id} 没有可仿真的 URDF`);
        const saved = preGravityPassiveRef.current.find(entry => entry.robot === item.robot);
        if (!saved) continue;
        setGravityMessage(`正在计算 ${passiveResults.length + 2} / ${passiveModelsRef.current.length + 1} 个模型的重力轨迹…`);
        const otherLimits = Object.fromEntries(Object.keys(saved.joints).map(name =>
          [name, !item.robot.joints[name]?.ignoreLimits]));
        const otherResult = await window.urdftools.viewerSettle(item.report.operation_id, model, saved.joints, otherLimits);
        if (ticket !== gravityRequestRef.current || robotRef.current !== robot) return;
        if (!Array.isArray(otherResult.frames) || otherResult.frames.length < 2 ||
            otherResult.frames.some(frame => !Number.isFinite(frame.time) || frame.position.length !== 3 ||
              frame.quaternion_wxyz.length !== 4 || [...frame.position, ...frame.quaternion_wxyz,
                ...Object.values(frame.joints)].some(value => !Number.isFinite(value))) ||
            (otherResult.ground_contacts < 1 && otherResult.ground_clearance > 0.002))
          throw new Error(`对比模型 ${item.id} 的重力轨迹无效或未接触地面`);
        passiveResults.push({ robot: item.robot, result: otherResult,
          offset: saved.position.clone().sub(new THREE.Vector3(...(otherResult.frames[0].position as Vec3Tuple))), index: 0 });
      }
      const frames = result.frames;
      const duration = Math.max(frames[frames.length - 1].time,
        ...passiveResults.map(item => item.result.frames[item.result.frames.length - 1].time));
      const comparisonOffset = preGravityPoseRef.current!.position.clone()
        .sub(new THREE.Vector3(...(frames[0].position as Vec3Tuple)));
      const applyFrame = (target: URDFRobot, trajectory: GravityResult['frames'], elapsed: number,
        offset: THREE.Vector3, frameIndex: number): number => {
        while (frameIndex < trajectory.length - 2 && trajectory[frameIndex + 1].time < elapsed) frameIndex++;
        const from = trajectory[frameIndex];
        const to = trajectory[Math.min(frameIndex + 1, trajectory.length - 1)];
        const ratio = to.time > from.time ? Math.max(0, Math.min(1, (elapsed - from.time) / (to.time - from.time))) : 1;
        target.position.set(...(from.position.map((value, axis) =>
          value + (to.position[axis] - value) * ratio) as Vec3Tuple)).add(offset);
        const a = new THREE.Quaternion(from.quaternion_wxyz[1], from.quaternion_wxyz[2],
          from.quaternion_wxyz[3], from.quaternion_wxyz[0]);
        const b = new THREE.Quaternion(to.quaternion_wxyz[1], to.quaternion_wxyz[2],
          to.quaternion_wxyz[3], to.quaternion_wxyz[0]);
        target.quaternion.copy(a.slerp(b, ratio));
        for (const name of Object.keys(from.joints)) {
          if (target.joints[name] && name in to.joints)
            target.setJointValue(name, from.joints[name] + (to.joints[name] - from.joints[name]) * ratio);
        }
        target.updateMatrixWorld(true);
        const support = gravitySupportBounds(target);
        if (support && Number.isFinite(support.min.z)) {
          const adjustment = 0.001 - support.min.z;
          if (Math.abs(adjustment) > 1e-6) {
            target.position.z += adjustment;
            target.updateMatrixWorld(true);
            maxGroundAdjustment = Math.max(maxGroundAdjustment, Math.abs(adjustment));
          }
          if (target === robot && (performance.now() - lastUi > 120 || elapsed >= duration))
            setVisualGroundMin(support.min.z + adjustment);
        }
        return frameIndex;
      };
      const playbackRate = 2 / 3;
      let maxGroundAdjustment = 0;
      let started: number | null = null;
      let index = 0;
      let lastUi = 0;
      const animate = (now: number) => {
        if (ticket !== gravityRequestRef.current || robotRef.current !== robot) return;
        if (started === null) started = now;
        const elapsed = Math.min(duration, (now - started) / 1000 * playbackRate);
        index = applyFrame(robot, frames, elapsed, comparisonOffset, index);
        for (const item of passiveResults)
          item.index = applyFrame(item.robot, item.result.frames, elapsed, item.offset, item.index);
        followGravityRef.current?.(robot);
        if (now - lastUi > 120 || elapsed >= duration) {
          lastUi = now;
          setJoints(old => old.map(joint => ({ ...joint, value: Number(robot.joints[joint.name]?.jointValue[0] ?? joint.value) })));
          setGravityMessage(`正在播放重力下落：${elapsed.toFixed(1)} / ${duration.toFixed(1)} 秒（⅔ 倍速）`);
        }
        if (elapsed < duration) {
          gravityAnimationRef.current = requestAnimationFrame(animate);
        } else {
          refreshModelAnalysisRef.current?.(robot);
          if (selectedObjectRef.current) setSelection(selectionInfo(robot, selectedObjectRef.current));
          setGravityMessage(`${result.engine}：${passiveResults.length + 1} 个模型同步预览，物理地面 z=0，无反弹贴地预览，${result.ground_contacts > 0 ? `${result.ground_contacts} 处物理接触` : '碰撞体距地小于 2 mm'}，${result.joint_count} 个关节已同步；${result.status === 'settled' ? '已稳定落地' : '关节仍可能缓慢运动'}（模拟 ${result.simulated_seconds.toFixed(1)} 秒）。${maxGroundAdjustment > 0.002 ? `模型贴地显示校正最大 ${(maxGroundAdjustment * 1000).toFixed(0)} mm。` : ''}`);
        }
      };
      gravityAnimationRef.current = requestAnimationFrame(animate);
    } catch (cause) {
      if (ticket !== gravityRequestRef.current) return;
      gravityRef.current = false;
      setGravityEnabled(false);
      preGravityPoseRef.current = null;
      for (const saved of preGravityPassiveRef.current) {
        saved.robot.position.copy(saved.position);
        saved.robot.quaternion.copy(saved.quaternion);
        for (const [name, value] of Object.entries(saved.joints)) saved.robot.setJointValue(name, value);
        saved.robot.updateMatrixWorld(true);
      }
      preGravityPassiveRef.current = [];
      placeOnGroundRef.current?.();
      setGravityMessage('重力计算失败：' + String(cause));
    }
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
  const comparisonGroundMins = [robotRef.current, ...compareRobotsRef.current]
    .filter((item): item is URDFRobot => !!item).map(item => overallVisualBounds(item)?.min.z ?? null);
  const jointComparison = selectedObject?.type === 'joint' ? [
    { id: report.operation_id, report, robot: robotRef.current }, ...passiveModelsRef.current
  ].flatMap(item => {
    const joint = item.robot?.joints[selectedObject.name];
    if (!joint || !item.robot) return [];
    const child = directChild(joint.urdfNode, 'child')?.getAttribute('link') || '';
    const row = readPhysicsRows(item.robot).find(candidate => candidate.name === child);
    const modelName = item.report.models.find(model => model.path === item.report.selected_model)?.name ||
      item.report.selected_model || item.id;
    return [{ id: item.id, modelName, joint, child, row,
      position: tuple(joint.getWorldPosition(new THREE.Vector3())),
      orientation: joint.getWorldQuaternion(new THREE.Quaternion()).toArray() }];
  }) : [];

  if (!ready) return null;
  return <section aria-label="三维机器人查看器" className="robot-viewer"
    data-mesh-count={meshCount} data-lit-mesh-count={litMeshCount} data-mesh-files-loaded={meshFilesLoaded} data-textured-mesh-count={textureCount} data-joint-quaternion={jointRotation} data-assets-loaded={String(assetsLoaded)}
    data-tree-link-count={linkCount} data-tree-joint-count={Object.keys(robotRef.current?.joints ?? {}).length}
    data-joint-gizmo-count={jointGizmoCount}
    data-visual-count={visualCount} data-collision-count={collisionCount}
    data-collision-styled-mesh-count={collisionStyledMeshCount}
    data-visible-visual-count={visibleVisualCount} data-visible-collision-count={visibleCollisionCount}
    data-com-marker-count={comMarkerCount} data-visible-com-marker-count={visibleComMarkerCount}
    data-inertia-marker-count={inertiaMarkerCount} data-visible-inertia-marker-count={visibleInertiaMarkerCount}
    data-inertia-visible={String(showInertiaMarkers)}
    data-shadow-visible={String(showShadows)} data-compare-loaded-count={compareLoadedCount}
    data-compare-ground-mins={comparisonGroundMins.map(value => value === null ? 'unknown' : value.toFixed(4)).join(',')}
    data-compare-visible-visual-count={compareVisibleVisualCount}
    data-compare-visible-collision-count={compareVisibleCollisionCount}
    data-com-visible={String(showComMarkers)} data-isolated-link={isolatedLink ?? ''}
    data-screenshot-ready={String(screenshotReady)} data-view-reset-count={viewResetCount}
    data-collision-visible={String(collisionVisible)} data-visual-visible={String(visualVisible)}
    data-gravity-visual-min={visualGroundMin === null ? '' : visualGroundMin.toFixed(5)} data-angle-unit={angleUnit}
    data-robot-root-z={robotRef.current?.position.z.toFixed(5) ?? ''}
    data-mass-known-count={knownMassCount} data-mass-unknown-count={unknownMassCount}
    data-total-known-mass={knownMassTotal.toFixed(3)} data-mass-complete={String(massComplete)}
    data-physics-fingerprint={physicsFingerprint(physicsRows)}
    data-overall-bounds={boundsAttribute} data-selected-node={selectedKey}
    data-selected-position={selectedPosition} data-selected-dimensions={selectedDimensions}>
    <div className="scene-heading"><div><small>02 / 三维视图</small><h2>{selected?.name || selected?.path}</h2></div>
      <div className="viewer-panel-launcher">{(['display', 'structure', 'joints', 'physics', 'measure'] as const).map((key, index) =>
        <button key={key} type="button" aria-pressed={panels[key]}
          onClick={() => setPanels(current => ({ ...current, [key]: !current[key] }))}>
          {['显示', '结构', '关节', '物理', '测量'][index]}</button>)}</div></div>
    <div className="viewer-grid">
      <div className="viewer-scene-layer">
        <div ref={host} className="robot-canvas" aria-label="机器人三维场景" />
        <p className="hint" data-assets-status>{error ? '模型资源加载异常：请查看错误提示' : assetsLoaded ? `URDF 已加载 · ${meshFilesLoaded} 个网格实例 · ${textureCount} 个贴图表面` : '正在解析 URDF 并加载网格资源…'}</p>
        {panels.display && <FloatingPanel title="显示与姿态" initial={{ x: 14, y: 18, width: 280, height: 245 }} dockSide="left" dockOrder={1}
          onClose={() => setPanels(current => ({ ...current, display: false }))}>
        <fieldset className="viewer-toggles">
          <legend>模型显示</legend>
          <label><input type="checkbox" aria-label="显示视觉模型" checked={visualVisible}
            onChange={event => setVisualVisible(event.target.checked)} />视觉模型</label>
          <label><input type="checkbox" aria-label="显示碰撞体" checked={collisionVisible}
            onChange={event => setCollisionVisible(event.target.checked)} />碰撞体</label>
          <label><input type="checkbox" aria-label="显示惯量" checked={showInertiaMarkers}
            onChange={event => setShowInertiaMarkers(event.target.checked)} />惯量蓝框</label>
          <label><input type="checkbox" aria-label="显示已知质心" checked={showComMarkers}
            onChange={event => setShowComMarkers(event.target.checked)} />已知质心</label>
          <label><input type="checkbox" aria-label="显示阴影" checked={showShadows}
            onChange={event => setShowShadows(event.target.checked)} />阴影</label>
          <label><input type="checkbox" aria-label="受重力影响" disabled={picking} checked={gravityEnabled}
            onChange={event => void toggleGravity(event.target.checked)} />受重力影响</label>
          <button type="button" aria-label="隔离选中 Link" disabled={selectedObject?.type !== 'link'}
            onClick={() => { if (selectedObject?.type === 'link') setIsolatedLink(current => current === selectedObject.name ? null : selectedObject.name); }}>
            {isolatedLink ? '解除隔离' : '隔离选中 Link'}
          </button>
          <button type="button" aria-label="重置视角" onClick={() => { resetViewRef.current?.(); setViewResetCount(count => count + 1); }}>重置视角</button>
          <button type="button" aria-label="导出三维截图" onClick={exportScreenshot}>导出 PNG</button>
          <span>显示与重力预览作用于全部对比模型。惯量蓝框按完整惯量张量的主轴和等效均匀盒计算；无效质量或惯量不显示。橙色圆点可拖动当前模型的关节。</span>
        </fieldset>
        {gravityMessage && <p role="status" className="gravity-status">{gravityMessage}</p>}
        </FloatingPanel>}
        {screenshotMessage && <p role="status" data-screenshot-message>{screenshotMessage}</p>}
        {selectedObject?.type === 'joint' && jointComparison.length > 0 &&
          <section className="joint-comparison-popover" aria-label="同名关节物理信息" data-joint-comparison={selectedObject.name}>
            <div className="joint-comparison-head"><strong>{selectedObject.name} · 关节物理信息</strong>
              <button type="button" aria-label="关闭关节物理信息" onClick={() => {
                selectedObjectRef.current = null; setSelectedObject(null); setSelection(null);
              }}>×</button></div>
            <div className="joint-comparison-cards">{jointComparison.map(item => <article key={item.id} data-joint-compare-model={item.id}>
              <h4>{item.modelName}</h4>
              <p>关节：{item.joint.jointType} · 子 Link：{item.child || '未知'}</p>
              <p>位置：{formatVector(item.position, 'm')}</p>
              <p>姿态四元数 (x,y,z,w)：{item.orientation.map(value => value.toFixed(3)).join(', ')}</p>
              <p>关节值：{Number(item.joint.jointValue[0] ?? 0).toFixed(3)} {item.joint.jointType === 'prismatic' ? 'm' : 'rad'}</p>
              <p>轴向：{directChild(item.joint.urdfNode, 'axis')?.getAttribute('xyz') || '1 0 0（默认）'}</p>
              <p>限位：{item.joint.jointType === 'continuous' ? '连续旋转' :
                Number.isFinite(item.joint.limit.lower) && Number.isFinite(item.joint.limit.upper) ?
                  `${item.joint.limit.lower.toFixed(3)} ~ ${item.joint.limit.upper.toFixed(3)}` : '未提供'}</p>
              <p>子 Link 质量：{item.row?.mass == null ? '未知' : `${item.row.mass.toFixed(4)} kg`}</p>
              <p>子 Link 质心（局部）：{formatVector(item.row?.comLocal ?? null, 'm')}</p>
              <p>子 Link 惯量 (kg·m²)：{item.row ? INERTIA_KEYS.map(key =>
                `${key}=${item.row!.inertia[key] === null ? '未知' : item.row!.inertia[key]!.toExponential(2)}`).join(' · ') : '未知'}</p>
            </article>)}</div>
          </section>}
        {error && <p role="alert" className="viewer-runtime-error">{error}</p>}
        {panels.measure && <FloatingPanel title="几何测量" initial={{ x: 20, y: 300, width: 300, height: 175 }} dockSide="right" dockOrder={3}
          onClose={() => setPanels(current => ({ ...current, measure: false }))}>
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
        </section></FloatingPanel>}
      </div>
      {panels.structure && <FloatingPanel title="结构树" initial={{ x: 350, y: 18, width: 340, height: 310 }} dockSide="right" dockOrder={0}
        onClose={() => setPanels(current => ({ ...current, structure: false }))} className="structure-window">
        <section aria-label="机器人结构树" className="analysis-panel">
          <div className="structure-panel-heading"><h3>结构树 · {linkCount} Link / {Object.keys(robotRef.current?.joints ?? {}).length} Joint</h3>
            <div className="angle-unit-switch" role="group" aria-label="旋转关节角度单位">
              <button type="button" aria-pressed={angleUnit === 'rad'} onClick={() => setAngleUnit('rad')}>弧度 rad</button>
              <button type="button" aria-pressed={angleUnit === 'deg'} onClick={() => setAngleUnit('deg')}>角度 °</button>
            </div></div>
          {selectedObject?.type === 'joint' && joints.some(joint => joint.name === selectedObject.name) &&
            <output className="structure-joint-value" data-structure-joint-value>
              {selectedObject.name}：{(() => { const joint = joints.find(item => item.name === selectedObject.name)!;
                return joint.unit === 'm' ? `${joint.value.toFixed(3)} m` :
                  angleUnit === 'deg' ? `${(joint.value * 180 / Math.PI).toFixed(1)}°` : `${joint.value.toFixed(3)} rad`;
              })()}
            </output>}
          {selectedObject?.type === 'joint' && joints.some(joint => joint.name === selectedObject.name && joint.unit === 'rad') &&
            <p className="hint">红色圆环标示旋转轴，蓝色箭头指向 URDF 定义的轴正方向。</p>}
          {linkTree.length ? <StructureGraph roots={linkTree} selected={selectedObject} onSelect={selectStructure}
            jointValues={Object.fromEntries(joints.map(joint => [joint.name, { value: joint.value, unit: joint.unit }]))}
            angleUnit={angleUnit} /> : <p>尚无可显示的结构树。</p>}
        </section></FloatingPanel>}
      {panels.physics && <FloatingPanel title="质量与惯量" initial={{ x: 350, y: 100, width: 330, height: 185 }} dockSide="right" dockOrder={2}
        onClose={() => setPanels(current => ({ ...current, physics: false }))}>
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
        </section></FloatingPanel>}
      {panels.joints && <FloatingPanel title="关节控制" initial={{ x: 350, y: 340, width: 320, height: 250 }} dockSide="right" dockOrder={1}
        onClose={() => setPanels(current => ({ ...current, joints: false }))} className="joints-window">
        <section aria-label="关节控制" className="analysis-panel"><h3>关节控制（{joints.length}）</h3>
          {joints.some(joint => joint.hasLimit) && <button type="button" aria-label="一键切换全部关节限位"
            disabled={gravityEnabled} onClick={toggleAllJointLimits}>
            {joints.filter(joint => joint.hasLimit).every(joint => joint.useLimit) ? '关闭全部限位' : '开启全部限位'}
          </button>}
          {joints.length === 0 ? <p>当前模型没有可移动关节。</p> :
          <div className="joint-panel">{joints.map(joint => <div key={joint.name} className="joint-item"
            data-selected={selectedObject?.type === 'joint' && selectedObject.name === joint.name}>
            <span>{joint.name} · {joint.kind}</span>
            {joint.hasLimit && <label className="joint-limit-control"><input type="checkbox" aria-label={`${joint.name} 应用 URDF 限位`}
              disabled={gravityEnabled} checked={joint.useLimit} onChange={event => toggleJointLimit(joint.name, event.target.checked)} />应用 URDF 限位</label>}
            <input aria-label={joint.name} type="range" disabled={gravityEnabled}
              min={joint.useLimit ? joint.min : joint.previewMin} max={joint.useLimit ? joint.max : joint.previewMax} step={0.01}
              value={joint.value} onChange={event => changeJoint(joint.name, Number(event.target.value))} />
            <output>{joint.unit === 'm' ? `${joint.value.toFixed(3)} m` : angleUnit === 'deg' ? `${(joint.value * 180 / Math.PI).toFixed(1)}°` : `${joint.value.toFixed(3)} rad`}</output>
          </div>)}</div>}
          <p className="hint">限位开关仅影响当前预览和重力模拟，不修改 URDF 文件。</p>
        </section></FloatingPanel>}
    </div>
  </section>;
}
