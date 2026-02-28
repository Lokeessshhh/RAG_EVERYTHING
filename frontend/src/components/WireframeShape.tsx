import { useRef, useState } from 'react';
import { Canvas, useFrame } from '@react-three/fiber';
import { PerspectiveCamera } from '@react-three/drei';
import { useTheme } from '../hooks/useTheme';

function Shape() {
  const meshRef = useRef<any>();
  const [hovered, setHovered] = useState(false);
  const { theme } = useTheme();
  
  useFrame((_state, delta) => {
    if (document.hidden) return;
    if (meshRef.current) {
      const speed = hovered ? 2.5 : 0.5;
      meshRef.current.rotation.y += delta * speed;
      meshRef.current.rotation.x += delta * speed * 0.3;
    }
  });

  return (
    <mesh 
      ref={meshRef} 
      onPointerOver={() => setHovered(true)}
      onPointerOut={() => setHovered(false)}
    >
      <icosahedronGeometry args={[2, 1]} />
      <meshBasicMaterial 
        wireframe 
        color={theme === 'dark' ? '#2ECC8A' : '#1A6B4A'} 
        transparent 
        opacity={0.8}
      />
    </mesh>
  );
}

export const WireframeShape = () => {
  return (
    <div className="w-full h-[400px]">
      <Canvas>
        <PerspectiveCamera makeDefault position={[0, 0, 5]} />
        <ambientLight intensity={0.5} />
        <Shape />
      </Canvas>
    </div>
  );
};
