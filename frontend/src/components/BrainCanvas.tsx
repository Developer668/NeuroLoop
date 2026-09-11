"use client";
import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { Maximize2, RotateCcw } from "lucide-react";

type Surface = { name: string; positions: number[]; indices: number[] };
type BrainMesh = THREE.Mesh<THREE.BufferGeometry, THREE.MeshStandardMaterial>;

export default function BrainCanvas({
  evaluationId,
  frame = 0,
  publicMesh = false,
  cinematic = false,
  comparisonId,
}: {
  evaluationId?: string;
  frame?: number;
  publicMesh?: boolean;
  cinematic?: boolean;
  comparisonId?: string;
}) {
  const container = useRef<HTMLDivElement>(null);
  const view = useRef<{
    meshes: BrainMesh[];
    render: () => void;
    reset: () => void;
    display: (mode: string, split: boolean) => void;
  } | null>(null);
  const [mode, setMode] = useState(cinematic ? "points" : "surface");
  const [split, setSplit] = useState(false);
  const [range, setRange] = useState<number[] | null>(null);
  const [status, setStatus] = useState("Loading anatomical surface");
  const [time, setTime] = useState<number | null>(null);
  const [vertex, setVertex] = useState<number | null>(null);
  const [ready, setReady] = useState(false);
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    const host = container.current;
    if (!host) return;
    setReady(false);
    setStatus("Loading anatomical surface");
    let disposed = false;
    let renderer: THREE.WebGLRenderer | undefined;
    let controls: OrbitControls | undefined;
    let observer: ResizeObserver | undefined;
    let pick: ((event: PointerEvent) => void) | undefined;
    let meshes: BrainMesh[] = [];
    let cloudMaterials: THREE.PointsMaterial[] = [];
    let animation = 0,
      visibility: IntersectionObserver | undefined;
    const controller = new AbortController();
    (async () => {
      try {
        const response = await fetch(
          publicMesh ? "/fsaverage5.json" : "/api/geometry",
          { signal: controller.signal },
        );
        if (!response.ok)
          throw new Error("Verified cortical mesh is unavailable");
        const data: { hemispheres: Surface[] } = await response.json();
        if (disposed) return;
        renderer = new THREE.WebGLRenderer({
          antialias: true,
          alpha: true,
          powerPreference: "low-power",
        });
        renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.5));
        renderer.setClearColor(0x000000, 0);
        renderer.outputColorSpace = THREE.SRGBColorSpace;
        host.appendChild(renderer.domElement);
        const scene = new THREE.Scene();
        scene.add(new THREE.AmbientLight(0xffffff, 1.45));
        const light = new THREE.DirectionalLight(0xe8f6ff, 3.0);
        light.position.set(130, 180, 180);
        scene.add(light);
        const fill = new THREE.DirectionalLight(0xb5dce8, 1.25);
        fill.position.set(-140, 20, -100);
        scene.add(fill);
        const group = new THREE.Group();
        data.hemispheres.forEach((surface, idx) => {
          const geometry = new THREE.BufferGeometry();
          geometry.setAttribute(
            "position",
            new THREE.Float32BufferAttribute(surface.positions, 3),
          );
          geometry.setIndex(surface.indices);
          geometry.computeVertexNormals();
          const colors = new Float32Array(surface.positions.length);
          const base = new THREE.Color(cinematic ? "#3c8297" : "#89bbc8");
          for (let i = 0; i < colors.length; i += 3) {
            colors[i] = base.r;
            colors[i + 1] = base.g;
            colors[i + 2] = base.b;
          }
          geometry.setAttribute("color", new THREE.BufferAttribute(colors, 3));
          const material = new THREE.MeshStandardMaterial({
            vertexColors: true,
            roughness: 0.6,
            metalness: 0.12,
            side: THREE.DoubleSide,
          });
          const mesh = new THREE.Mesh(geometry, material);
          mesh.userData.offset = idx * 10242;
          meshes.push(mesh);
          group.add(mesh);
          const pointMaterial = new THREE.PointsMaterial({
            size: cinematic ? 1.0 : 1.15,
            vertexColors: true,
            sizeAttenuation: true,
            transparent: true,
            opacity: 0.86,
          });
          cloudMaterials.push(pointMaterial);
          const cloud = new THREE.Points(geometry, pointMaterial);
          cloud.visible = cinematic;
          mesh.visible = !cinematic;
          mesh.userData.cloud = cloud;
          group.add(cloud);
        });
        group.rotation.x = -Math.PI / 2;
        const center = new THREE.Box3()
          .setFromObject(group)
          .getCenter(new THREE.Vector3());
        group.position.sub(center);
        scene.add(group);
        const camera = new THREE.PerspectiveCamera(36, 1, 0.1, 2000);
        camera.position.set(185, 88, 230);
        controls = new OrbitControls(camera, renderer.domElement);
        controls.enableDamping = false;
        controls.enablePan = false;
        controls.minDistance = 190;
        controls.maxDistance = 480;
        const render = () => renderer?.render(scene, camera);
        const resize = () => {
          if (!renderer) return;
          const width = host.clientWidth,
            height = host.clientHeight;
          renderer.setSize(width, height);
          camera.aspect = width / Math.max(height, 1);
          camera.updateProjectionMatrix();
          render();
        };
        controls.addEventListener("change", render);
        observer = new ResizeObserver(resize);
        observer.observe(host);
        resize();
        view.current = {
          meshes,
          render,
          display: (mode, split) => {
            meshes.forEach((m, i) => {
              m.visible = mode !== "points";
              m.material.wireframe = mode === "wireframe";
              m.material.opacity = mode === "wireframe" ? 0.45 : 1;
              m.material.transparent = mode === "wireframe";
              const cloud = m.userData.cloud as THREE.Points;
              cloud.visible = mode === "points";
              m.position.x = split ? (i === 0 ? -22 : 22) : 0;
              cloud.position.copy(m.position);
            });
            render();
          },
          reset: () => {
            camera.position.set(185, 88, 230);
            controls?.target.set(0, 0, 0);
            controls?.update();
            render();
          },
        };
        if (
          cinematic &&
          !window.matchMedia("(prefers-reduced-motion: reduce)").matches
        ) {
          let onscreen = true,
            previous = 0;
          const tick = (now: number) => {
            if (disposed) return;
            animation = requestAnimationFrame(tick);
            if (!onscreen || document.hidden || now - previous < 50) return;
            previous = now;
            group.rotation.z += 0.0014;
            render();
          };
          visibility = new IntersectionObserver((entries) => {
            onscreen = entries[0].isIntersecting;
          });
          visibility.observe(host);
          animation = requestAnimationFrame(tick);
        }
        const ray = new THREE.Raycaster();
        pick = (event: PointerEvent) => {
          if (event.button !== 0 || !renderer) return;
          const rect = renderer.domElement.getBoundingClientRect();
          const pointer = new THREE.Vector2(
            ((event.clientX - rect.left) / rect.width) * 2 - 1,
            (-(event.clientY - rect.top) / rect.height) * 2 + 1,
          );
          ray.setFromCamera(pointer, camera);
          const hit = ray.intersectObjects(meshes)[0];
          if (hit?.face)
            setVertex(hit.face.a + Number(hit.object.userData.offset));
        };
        renderer.domElement.addEventListener("pointerdown", pick);
        setStatus("");
        setReady(true);
      } catch (error) {
        if (!disposed)
          setStatus(
            error instanceof Error
              ? error.message
              : "3D rendering is unavailable",
          );
      }
    })();
    return () => {
      disposed = true;
      controller.abort();
      cancelAnimationFrame(animation);
      visibility?.disconnect();
      cloudMaterials.forEach((m) => m.dispose());
      observer?.disconnect();
      controls?.dispose();
      if (pick) renderer?.domElement.removeEventListener("pointerdown", pick);
      meshes.forEach((m) => {
        m.geometry.dispose();
        m.material.dispose();
      });
      renderer?.dispose();
      if (renderer?.domElement.parentNode === host)
        host.removeChild(renderer.domElement);
      view.current = null;
    };
  }, [publicMesh, cinematic, retry]);
  useEffect(() => {
    view.current?.display(mode, split);
  }, [mode, split, ready]);
  useEffect(() => {
    if (!evaluationId) {
      setTime(null);
      setRange(null);
      return;
    }
    if (!ready) return;
    const controller = new AbortController();
    const paint = async () => {
      try {
        const response = await fetch(
          `/api/evaluations/${evaluationId}/frame?index=${frame}${comparisonId ? `&reference=${encodeURIComponent(comparisonId)}` : ""}`,
          { signal: controller.signal },
        );
        if (!response.ok) {
          const problem = await response.json().catch(() => ({}));
          throw new Error(
            problem.detail ||
              "Response frame is unavailable. Retry to reconnect.",
          );
        }
        const data: { values: number[]; range: number[]; time: number } =
          await response.json();
        if (data.values.length !== 20484)
          throw new Error("Cortical data and surface do not match");
        if (controller.signal.aborted || !view.current) return;
        const limit = Math.max(
          Math.abs(data.range[0]),
          Math.abs(data.range[1]),
          0.001,
        );
        const low = new THREE.Color("#426bb2"),
          mid = new THREE.Color("#e4eef0"),
          high = new THREE.Color("#158e87");
        const c = new THREE.Color();
        view.current.meshes.forEach((mesh) => {
          const colors = mesh.geometry.getAttribute(
            "color",
          ) as THREE.BufferAttribute;
          const offset = Number(mesh.userData.offset);
          for (let i = 0; i < colors.count; i++) {
            const v = Math.max(
              -1,
              Math.min(1, data.values[i + offset] / limit),
            );
            c.copy(mid).lerp(v >= 0 ? high : low, Math.abs(v));
            colors.setXYZ(i, c.r, c.g, c.b);
          }
          colors.needsUpdate = true;
        });
        view.current.render();
        setTime(data.time);
        setRange([-limit, limit]);
        setStatus("");
      } catch (error) {
        if (!controller.signal.aborted)
          setStatus(
            error instanceof Error ? error.message : "Unable to read response",
          );
      }
    };
    void paint();
    return () => controller.abort();
  }, [evaluationId, frame, comparisonId, ready]);
  return (
    <div className="brain-stage">
      <div className="brain-stage-top">
        <span>FSAVERAGE5 / CORTEX</span>
        <div>
          <button
            className="icon-button"
            aria-label="Reset brain view"
            onClick={() => view.current?.reset()}
          >
            <RotateCcw size={15} />
          </button>
          <button
            className="icon-button"
            aria-label="Expand brain view"
            onClick={() => {
              const result =
                container.current?.parentElement?.requestFullscreen?.();
              result?.catch(() =>
                setStatus("Fullscreen is unavailable in this browser"),
              );
            }}
          >
            <Maximize2 size={15} />
          </button>
        </div>
      </div>
      <div className="brain-canvas" ref={container} />
      {status && (
        <div className="brain-message" role="status">
          {status}
          {!status.startsWith("Loading") && (
            <button className="button" onClick={() => setRetry((n) => n + 1)}>
              Retry brain view
            </button>
          )}
        </div>
      )}
      <div className="brain-display-controls">
        <div
          className="brain-mode-group"
          role="group"
          aria-label="Surface display mode"
        >
          {["surface", "points", "wireframe"].map((m) => (
            <button
              key={m}
              className={mode === m ? "selected" : ""}
              onClick={() => setMode(m)}
              aria-pressed={mode === m}
            >
              {m.charAt(0).toUpperCase() + m.slice(1)}
            </button>
          ))}
        </div>
        <label
          className="hemisphere-toggle"
          title="Adds space between the hemispheres in any display mode"
        >
          <input
            type="checkbox"
            checked={split}
            onChange={(e) => setSplit(e.target.checked)}
          />
          <span>Spread hemispheres</span>
        </label>
      </div>
      {range && (
        <div className="brain-scale">
          <span>Model-response units</span>
          <i />
          <div>
            <span>{range[0].toFixed(2)}</span>
            <span>{range[1].toFixed(2)}</span>
          </div>
        </div>
      )}
      <div className="brain-stage-bottom">
        <span>
          {time === null
            ? "ANATOMY ONLY"
            : `${comparisonId ? "DIFFERENCE" : "RESPONSE"} AT ${time.toFixed(1)}s`}
          {vertex !== null ? ` · VERTEX ${vertex}` : ""}
        </span>
        <span>Drag to rotate</span>
      </div>
    </div>
  );
}
