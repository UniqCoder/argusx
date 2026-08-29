import React, { useEffect, useRef } from "react";
import * as THREE from "three";

interface HeroRightProps {
  opacity: number;
  mouseX: number;
  mouseY: number;
}

export const HeroRight: React.FC<HeroRightProps> = ({
  opacity,
  mouseX,
  mouseY,
}) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const sceneRef = useRef<{
    scene: THREE.Scene;
    camera: THREE.PerspectiveCamera;
    renderer: THREE.WebGLRenderer;
    coin: THREE.Group;
    rafId: number;
  }>();

  useEffect(() => {
    if (!canvasRef.current) return;

    // Scene setup
    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(45, 1, 0.1, 1000);
    camera.position.z = 5;

    const renderer = new THREE.WebGLRenderer({
      canvas: canvasRef.current,
      antialias: true,
      alpha: true,
    });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setClearColor(0x000000, 0);

    // Create Bitcoin coin
    const coinGroup = new THREE.Group();

    // Main cylinder (coin body)
    const coinGeometry = new THREE.CylinderGeometry(1, 1, 0.15, 64);
    const coinMaterial = new THREE.MeshStandardMaterial({
      color: 0xf5a524,
      metalness: 0.8,
      roughness: 0.2,
      emissive: 0xf5a524,
      emissiveIntensity: 0.1,
    });
    const coin = new THREE.Mesh(coinGeometry, coinMaterial);
    coin.rotation.x = Math.PI / 2;
    coinGroup.add(coin);

    // Edge ring for detail
    const edgeGeometry = new THREE.TorusGeometry(1, 0.08, 16, 64);
    const edgeMaterial = new THREE.MeshStandardMaterial({
      color: 0xd68910,
      metalness: 0.9,
      roughness: 0.1,
    });
    const edge = new THREE.Mesh(edgeGeometry, edgeMaterial);
    coinGroup.add(edge);

    // Bitcoin symbol (simplified ₿)
    const symbolShape = new THREE.Shape();
    symbolShape.moveTo(0, 0.5);
    symbolShape.lineTo(0, -0.5);
    const symbolGeometry = new THREE.ExtrudeGeometry(symbolShape, {
      depth: 0.05,
      bevelEnabled: false,
    });
    const symbolMaterial = new THREE.MeshStandardMaterial({
      color: 0x050810,
      metalness: 0.3,
      roughness: 0.7,
    });
    const symbol = new THREE.Mesh(symbolGeometry, symbolMaterial);
    symbol.position.z = 0.08;
    coinGroup.add(symbol);

    scene.add(coinGroup);

    // Lights
    const ambientLight = new THREE.AmbientLight(0xffffff, 0.4);
    scene.add(ambientLight);

    const pointLight1 = new THREE.PointLight(0x22d3ee, 1.5, 100);
    pointLight1.position.set(3, 3, 3);
    scene.add(pointLight1);

    const pointLight2 = new THREE.PointLight(0xf5a524, 1.5, 100);
    pointLight2.position.set(-3, -3, 3);
    scene.add(pointLight2);

    // Store refs
    sceneRef.current = {
      scene,
      camera,
      renderer,
      coin: coinGroup,
      rafId: 0,
    };

    // Resize handler
    const handleResize = () => {
      if (!canvasRef.current || !sceneRef.current) return;
      const { width, height } = canvasRef.current.getBoundingClientRect();
      sceneRef.current.renderer.setSize(width, height);
      sceneRef.current.camera.aspect = width / height;
      sceneRef.current.camera.updateProjectionMatrix();
    };
    handleResize();
    window.addEventListener("resize", handleResize);

    // Animation loop
    const animate = () => {
      if (!sceneRef.current) return;

      sceneRef.current.rafId = requestAnimationFrame(animate);

      // Idle rotation
      sceneRef.current.coin.rotation.y += 0.005;

      sceneRef.current.renderer.render(
        sceneRef.current.scene,
        sceneRef.current.camera,
      );
    };
    animate();

    return () => {
      window.removeEventListener("resize", handleResize);
      if (sceneRef.current) {
        cancelAnimationFrame(sceneRef.current.rafId);
        sceneRef.current.renderer.dispose();
      }
    };
  }, []);

  // Update tilt based on mouse position
  useEffect(() => {
    if (!sceneRef.current) return;

    const targetRotationX = mouseY * 0.3;
    const targetRotationY = mouseX * 0.3;

    // Smooth interpolation
    const currentRotation = sceneRef.current.coin.rotation;
    currentRotation.x += (targetRotationX - currentRotation.x) * 0.1;
    currentRotation.z += (targetRotationY - currentRotation.z) * 0.1;
  }, [mouseX, mouseY]);

  return (
    <div
      className="absolute inset-0 flex items-center justify-center pointer-events-none"
      style={{ opacity }}
    >
      <canvas
        ref={canvasRef}
        className="w-full h-full"
        style={{ maxWidth: "600px", maxHeight: "600px" }}
      />
    </div>
  );
};
