"use client";

import { useEffect, useRef } from "react";

interface SparklineProps {
  data: number[];
  width?: number;
  height?: number;
}

/** Pixel-styled canvas sparkline (clean-room, green screen look). */
export function Sparkline({ data, width = 224, height = 46 }: SparklineProps) {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const cv = ref.current;
    if (!cv) return;
    const ctx = cv.getContext("2d");
    if (!ctx) return;
    const W = cv.width;
    const H = cv.height;
    ctx.clearRect(0, 0, W, H);

    // dotted baseline grid
    ctx.fillStyle = "rgba(63,138,89,.25)";
    for (let y = 10; y < H; y += 12) for (let x = 0; x < W; x += 5) ctx.fillRect(x, y, 2, 1);

    const pts = data.length > 1 ? data : [0, 0];
    let mn = Math.min(...pts);
    let mx = Math.max(...pts);
    if (mx === mn) {
      mx += 1;
      mn -= 1;
    }
    const pad = 6;
    const X = (i: number) => (i / (pts.length - 1)) * (W - pad * 2) + pad;
    const Y = (v: number) => H - pad - ((v - mn) / (mx - mn)) * (H - pad * 2);

    // area fill
    ctx.beginPath();
    ctx.moveTo(X(0), H);
    pts.forEach((v, i) => ctx.lineTo(X(i), Y(v)));
    ctx.lineTo(X(pts.length - 1), H);
    ctx.closePath();
    ctx.fillStyle = "rgba(111,224,140,.16)";
    ctx.fill();

    // line
    ctx.beginPath();
    pts.forEach((v, i) => (i ? ctx.lineTo(X(i), Y(v)) : ctx.moveTo(X(i), Y(v))));
    ctx.strokeStyle = "#6fe08c";
    ctx.lineWidth = 2;
    ctx.lineJoin = "round";
    ctx.stroke();

    // head dot
    const lx = X(pts.length - 1);
    const ly = Y(pts[pts.length - 1] ?? 0);
    ctx.fillStyle = "#d7ffe2";
    ctx.fillRect(lx - 2, ly - 2, 4, 4);
  }, [data]);

  return <canvas ref={ref} width={width} height={height} className="pix-spark" />;
}
