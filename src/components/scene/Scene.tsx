import { Environment, Lightformer } from "@react-three/drei";
import { useThree } from "@react-three/fiber";
import { useEffect } from "react";

import { BitcoinCoin } from "./BitcoinCoin";
import { CameraRig } from "./CameraRig";
import { NetworkField } from "./NetworkField";
import { Particles } from "./Particles";
import { TransactionPath } from "./TransactionPath";

interface SceneProps {
  reducedMotion?: boolean;
}

/**
 * Forces every material in the scene to compile its WebGL shader program up
 * front, at mount, instead of lazily the first time each object actually
 * becomes visible.
 *
 * BitcoinCoin and TransactionPath sit at `visible={false}` (or opacity 0)
 * until scroll crosses their reveal point — BitcoinCoin's meshStandardMaterial
 * (a PBR shader, the most expensive kind to compile) first renders at
 * progress ~0.14, right where beat 01 hands off to beat 02. Compiling a new
 * shader program blocks the main thread for tens to hundreds of
 * milliseconds, which is exactly the "sticks for a second" felt while
 * scrolling through phase 1. `gl.compile()` walks the whole scene graph
 * (visibility does not stop traversal) and compiles every program during the
 * still frame right after mount, before the user has scrolled at all, so
 * every later reveal — the coin, the TRON transaction path — is just an
 * already-compiled draw call.
 */
function ShaderWarmup() {
  const { gl, scene, camera } = useThree();
  useEffect(() => {
    gl.compile(scene, camera);
  }, [gl, scene, camera]);
  return null;
}

export function Scene({ reducedMotion = false }: SceneProps) {
  return (
    <>
      <color attach="background" args={["#04060c"]} />
      <fog attach="fog" args={["#04060c", 34, 150]} />

      <ambientLight intensity={reducedMotion ? 0.55 : 0.35} />
      <directionalLight
        position={[8, 12, 10]}
        intensity={reducedMotion ? 1.6 : 2.1}
        color="#ffd9a0"
      />
      <directionalLight
        position={[-10, -4, -8]}
        intensity={0.9}
        color="#3ba7ff"
      />
      <pointLight
        position={[0, 0, 6]}
        intensity={reducedMotion ? 14 : 22}
        distance={30}
        color="#ffb64a"
      />

      <Environment resolution={reducedMotion ? 64 : 128}>
        <Lightformer
          intensity={reducedMotion ? 1.6 : 2.4}
          position={[0, 6, 4]}
          scale={[12, 12, 1]}
          color="#fff0d4"
        />
        <Lightformer
          intensity={1.4}
          color="#3ba7ff"
          position={[-8, 0, 2]}
          rotation-y={Math.PI / 2}
          scale={[22, 6, 1]}
        />
        <Lightformer
          intensity={1.1}
          color="#22e0ff"
          position={[8, -2, -2]}
          rotation-y={-Math.PI / 2}
          scale={[22, 6, 1]}
        />
      </Environment>

      <CameraRig reducedMotion={reducedMotion} />
      <Particles reducedMotion={reducedMotion} />
      <NetworkField reducedMotion={reducedMotion} />
      <BitcoinCoin reducedMotion={reducedMotion} />
      <TransactionPath reducedMotion={reducedMotion} />
      <ShaderWarmup />
    </>
  );
}
