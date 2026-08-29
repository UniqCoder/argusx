import { Environment, Lightformer } from "@react-three/drei";

import { BitcoinCoin } from "./BitcoinCoin";
import { CameraRig } from "./CameraRig";
import { NetworkField } from "./NetworkField";
import { Particles } from "./Particles";
import { TransactionPath } from "./TransactionPath";

interface SceneProps {
  reducedMotion?: boolean;
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
    </>
  );
}
