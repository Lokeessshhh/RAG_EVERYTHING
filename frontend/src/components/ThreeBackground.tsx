import { useRef, useMemo } from 'react';
import { Canvas, useFrame } from '@react-three/fiber';
import { Points, PointMaterial } from '@react-three/drei';

function ParticleField() {
  const ref = useRef<any>();
  
  const points = useMemo(() => {
    const p = new Float32Array(200 * 3);
    for (let i = 0; i < 200; i++) {
      p[i * 3] = (Math.random() - 0.5) * 10;
      p[i * 3 + 1] = (Math.random() - 0.5) * 10;
      p[i * 3 + 2] = (Math.random() - 0.5) * 10;
    }
    return p;
  }, []);

  useFrame((_state, delta) => {
    if (document.hidden) return;
    if (ref.current) {
      ref.current.rotation.x -= delta / 10;
      ref.current.rotation.y -= delta / 15;
    }
  });

  return (
    <group rotation={[0, 0, Math.PI / 4]}>
      <Points ref={ref} positions={points} stride={3} frustumCulled={false}>
        <PointMaterial
          transparent
          color="#2ECC8A"
          size={0.05}
          sizeAttenuation={true}
          depthWrite={false}
        />
      </Points>
    </group>
  );
}

export const ThreeBackground = () => {
  return (
    <div className="absolute inset-0 -z-10 bg-bg transition-colors duration-500 overflow-hidden">
      {/* Texture overlay for light mode */}
      <div className="absolute inset-0 opacity-[0.03] pointer-events-none dark:hidden" style={{ backgroundImage: 'url("https://www.transparenttextures.com/patterns/felt.png")' }}></div>
      <div className="absolute inset-0 bg-gradient-to-tr from-accent-glow via-transparent to-transparent opacity-50"></div>
      
      {/* Dark mode particles */}
      <div className="hidden dark:block w-full h-full">
        <Canvas camera={{ position: [0, 0, 5] }}>
          <ParticleField />
        </Canvas>
      </div>
      
      {/* Light mode glow */}
      <div className="block dark:hidden w-full h-full">
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[800px] h-[800px] bg-accent-light rounded-full blur-[120px] opacity-30"></div>
      </div>
    </div>
  );
};
