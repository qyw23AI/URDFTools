import { useEffect, useRef } from 'react';
import * as THREE from 'three';
import { STLLoader } from 'three/addons/loaders/STLLoader.js';
import type { JointAxisCandidate } from './cadJointInference';

export type CadPartShape = { name: string; bounds_min_m: number[]; bounds_max_m: number[];
  mesh_url?: string; color_rgb?: number[] | null };
type JointPose = { parent: string; child: string; type: string; axis: number[]; origin_m: number[] };
type LinkPose = { name: string; parts: string[] };
const joinPoint = (point: number[]) => point.map(value => value.toFixed(6)).join(',');

export function CadPartCanvas({ parts, selected, hidden = [], fallbackBoxes = false, links = [], joints = [], jointValues = {}, onSelect, onPick, onLoadError, pickingJoint, jointOrigin, jointAxis, parentParts = [], childParts = [], axisCandidates = [], onAxisSelect }: {
  parts: CadPartShape[]; selected: string[]; hidden?: string[]; onSelect: (name: string) => void;
  fallbackBoxes?: boolean;
  links?: LinkPose[]; joints?: JointPose[]; jointValues?: Record<string, number>;
  onLoadError?: (message: string) => void;
  onPick?: (name: string, point: [number, number, number]) => void;
  pickingJoint?: boolean; jointOrigin?: number[]; jointAxis?: number[];
  parentParts?: string[]; childParts?: string[];
  axisCandidates?: JointAxisCandidate[]; onAxisSelect?: (candidate: JointAxisCandidate) => void;
}) {
  const host = useRef<HTMLDivElement>(null);
  const selectedRef = useRef(selected);
  selectedRef.current = selected;
  const hiddenRef = useRef(hidden);
  hiddenRef.current = hidden;
  const linksRef = useRef(links);
  linksRef.current = links;
  const jointsRef = useRef(joints);
  jointsRef.current = joints;
  const valuesRef = useRef(jointValues);
  valuesRef.current = jointValues;
  const selectRef = useRef(onSelect);
  selectRef.current = onSelect;
  const pickRef = useRef(onPick);
  pickRef.current = onPick;
  const errorRef = useRef(onLoadError);
  errorRef.current = onLoadError;
  const pickingRef = useRef(pickingJoint);
  pickingRef.current = pickingJoint;
  const parentRef = useRef(parentParts);
  parentRef.current = parentParts;
  const childRef = useRef(childParts);
  childRef.current = childParts;
  const originRef = useRef(jointOrigin);
  originRef.current = jointOrigin;
  const axisRef = useRef(jointAxis);
  axisRef.current = jointAxis;
  const candidatesRef = useRef(axisCandidates);
  candidatesRef.current = axisCandidates;
  const selectAxisRef = useRef(onAxisSelect);
  selectAxisRef.current = onAxisSelect;
  useEffect(() => {
    const element = host.current;
    if (!element) return;
    let stopped = false;
    let frame = 0;
    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x1c2b37);
    const camera = new THREE.PerspectiveCamera(48, 1, 0.001, 1000);
    camera.up.set(0, 0, 1);
    const renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    element.appendChild(renderer.domElement);
    scene.add(new THREE.HemisphereLight(0xffffff, 0x52677c, 2));
    const light = new THREE.DirectionalLight(0xffffff, 2);
    light.position.set(3, -4, 7); scene.add(light);
    const modelRoot = new THREE.Group();
    const meshRoot = new THREE.Group();
    modelRoot.add(meshRoot); scene.add(modelRoot);
    const meshes: THREE.Mesh[] = [];
    const bounds = new THREE.Box3();
    const loader = new STLLoader();
    for (const [index, part] of parts.entries()) {
      const min = new THREE.Vector3(part.bounds_min_m[0], part.bounds_min_m[1], part.bounds_min_m[2]);
      const max = new THREE.Vector3(part.bounds_max_m[0], part.bounds_max_m[1], part.bounds_max_m[2]);
      bounds.expandByPoint(min); bounds.expandByPoint(max);
      if (!part.mesh_url) {
        if (fallbackBoxes) {
          const size = max.clone().sub(min);
          const mesh = new THREE.Mesh(new THREE.BoxGeometry(size.x, size.y, size.z),
            new THREE.MeshStandardMaterial({color: 0x98a7ae, roughness: 0.8}));
          mesh.position.copy(min.clone().add(max).multiplyScalar(0.5));
          mesh.name = part.name; mesh.userData.baseColor = new THREE.Color(0x98a7ae);
          mesh.updateMatrix(); mesh.userData.baseMatrix = mesh.matrix.clone(); mesh.matrixAutoUpdate = false;
          meshRoot.add(mesh); meshes.push(mesh);
        } else errorRef.current?.(`${part.name}: 没有可用的 CAD 网格`);
        continue;
      }
      void fetch(part.mesh_url).then(response => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return response.arrayBuffer();
      }).then(bytes => {
        const geometry = loader.parse(bytes);
        const sourceColor = part.color_rgb?.length === 3 ?
          new THREE.Color(part.color_rgb[0], part.color_rgb[1], part.color_rgb[2]) :
          new THREE.Color().setHSL((index * 0.147) % 1, 0.32, 0.54);
        const mesh = new THREE.Mesh(geometry, new THREE.MeshStandardMaterial({
          color: sourceColor, metalness: 0.12, roughness: 0.66, side: THREE.DoubleSide
        }));
        mesh.name = part.name;
        mesh.userData.baseColor = sourceColor;
        mesh.updateMatrix(); mesh.userData.baseMatrix = mesh.matrix.clone(); mesh.matrixAutoUpdate = false;
        if (stopped) { geometry.dispose(); (mesh.material as THREE.Material).dispose(); return; }
        meshRoot.add(mesh); meshes.push(mesh);
      }).catch(cause => errorRef.current?.(`${part.name}: 网格加载失败：${String(cause)}`));
    }
    const center = bounds.isEmpty() ? new THREE.Vector3() : bounds.getCenter(new THREE.Vector3());
    const radius = Math.max(0.04, bounds.isEmpty() ? 0.3 : bounds.getSize(new THREE.Vector3()).length() / 2);
    camera.position.copy(center).add(new THREE.Vector3(radius * 1.4, -radius * 1.7, radius * 1.2));
    camera.lookAt(center);
    modelRoot.position.copy(center);
    meshRoot.position.copy(center).multiplyScalar(-1);
    const pivot = new THREE.Group();
    const pivotRing = new THREE.Mesh(new THREE.TorusGeometry(0.018, 0.002, 8, 48),
      new THREE.MeshBasicMaterial({color: 0xff3838, depthTest: false}));
    const pivotDot = new THREE.Mesh(new THREE.SphereGeometry(0.006, 12, 12),
      new THREE.MeshBasicMaterial({color: 0xff3838, depthTest: false}));
    const arrow = new THREE.ArrowHelper(new THREE.Vector3(0, 0, 1), new THREE.Vector3(), 0.16, 0x248cff, 0.035, 0.017);
    (arrow.line.material as THREE.Material).depthTest = false;
    (arrow.cone.material as THREE.Material).depthTest = false;
    arrow.line.renderOrder = 50; arrow.cone.renderOrder = 50;
    pivot.add(pivotRing, pivotDot, arrow);
    pivot.scale.setScalar(Math.min(2, Math.max(0.2, radius / 1.4)));
    meshRoot.add(pivot);
    const candidateRoot = new THREE.Group();
    meshRoot.add(candidateRoot);
    type CandidateVisual = {group: THREE.Group; ring: THREE.Mesh; hit: THREE.Mesh; arrow: THREE.ArrowHelper};
    let candidateVisuals: CandidateVisual[] = [];
    let shownCandidates: JointAxisCandidate[] = [];
    let hoveredCandidate = -1;
    function disposeCandidates() {
      for (const visual of candidateVisuals) {
        visual.ring.geometry.dispose(); (visual.ring.material as THREE.Material).dispose();
        visual.hit.geometry.dispose(); (visual.hit.material as THREE.Material).dispose();
        visual.arrow.line.geometry.dispose(); (visual.arrow.line.material as THREE.Material).dispose();
        visual.arrow.cone.geometry.dispose(); (visual.arrow.cone.material as THREE.Material).dispose();
        candidateRoot.remove(visual.group);
      }
      candidateVisuals = [];
    }
    function updateCandidates(next: JointAxisCandidate[]) {
      if (shownCandidates === next) return;
      disposeCandidates(); shownCandidates = next; hoveredCandidate = -1;
      for (const candidate of next) {
        const group = new THREE.Group();
        const ringRadius = Math.max(0.008, Math.min(radius * 0.18, candidate.radius_m * 1.2));
        const ring = new THREE.Mesh(new THREE.TorusGeometry(ringRadius, Math.max(0.001, ringRadius * 0.09), 8, 48),
          new THREE.MeshBasicMaterial({color: 0xf24d56, transparent: true, opacity: 0.68, depthTest: false}));
        const hit = new THREE.Mesh(new THREE.CircleGeometry(ringRadius * 1.45, 32),
          new THREE.MeshBasicMaterial({color: 0xffffff, transparent: true, opacity: 0.001, side: THREE.DoubleSide, depthTest: false}));
        const arrow = new THREE.ArrowHelper(new THREE.Vector3(0, 0, 1), new THREE.Vector3(),
          Math.max(0.06, radius * 0.38), 0x219bff, Math.max(0.016, radius * 0.08), Math.max(0.008, radius * 0.035));
        (arrow.line.material as THREE.Material).depthTest = false;
        (arrow.cone.material as THREE.Material).depthTest = false;
        arrow.line.renderOrder = 50; arrow.cone.renderOrder = 50;
        arrow.visible = false;
        group.add(ring, hit, arrow); candidateRoot.add(group);
        candidateVisuals.push({group, ring, hit, arrow});
      }
    }
    const raycaster = new THREE.Raycaster();
    const pointer = new THREE.Vector2();
    let down: { x: number; y: number; distance: number; button: number } | null = null;
    let lastJointFocus = '';
    const upAxis = camera.up.clone().normalize();
    const rightAxis = new THREE.Vector3(1, 0, 0).applyQuaternion(camera.quaternion).normalize();
    const screenUpAxis = new THREE.Vector3(0, 1, 0).applyQuaternion(camera.quaternion).normalize();
    const onDown = (event: PointerEvent) => {
      if (event.button !== 0 && event.button !== 2) return;
      down = { x: event.clientX, y: event.clientY, distance: 0, button: event.button };
      if (event.isTrusted) renderer.domElement.setPointerCapture(event.pointerId);
    };
    const onMove = (event: PointerEvent) => {
      if (!down) {
        const rect = renderer.domElement.getBoundingClientRect();
        pointer.set((event.clientX - rect.left) / rect.width * 2 - 1, -(event.clientY - rect.top) / rect.height * 2 + 1);
        raycaster.setFromCamera(pointer, camera);
        const hit = raycaster.intersectObjects(candidateVisuals.map(visual => visual.hit), false)[0];
        hoveredCandidate = hit ? candidateVisuals.findIndex(visual => visual.hit === hit.object) : -1;
        renderer.domElement.style.cursor = hoveredCandidate >= 0 ? 'pointer' : '';
        return;
      }
      const dx = event.clientX - down.x, dy = event.clientY - down.y;
      down.distance += Math.hypot(dx, dy);
      down.x = event.clientX; down.y = event.clientY;
      if (!dx && !dy) return;
      if (down.button === 2) {
        const zoom = camera.position.distanceTo(center);
        modelRoot.position.addScaledVector(rightAxis, dx * zoom / Math.max(200, element.clientHeight));
        modelRoot.position.addScaledVector(upAxis, -dy * zoom / Math.max(200, element.clientHeight));
      } else {
        modelRoot.quaternion.premultiply(new THREE.Quaternion().setFromAxisAngle(upAxis, dx * 0.008));
        modelRoot.quaternion.premultiply(new THREE.Quaternion().setFromAxisAngle(rightAxis, dy * 0.008));
      }
    };
    const onUp = (event: PointerEvent) => {
      if (!down || event.button !== down.button) return;
      const movement = down.distance + Math.hypot(event.clientX - down.x, event.clientY - down.y);
      const button = down.button;
      down = null;
      if (movement > 5 || button !== 0) return;
      const rect = renderer.domElement.getBoundingClientRect();
      pointer.set((event.clientX - rect.left) / rect.width * 2 - 1, -(event.clientY - rect.top) / rect.height * 2 + 1);
      raycaster.setFromCamera(pointer, camera);
      const candidateHit = raycaster.intersectObjects(candidateVisuals.map(visual => visual.hit), false)[0];
      if (candidateHit) {
        const index = candidateVisuals.findIndex(visual => visual.hit === candidateHit.object);
        if (index >= 0) { selectAxisRef.current?.(shownCandidates[index]); return; }
      }
      const hit = raycaster.intersectObjects(meshes.filter(mesh => mesh.visible), false)[0];
      if (hit) {
        selectRef.current(hit.object.name);
        if (pickingRef.current) {
          const originalPoint = meshRoot.worldToLocal(hit.point.clone());
          pickRef.current?.(hit.object.name, [originalPoint.x, originalPoint.y, originalPoint.z]);
        }
      }
    };
    const onWheel = (event: WheelEvent) => {
      event.preventDefault();
      const offset = camera.position.clone().sub(center);
      const scale = Math.exp(event.deltaY * 0.001);
      offset.setLength(THREE.MathUtils.clamp(offset.length() * scale, radius * 1.15, radius * 8));
      camera.position.copy(center).add(offset);
    };
    const onCancel = () => { down = null; };
    renderer.domElement.addEventListener('pointerdown', onDown);
    renderer.domElement.addEventListener('pointermove', onMove);
    renderer.domElement.addEventListener('pointerup', onUp);
    renderer.domElement.addEventListener('pointercancel', onCancel);
    renderer.domElement.addEventListener('wheel', onWheel, { passive: false });
    const onContextMenu = (event: MouseEvent) => event.preventDefault();
    renderer.domElement.addEventListener('contextmenu', onContextMenu);
    const render = () => {
      if (stopped) return;
      const width = Math.max(2, element.clientWidth), height = Math.max(2, element.clientHeight);
      renderer.setSize(width, height, false);
      camera.aspect = width / height; camera.updateProjectionMatrix();
      const partLinks = new Map(linksRef.current.flatMap(link => link.parts.map(part => [part, link.name] as const)));
      const linkTransforms = new Map<string, THREE.Matrix4>();
      const childNames = new Set(jointsRef.current.map(joint => joint.child));
      for (const link of linksRef.current) if (!childNames.has(link.name)) linkTransforms.set(link.name, new THREE.Matrix4());
      for (let pass = 0; pass < jointsRef.current.length; pass++) {
        let changed = false;
        for (const joint of jointsRef.current) {
          const parent = linkTransforms.get(joint.parent);
          if (!parent || linkTransforms.has(joint.child)) continue;
          const origin = new THREE.Vector3(...joint.origin_m);
          const axis = new THREE.Vector3(...joint.axis).normalize();
          const value = valuesRef.current[joint.child] || 0;
          const motion = joint.type === 'prismatic' ?
            new THREE.Matrix4().makeTranslation(axis.x * value, axis.y * value, axis.z * value) :
            new THREE.Matrix4().makeRotationAxis(axis, joint.type === 'fixed' ? 0 : value);
          const transform = parent.clone().multiply(new THREE.Matrix4().makeTranslation(origin.x, origin.y, origin.z))
            .multiply(motion).multiply(new THREE.Matrix4().makeTranslation(-origin.x, -origin.y, -origin.z));
          linkTransforms.set(joint.child, transform); changed = true;
        }
        if (!changed) break;
      }
      for (const mesh of meshes) {
        mesh.matrix.copy(linkTransforms.get(partLinks.get(mesh.name) || '') || new THREE.Matrix4())
          .multiply(mesh.userData.baseMatrix);
        const material = mesh.material as THREE.MeshStandardMaterial;
        mesh.visible = !hiddenRef.current.includes(mesh.name);
        if (selectedRef.current.includes(mesh.name)) material.color.setHex(0x101010);
        else if (childRef.current.includes(mesh.name)) material.color.setHex(0x368d82);
        else if (parentRef.current.includes(mesh.name)) material.color.setHex(0xa87b3f);
        else material.color.copy(mesh.userData.baseColor);
      }
      updateCandidates(candidatesRef.current);
      for (const [index, visual] of candidateVisuals.entries()) {
        const candidate = shownCandidates[index];
        const parentLink = partLinks.get(candidate.parentPart);
        const transform = linkTransforms.get(parentLink || '') || new THREE.Matrix4();
        const direction = new THREE.Vector3(...candidate.axis).normalize().transformDirection(transform);
        visual.group.position.set(...candidate.origin_m as [number, number, number]).applyMatrix4(transform);
        visual.group.quaternion.setFromUnitVectors(new THREE.Vector3(0, 0, 1), direction);
        const hovered = index === hoveredCandidate;
        (visual.ring.material as THREE.MeshBasicMaterial).color.setHex(hovered ? 0x279fff : 0xf24d56);
        (visual.ring.material as THREE.MeshBasicMaterial).opacity = hovered ? 0.95 : 0.68;
        visual.arrow.visible = hovered;
      }
      const origin = originRef.current;
      pivot.visible = !candidateVisuals.length && !!origin && origin.length === 3;
      if (pivot.visible) {
        const selectedParent = parentRef.current.length ? partLinks.get(parentRef.current[0]) : undefined;
        const parentTransform = linkTransforms.get(selectedParent || '') || new THREE.Matrix4();
        pivot.position.set(origin![0], origin![1], origin![2]).applyMatrix4(parentTransform);
        const axis = axisRef.current || [0, 0, 1];
        const direction = new THREE.Vector3(axis[0], axis[1], axis[2]).normalize().transformDirection(parentTransform);
        arrow.setDirection(direction);
        pivotRing.quaternion.setFromUnitVectors(new THREE.Vector3(0, 0, 1), direction);
      }
      const focusOrigin = candidateVisuals.length ? shownCandidates[0].origin_m : pivot.visible ? origin : undefined;
      const focusTarget = candidateVisuals.length ? candidateVisuals[0].group : pivot;
      const focusKey = focusOrigin ? `${joinPoint(focusOrigin)}:${candidateVisuals.length}:${parentRef.current.join(',')}:${childRef.current.join(',')}` : '';
      if (focusKey && focusKey !== lastJointFocus) {
        lastJointFocus = focusKey;
        const panel = element.closest('.cad-wizard')?.querySelector('.cad-joint-work-window');
        if (panel) {
          const canvasRect = renderer.domElement.getBoundingClientRect();
          const panelRect = panel.getBoundingClientRect();
          const projected = focusTarget.getWorldPosition(new THREE.Vector3()).project(camera);
          const screenX = canvasRect.left + (projected.x + 1) * width / 2;
          const screenY = canvasRect.top + (1 - projected.y) * height / 2;
          if (screenX >= panelRect.left && screenX <= panelRect.right && screenY > panelRect.top - 70) {
            const pixels = screenY - (panelRect.top - 85);
            const unitsPerPixel = 2 * camera.position.distanceTo(center) * Math.tan(THREE.MathUtils.degToRad(camera.fov / 2)) / height;
            modelRoot.position.addScaledVector(screenUpAxis, pixels * unitsPerPixel);
          }
        }
      } else if (!focusKey) lastJointFocus = '';
      element.dataset.jointOrigin = pivot.visible ? joinPoint(origin!) : '';
      element.dataset.jointAxis = pivot.visible ? joinPoint(axisRef.current || [0, 0, 1]) : '';
      element.dataset.modelQuaternion = modelRoot.quaternion.toArray().map(value => value.toFixed(6)).join(',');
      element.dataset.modelPosition = joinPoint(modelRoot.position.toArray());
      element.dataset.candidateCount = String(candidateVisuals.length);
      element.dataset.hoveredCandidate = String(hoveredCandidate);
      element.dataset.candidateScreenPositions = JSON.stringify(candidateVisuals.map(visual => {
        const projected = visual.hit.getWorldPosition(new THREE.Vector3()).project(camera);
        return [Math.round((projected.x + 1) * width / 2), Math.round((1 - projected.y) * height / 2)];
      }));
      element.dataset.cameraPosition = camera.position.toArray().map(value => value.toFixed(6)).join(',');
      const motionChild = jointsRef.current.find(joint => joint.type !== 'fixed')?.child;
      const motionMesh = meshes.find(mesh => partLinks.get(mesh.name) === motionChild);
      element.dataset.motionMatrix = motionMesh?.matrix.elements.map(value => value.toFixed(5)).join(',') || '';
      renderer.render(scene, camera);
      frame = requestAnimationFrame(render);
    };
    render();
    return () => {
      stopped = true; cancelAnimationFrame(frame);
      renderer.domElement.removeEventListener('pointerdown', onDown);
      renderer.domElement.removeEventListener('pointermove', onMove);
      renderer.domElement.removeEventListener('pointerup', onUp);
      renderer.domElement.removeEventListener('pointercancel', onCancel);
      renderer.domElement.removeEventListener('wheel', onWheel);
      renderer.domElement.removeEventListener('contextmenu', onContextMenu);
      disposeCandidates();
      meshes.forEach(mesh => { mesh.geometry.dispose(); (mesh.material as THREE.Material).dispose(); });
      pivotRing.geometry.dispose(); (pivotRing.material as THREE.Material).dispose();
      pivotDot.geometry.dispose(); (pivotDot.material as THREE.Material).dispose();
      arrow.line.geometry.dispose(); (arrow.line.material as THREE.Material).dispose();
      arrow.cone.geometry.dispose(); (arrow.cone.material as THREE.Material).dispose();
      renderer.dispose(); renderer.domElement.remove();
    };
  }, [parts]);
  return <div className="cad-part-canvas" ref={host} aria-label="CAD 零件三维选择画布" />;
}
