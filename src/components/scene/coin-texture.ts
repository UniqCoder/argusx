import * as THREE from "three";

/**
 * Engraved coin face: circuitry traces + ₿ glyph.
 * Used as colour + emissive + roughness source so the coin reads as a
 * machined metal object rather than a flat disc.
 */
export function createCoinTexture(): THREE.CanvasTexture {
  const size = 1024;
  const c = document.createElement("canvas");
  c.width = c.height = size;
  const ctx = c.getContext("2d")!;
  const mid = size / 2;

  const base = ctx.createRadialGradient(
    mid * 0.7,
    mid * 0.6,
    40,
    mid,
    mid,
    mid,
  );
  base.addColorStop(0, "#6a5426");
  base.addColorStop(0.45, "#c98d21");
  base.addColorStop(0.75, "#8a5f16");
  base.addColorStop(1, "#3a2708");
  ctx.fillStyle = base;
  ctx.fillRect(0, 0, size, size);

  // milled rim
  ctx.strokeStyle = "rgba(255, 226, 160, 0.55)";
  ctx.lineWidth = 10;
  ctx.beginPath();
  ctx.arc(mid, mid, mid * 0.93, 0, Math.PI * 2);
  ctx.stroke();
  ctx.lineWidth = 3;
  for (let i = 0; i < 180; i++) {
    const a = (i / 180) * Math.PI * 2;
    ctx.beginPath();
    ctx.moveTo(mid + Math.cos(a) * mid * 0.94, mid + Math.sin(a) * mid * 0.94);
    ctx.lineTo(mid + Math.cos(a) * mid * 0.99, mid + Math.sin(a) * mid * 0.99);
    ctx.stroke();
  }

  // engraved circuitry
  let seed = 7;
  const rnd = () => (seed = (seed * 1664525 + 1013904223) >>> 0) / 4294967296;
  ctx.lineCap = "round";
  for (let i = 0; i < 90; i++) {
    const a = rnd() * Math.PI * 2;
    let r = mid * (0.18 + rnd() * 0.7);
    let x = mid + Math.cos(a) * r;
    let y = mid + Math.sin(a) * r;
    ctx.beginPath();
    ctx.moveTo(x, y);
    const steps = 2 + Math.floor(rnd() * 4);
    for (let s = 0; s < steps; s++) {
      const horiz = rnd() > 0.5;
      const len = 20 + rnd() * 110;
      x += horiz ? (rnd() > 0.5 ? len : -len) : 0;
      y += horiz ? 0 : rnd() > 0.5 ? len : -len;
      if (Math.hypot(x - mid, y - mid) > mid * 0.88) break;
      ctx.lineTo(x, y);
    }
    ctx.strokeStyle =
      rnd() > 0.6 ? "rgba(255,214,132,0.85)" : "rgba(46,30,6,0.75)";
    ctx.lineWidth = 2 + rnd() * 4;
    ctx.stroke();
    ctx.beginPath();
    ctx.arc(x, y, 4 + rnd() * 5, 0, Math.PI * 2);
    ctx.fillStyle = "rgba(255,236,190,0.8)";
    ctx.fill();
  }

  // glyph
  ctx.save();
  ctx.translate(mid, mid);
  ctx.font = `bold ${size * 0.58}px Georgia, serif`;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillStyle = "rgba(28,17,2,0.65)";
  ctx.fillText("₿", 6, size * 0.02 + 8);
  ctx.fillStyle = "#ffe6ac";
  ctx.fillText("₿", 0, size * 0.02);
  ctx.restore();

  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.anisotropy = 4;
  return tex;
}
