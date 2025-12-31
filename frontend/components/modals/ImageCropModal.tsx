'use client';

import React, { useCallback, useEffect, useRef, useState } from 'react';
import Modal from '@/components/Modal';
import { logger } from '@/lib/logger';

interface ImageCropModalProps {
  isOpen: boolean;
  file: File | null;
  onClose: () => void;
  onCropped: (blob: Blob) => void;
  /** viewport (visible square) size in px */
  viewportSize?: number;
  /** output size in px (square) */
  outputSize?: number;
}

/**
 * Lightweight avatar cropper with zoom and pan.
 * - Always outputs a square JPEG on a white background
 * - No external dependencies
 */
export default function ImageCropModal({
  isOpen,
  file,
  onClose,
  onCropped,
  viewportSize = 320,
  outputSize = 800,
}: ImageCropModalProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [image, setImage] = useState<HTMLImageElement | null>(null);
  const [natural, setNatural] = useState<{ w: number; h: number } | null>(null);
  const [scale, setScale] = useState(1); // absolute scale applied to the image
  const [minScale, setMinScale] = useState(0.5);
  const [maxScale, setMaxScale] = useState(4);
  const [offset, setOffset] = useState({ x: 0, y: 0 }); // translation in px in viewport space
  const [dragStart, setDragStart] = useState<{ x: number; y: number } | null>(null);

  // Load image when file changes
  useEffect(() => {
    if (!file) {
      queueMicrotask(() => {
        setImage(null);
        setNatural(null);
        setScale(1);
        setMinScale(0.5);
        setMaxScale(4);
        setOffset({ x: 0, y: 0 });
        setDragStart(null);
      });
      return;
    }
    const url = URL.createObjectURL(file);
    const img = new Image();
    img.onload = () => {
      setImage(img);
      setNatural({ w: img.naturalWidth, h: img.naturalHeight });
      // Compute min scale to CONTAIN entire image in the viewport
      const contain = Math.min(viewportSize / img.naturalWidth, viewportSize / img.naturalHeight);
      const cover = Math.max(viewportSize / img.naturalWidth, viewportSize / img.naturalHeight);
      // Start slightly above contain so the image is comfortably visible
      // and not too tiny at first; user can still zoom out back to contain via slider
      setScale(contain * 1.15);
      setMinScale(contain);
      // Allow substantial zoom-in (beyond original pixel size if desired)
      setMaxScale(Math.max(3, cover * 10));
      setOffset({ x: 0, y: 0 });
    };
    img.onerror = () => {
      logger.error('Failed to load image for cropping');
    };
    img.src = url;
    return () => URL.revokeObjectURL(url);
  }, [file, viewportSize]);

  const currentScale = scale;

  // Clamp offset to avoid empty borders
  const clampOffset = useCallback(
    (x: number, y: number) => {
      if (!natural) return { x, y };
      const halfW = (natural.w * currentScale) / 2;
      const halfH = (natural.h * currentScale) / 2;
      const limitX = Math.max(0, halfW - viewportSize / 2);
      const limitY = Math.max(0, halfH - viewportSize / 2);
      return {
        x: Math.min(limitX, Math.max(-limitX, x)),
        y: Math.min(limitY, Math.max(-limitY, y)),
      };
    },
    [natural, currentScale, viewportSize]
  );

  const onPointerDown = (e: React.PointerEvent) => {
    (e.target as HTMLElement).setPointerCapture?.(e.pointerId);
    setDragStart({ x: e.clientX, y: e.clientY });
  };
  const onPointerMove = (e: React.PointerEvent) => {
    if (!dragStart) return;
    const dx = e.clientX - dragStart.x;
    const dy = e.clientY - dragStart.y;
    const next = clampOffset(offset.x + dx, offset.y + dy);
    setOffset(next);
    setDragStart({ x: e.clientX, y: e.clientY });
  };
  const onPointerUp = () => setDragStart(null);

  const handleWheel = (e: React.WheelEvent) => {
    e.preventDefault();
    const delta = -e.deltaY; // scroll up to zoom in
    const factor = delta > 0 ? 1.05 : 0.95;
    const next = Math.min(maxScale, Math.max(minScale, currentScale * factor));
    setScale(next);
  };

  const handleSave = async () => {
    if (!image || !natural) return;
    const canvas = document.createElement('canvas');
    canvas.width = outputSize;
    canvas.height = outputSize;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    // White background
    ctx.fillStyle = '#ffffff';
    ctx.fillRect(0, 0, outputSize, outputSize);

    // Map viewport-space transforms to output canvas space
    const scaleToOutput = outputSize / viewportSize; // scale viewport px to output px
    ctx.save();
    ctx.translate((outputSize / 2) + offset.x * scaleToOutput, (outputSize / 2) + offset.y * scaleToOutput);
    ctx.scale(currentScale * scaleToOutput, currentScale * scaleToOutput);
    ctx.drawImage(image, -natural.w / 2, -natural.h / 2);
    ctx.restore();

    try {
      const blob: Blob | null = await new Promise((resolve) => canvas.toBlob((b) => resolve(b), 'image/jpeg', 0.9));
      if (blob) {
        onCropped(blob);
      }
    } catch (err) {
      logger.error('Failed to create cropped image', err instanceof Error ? err : new Error(String(err)));
    }
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={"Adjust your profile picture"}
      description="Preview and crop your profile picture before saving"
      size="lg"
      footer={
        <div className="flex justify-end gap-3">
          <button
            type="button"
            onClick={onClose}
            className="h-10 min-w-[112px] inline-flex items-center justify-center px-4 text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50 cursor-pointer"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleSave}
            className="h-10 min-w-[112px] inline-flex items-center justify-center px-4 bg-[#7E22CE] text-white rounded-md hover:bg-[#7E22CE] cursor-pointer"
          >
            Save
          </button>
        </div>
      }
    >
      <div className="flex flex-col gap-4">
        <div className="flex items-center gap-4">
          <label className="text-sm text-gray-600">Zoom</label>
          <input
            type="range"
            min={0}
            max={1}
            step={0.005}
            value={(currentScale - minScale) / (maxScale - minScale)}
            onChange={(e) => {
              const t = parseFloat(e.target.value);
              setScale(minScale + t * (maxScale - minScale));
            }}
            className="w-64 accent-[#7E22CE]"
          />
          <span className="text-xs text-gray-500 w-14 text-right">{Math.round((currentScale / minScale) * 100)}%</span>
        </div>

        <div
          ref={containerRef}
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
          onPointerLeave={onPointerUp}
          onWheel={handleWheel}
          className="relative mx-auto rounded-lg border border-gray-300 bg-[linear-gradient(45deg,#f3f4f6_25%,transparent_25%),linear-gradient(-45deg,#f3f4f6_25%,transparent_25%),linear-gradient(45deg,transparent_75%,#f3f4f6_75%),linear-gradient(-45deg,transparent_75%,#f3f4f6_75%)] bg-[length:20px_20px] bg-[position:0_0,0_10px,10px_-10px,-10px_0px] overflow-hidden select-none"
          style={{ width: viewportSize, height: viewportSize, touchAction: 'none', cursor: dragStart ? 'grabbing' : 'grab' }}
          aria-label="Image crop area"
        >
          {image && natural && (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={image.src}
              alt="To be cropped"
              draggable={false}
              className="absolute top-1/2 left-1/2 select-none"
              style={{
                transform: `translate(calc(-50% + ${offset.x}px), calc(-50% + ${offset.y}px))`,
                width: `${natural.w * currentScale}px`,
                height: `${natural.h * currentScale}px`,
                maxWidth: 'none',
                maxHeight: 'none',
                userSelect: 'none',
              }}
            />
          )}
          {/* Square frame overlay */}
          <div className="pointer-events-none absolute inset-0 ring-2 ring-white/80" />
        </div>

        <p className="text-xs text-gray-500 text-center">Drag to pan, use the slider or scroll to zoom. Output is square.</p>
      </div>
    </Modal>
  );
}
