import { useEffect, useRef } from 'react';
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';

export type PuzzlePart = { name: string; width_mm: number; height_mm: number; depth_mm: number; placement_mm: number[] };

export function ModelPuzzleCanvas({ parts, selected, onSelect, onMove }: {
  parts: PuzzlePart[]; selected: string | null; onSelect: (name: string) => void;
  onMove: (name: string, x_mm: number, y_mm: number) => void;
}) {
  const host = useRef<HTMLDivElement>(null);
  const view = useRef<{ count: number; camera: THREE.Vector3; target: THREE.Vector3 } | null>(null);
  const selectedRef = useRef(selected);
  selectedRef.current = selected;
  const selectRef = useRef(onSelect), moveRef = useRef(onMove);
  selectRef.current = onSelect; moveRef.current = onMove;
  useEffect(() => {
    const element = host.current;
    if (!element) return;
    let stopped = false, frame = 0;
    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x1c2b37);
    const camera = new THREE.PerspectiveCamera(48, 1, 0.001, 1000);
    camera.up.set(0, 0, 1);
    const renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    element.appendChild(renderer.domElement);
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    const grid = new THREE.GridHelper(0.4, 40, 0x6b8598, 0x3a5262);
    grid.rotation.x = Math.PI / 2;
    scene.add(grid, new THREE.HemisphereLight(0xffffff, 0x546c80, 2));
    const light = new THREE.DirectionalLight(0xffffff, 2);
    light.position.set(0.3, -0.4, 0.7); scene.add(light);
    const meshes: THREE.Mesh[] = [];
    const bounds = new THREE.Box3();
    parts.forEach((part, index) => {
      const width = Math.max(0.001, part.width_mm / 1000);
      const height = Math.max(0.001, part.height_mm / 1000);
      const depth = Math.max(0.001, part.depth_mm / 1000);
      const mesh = new THREE.Mesh(new THREE.BoxGeometry(width, height, depth),
        new THREE.MeshStandardMaterial({ color: new THREE.Color().setHSL((index * 0.16 + 0.48) % 1, 0.47, 0.52),
          roughness: 0.7 }));
      mesh.name = part.name;
      mesh.position.set((part.placement_mm[0] || 0) / 1000, (part.placement_mm[1] || 0) / 1000,
        (part.placement_mm[2] || 0) / 1000 + depth / 2);
      scene.add(mesh); meshes.push(mesh); bounds.expandByObject(mesh);
    });
    const center = bounds.isEmpty() ? new THREE.Vector3() : bounds.getCenter(new THREE.Vector3());
    const radius = Math.max(0.13, bounds.isEmpty() ? 0.2 : bounds.getSize(new THREE.Vector3()).length() / 2);
    camera.position.copy(center).add(new THREE.Vector3(radius * 1.5, -radius * 1.7, radius * 1.3));
    controls.target.copy(center);
    if (view.current?.count === parts.length) {
      camera.position.copy(view.current.camera); controls.target.copy(view.current.target);
    }
    controls.update();
    const raycaster = new THREE.Raycaster(), pointer = new THREE.Vector2();
    const hitPlane = new THREE.Plane(new THREE.Vector3(0, 0, 1), 0);
    let drag: { mesh: THREE.Mesh; x: number; y: number; offset: THREE.Vector3; moved: boolean } | null = null;
    const updateRay = (event: PointerEvent) => {
      const rect = renderer.domElement.getBoundingClientRect();
      pointer.set((event.clientX - rect.left) / rect.width * 2 - 1, -(event.clientY - rect.top) / rect.height * 2 + 1);
      raycaster.setFromCamera(pointer, camera);
    };
    const onDown = (event: PointerEvent) => {
      if (event.button !== 0) return;
      updateRay(event);
      const hit = raycaster.intersectObjects(meshes, false)[0];
      if (!hit) return;
      const mesh = hit.object as THREE.Mesh;
      hitPlane.constant = -mesh.position.z;
      const point = raycaster.ray.intersectPlane(hitPlane, new THREE.Vector3());
      if (!point) return;
      drag = { mesh, x: event.clientX, y: event.clientY, offset: mesh.position.clone().sub(point), moved: false };
      selectRef.current(mesh.name);
      controls.enabled = false;
      renderer.domElement.setPointerCapture(event.pointerId);
    };
    const onMove = (event: PointerEvent) => {
      if (!drag) return;
      if (Math.hypot(event.clientX - drag.x, event.clientY - drag.y) > 4) drag.moved = true;
      if (!drag.moved) return;
      updateRay(event);
      const point = raycaster.ray.intersectPlane(hitPlane, new THREE.Vector3());
      if (!point) return;
      const snap = (value: number) => Math.round(value / 0.005) * 0.005;
      drag.mesh.position.x = snap(point.x + drag.offset.x);
      drag.mesh.position.y = snap(point.y + drag.offset.y);
    };
    const onUp = () => {
      if (!drag) return;
      if (drag.moved) moveRef.current(drag.mesh.name, Math.round(drag.mesh.position.x * 1000), Math.round(drag.mesh.position.y * 1000));
      drag = null; controls.enabled = true;
    };
    renderer.domElement.addEventListener('pointerdown', onDown);
    renderer.domElement.addEventListener('pointermove', onMove);
    renderer.domElement.addEventListener('pointerup', onUp);
    renderer.domElement.addEventListener('pointercancel', onUp);
    const render = () => {
      if (stopped) return;
      const width = Math.max(2, element.clientWidth), height = Math.max(2, element.clientHeight);
      renderer.setSize(width, height, false);
      camera.aspect = width / height; camera.updateProjectionMatrix();
      controls.update();
      for (const mesh of meshes) (mesh.material as THREE.MeshStandardMaterial).emissive.setHex(
        mesh.name === selectedRef.current ? 0x40a8b6 : 0x000000);
      renderer.render(scene, camera);
      frame = requestAnimationFrame(render);
    };
    render();
    return () => {
      stopped = true; cancelAnimationFrame(frame);
      view.current = { count: parts.length, camera: camera.position.clone(), target: controls.target.clone() };
      renderer.domElement.removeEventListener('pointerdown', onDown);
      renderer.domElement.removeEventListener('pointermove', onMove);
      renderer.domElement.removeEventListener('pointerup', onUp);
      renderer.domElement.removeEventListener('pointercancel', onUp);
      controls.dispose();
      meshes.forEach(mesh => { mesh.geometry.dispose(); (mesh.material as THREE.Material).dispose(); });
      renderer.dispose(); renderer.domElement.remove();
    };
  }, [parts]);
  return <div className="model-puzzle-canvas" ref={host} aria-label="拖动零件进行拼装的三维画布" />;
}
