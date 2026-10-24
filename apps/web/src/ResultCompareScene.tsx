import { useEffect, useRef, useState } from 'react';
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { OBJLoader } from 'three/addons/loaders/OBJLoader.js';
import URDFLoader from 'urdf-loader';

export type ResultSceneAssets = { run_id: string; model_path: string;
  assets: { path: string; sha256: string; size: number }[] };

function assetUrl(runId: string, relative: string) {
  return `urdftools://result-asset/${encodeURIComponent(runId)}/` +
    relative.split('/').map(encodeURIComponent).join('/');
}

export function ResultCompareScene({ left, right, leftName, rightName }: {
  left: ResultSceneAssets; right: ResultSceneAssets; leftName: string; rightName: string;
}) {
  const host = useRef<HTMLDivElement>(null);
  const [message, setMessage] = useState('正在加载两个 URDF 模型…');
  useEffect(() => {
    const element = host.current;
    if (!element) return;
    let stopped = false;
    let frame = 0;
    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x192632);
    const camera = new THREE.PerspectiveCamera(45, 1, 0.001, 2000);
    camera.up.set(0, 0, 1);
    const renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    element.appendChild(renderer.domElement);
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    scene.add(new THREE.HemisphereLight(0xffffff, 0x5a7188, 2));
    const sun = new THREE.DirectionalLight(0xffffff, 2);
    sun.position.set(3, -4, 7);
    scene.add(sun);
    const groups = [new THREE.Group(), new THREE.Group()];
    groups.forEach(group => scene.add(group));
    const grid = new THREE.GridHelper(4, 32, 0x6f879a, 0x394c5d);
    grid.rotation.x = Math.PI / 2;
    scene.add(grid);
    const allBounds: (THREE.Box3 | null)[] = [null, null];
    const updateLayout = () => {
      if (!allBounds[0] || !allBounds[1]) return;
      const width = Math.max(allBounds[0].getSize(new THREE.Vector3()).x,
        allBounds[1].getSize(new THREE.Vector3()).x, 0.35);
      const gap = width * 0.3;
      const spacing = width + gap;
      groups.forEach((group, index) => {
        const center = allBounds[index]!.getCenter(new THREE.Vector3());
        group.position.set((index === 0 ? -1 : 1) * spacing / 2 - center.x, -center.y, -allBounds[index]!.min.z);
      });
      const full = new THREE.Box3().setFromObject(groups[0]).union(new THREE.Box3().setFromObject(groups[1]));
      const center = full.getCenter(new THREE.Vector3());
      const radius = Math.max(0.35, full.getSize(new THREE.Vector3()).length() / 2);
      grid.scale.setScalar(Math.max(1, radius));
      camera.position.copy(center).add(new THREE.Vector3(radius * 1.4, -radius * 1.7, radius * 1.15));
      camera.near = Math.max(0.001, radius / 1000);
      camera.far = Math.max(30, radius * 100);
      camera.updateProjectionMatrix();
      controls.target.copy(center);
      controls.update();
      setMessage('左键旋转 · 右键平移 · 滚轮缩放');
    };
    const load = (data: ResultSceneAssets, index: number) => {
      const manager = new THREE.LoadingManager();
      manager.onError = url => { if (!stopped) setMessage('模型网格资源加载失败：' + url); };
      const refreshBounds = () => {
        if (stopped || !groups[index].children.length) return;
        groups[index].position.set(0, 0, 0);
        groups[index].updateMatrixWorld(true);
        const box = new THREE.Box3().setFromObject(groups[index].children[0]);
        if (box.isEmpty()) return;
        allBounds[index] = box;
        updateLayout();
      };
      manager.onLoad = refreshBounds;
      const loader = new URDFLoader(manager);
      const xmlUrl = assetUrl(data.run_id, data.model_path);
      fetch(xmlUrl).then(response => {
        if (!response.ok) throw new Error(`URDF 资源 ${response.status}`);
        return response.text();
      }).then(xml => {
        if (stopped) return;
        const packageRoots = Array.from(xml.matchAll(/package:\/\/([^/"'\s]+)\/([^"'\s]+)/g), match => {
          const asset = data.assets.find(item => item.path.endsWith(match[2]));
          const prefix = asset ? asset.path.slice(0, -match[2].length) : '';
          return [match[1], assetUrl(data.run_id, prefix).replace(/\/$/, '')] as const;
        });
        loader.packages = Object.fromEntries(packageRoots);
        const original = loader.loadMeshCb.bind(loader);
        loader.loadMeshCb = (url, loadingManager, material, complete) => {
          if (/\.obj(?:\?|$)/i.test(url)) {
            new OBJLoader(loadingManager).load(url, object => {
              object.traverse(child => { if (child instanceof THREE.Mesh && material) child.material = material; });
              complete(object);
            }, undefined, cause => complete(null as unknown as THREE.Object3D, cause instanceof Error ? cause : new Error(String(cause))));
          } else original(url, loadingManager, material, complete);
        };
        loader.load(xmlUrl, robot => {
          if (stopped) return;
          robot.traverse(object => {
            if ((object as THREE.Object3D & { isURDFCollider?: boolean }).isURDFCollider) object.visible = false;
          });
          groups[index].add(robot);
          robot.updateMatrixWorld(true);
          refreshBounds();
        }, undefined, cause => { if (!stopped) setMessage('URDF 解析失败：' + String(cause)); });
      }).catch(cause => { if (!stopped) setMessage('URDF 加载失败：' + String(cause)); });
    };
    load(left, 0); load(right, 1);
    const render = () => {
      if (stopped) return;
      const width = Math.max(2, element.clientWidth);
      const height = Math.max(2, element.clientHeight);
      renderer.setSize(width, height, false);
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
      controls.update();
      renderer.render(scene, camera);
      frame = requestAnimationFrame(render);
    };
    render();
    return () => {
      stopped = true;
      cancelAnimationFrame(frame);
      controls.dispose();
      groups.forEach(group => group.traverse(object => {
        if (object instanceof THREE.Mesh) {
          object.geometry?.dispose();
          (Array.isArray(object.material) ? object.material : [object.material]).forEach(material => material?.dispose());
        }
      }));
      renderer.dispose();
      renderer.domElement.remove();
    };
  }, [left, right]);
  return <div className="result-scene"><div className="result-scene-labels"><span>待分析 · {leftName}</span><span>标准 · {rightName}</span></div>
    <div ref={host} className="result-scene-canvas" /><p role="status">{message}</p></div>;
}
