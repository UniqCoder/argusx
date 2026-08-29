import React, { useRef, useEffect } from "react";

interface GalleryCardProps {
  children: React.ReactNode;
  x: number; // percentage
  y: number; // percentage
  index: number;
  scale: number; // updated from RAF loop
}

export const GalleryCard: React.FC<GalleryCardProps> = ({
  children,
  x,
  y,
  index,
  scale,
}) => {
  const cardRef = useRef<HTMLDivElement>(null);

  return (
    <div
      ref={cardRef}
      className="absolute bp-card"
      style={{
        left: `${x}%`,
        top: `${y}%`,
        width: "380px",
        height: "280px",
        transform: `translate(-50%, -50%) scale(${scale})`,
        transformOrigin: "center center",
        opacity: scale,
        transition: "none", // RAF-driven, no CSS transition
      }}
    >
      <div className="w-full h-full">{children}</div>
    </div>
  );
};
