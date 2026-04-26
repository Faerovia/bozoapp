"use client";

/**
 * Touch + mouse signature pad — vrátí PNG jako data URL.
 * Žádný external dep (žádný react-signature-canvas) — minimal HTML5 canvas.
 *
 * Použití:
 *   <SignaturePad onChange={(dataUrl) => setSignature(dataUrl)} />
 *
 * Klient by měl validovat min. počet bodů (např. 50) ať nejde o prázdný canvas.
 */

import { useEffect, useRef, useState } from "react";
import { RotateCcw } from "lucide-react";

interface SignaturePadProps {
  onChange?: (dataUrl: string | null) => void;
  width?: number;
  height?: number;
  strokeColor?: string;
  strokeWidth?: number;
}

export function SignaturePad({
  onChange,
  width = 500,
  height = 200,
  strokeColor = "#1f2937",
  strokeWidth = 2,
}: SignaturePadProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const drawingRef = useRef(false);
  const lastRef = useRef<{ x: number; y: number } | null>(null);
  const pointsRef = useRef(0);
  const [hasContent, setHasContent] = useState(false);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    // White bg pro PNG (jinak by byl transparentní = na PDF špatně viditelný)
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    ctx.strokeStyle = strokeColor;
    ctx.lineWidth = strokeWidth;
  }, [strokeColor, strokeWidth]);

  function getPos(e: React.PointerEvent<HTMLCanvasElement>) {
    const canvas = canvasRef.current!;
    const rect = canvas.getBoundingClientRect();
    return {
      x: ((e.clientX - rect.left) * canvas.width) / rect.width,
      y: ((e.clientY - rect.top) * canvas.height) / rect.height,
    };
  }

  function handlePointerDown(e: React.PointerEvent<HTMLCanvasElement>) {
    e.preventDefault();
    const canvas = canvasRef.current!;
    canvas.setPointerCapture(e.pointerId);
    drawingRef.current = true;
    lastRef.current = getPos(e);
  }

  function handlePointerMove(e: React.PointerEvent<HTMLCanvasElement>) {
    if (!drawingRef.current) return;
    const canvas = canvasRef.current!;
    const ctx = canvas.getContext("2d");
    if (!ctx || !lastRef.current) return;
    const pos = getPos(e);
    ctx.beginPath();
    ctx.moveTo(lastRef.current.x, lastRef.current.y);
    ctx.lineTo(pos.x, pos.y);
    ctx.stroke();
    lastRef.current = pos;
    pointsRef.current += 1;
    if (!hasContent && pointsRef.current > 5) {
      setHasContent(true);
      onChange?.(canvas.toDataURL("image/png"));
    }
  }

  function handlePointerUp() {
    if (!drawingRef.current) return;
    drawingRef.current = false;
    lastRef.current = null;
    const canvas = canvasRef.current;
    if (canvas && hasContent) {
      onChange?.(canvas.toDataURL("image/png"));
    }
  }

  function handleClear() {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    pointsRef.current = 0;
    setHasContent(false);
    onChange?.(null);
  }

  return (
    <div className="space-y-2">
      <div className="relative rounded-md border-2 border-dashed border-gray-300 bg-white">
        <canvas
          ref={canvasRef}
          width={width}
          height={height}
          className="block w-full touch-none cursor-crosshair"
          style={{ height: `${height}px`, maxHeight: `${height}px` }}
          onPointerDown={handlePointerDown}
          onPointerMove={handlePointerMove}
          onPointerUp={handlePointerUp}
          onPointerCancel={handlePointerUp}
          onPointerLeave={handlePointerUp}
        />
        {!hasContent && (
          <div className="pointer-events-none absolute inset-0 flex items-center justify-center text-sm text-gray-400">
            Podepište prstem nebo myší
          </div>
        )}
      </div>
      <div className="flex items-center justify-between">
        <span className="text-xs text-gray-500">
          {hasContent ? "Podpis je připraven k odeslání." : "Zatím prázdné"}
        </span>
        <button
          type="button"
          onClick={handleClear}
          className="flex items-center gap-1 rounded-md px-2 py-1 text-xs text-gray-600 hover:bg-gray-100"
        >
          <RotateCcw className="h-3 w-3" />
          Vymazat
        </button>
      </div>
    </div>
  );
}
