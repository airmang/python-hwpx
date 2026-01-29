"use client";

import { useState } from "react";
import { useEditorStore } from "@/lib/store";
import { Dialog } from "./Dialog";
import { DialogSection } from "./DialogSection";
import { Square, Circle, Minus, ArrowRight } from "lucide-react";
import type { ShapeType } from "@/lib/store/types";

const SHAPE_OPTIONS: { type: ShapeType; label: string; icon: React.ReactNode }[] = [
  { type: "rectangle", label: "직사각형", icon: <Square className="w-8 h-8" /> },
  { type: "ellipse", label: "원/타원", icon: <Circle className="w-8 h-8" /> },
  { type: "line", label: "선", icon: <Minus className="w-8 h-8" /> },
  { type: "arrow", label: "화살표", icon: <ArrowRight className="w-8 h-8" /> },
];

export function ShapeDialog() {
  const uiState = useEditorStore((s) => s.uiState);
  const closeShapeDialog = useEditorStore((s) => s.closeShapeDialog);
  const insertShape = useEditorStore((s) => s.insertShape);

  const [selectedShape, setSelectedShape] = useState<ShapeType>("rectangle");
  const [width, setWidth] = useState(50);
  const [height, setHeight] = useState(30);

  const handleApply = () => {
    insertShape(selectedShape, width, height);
    closeShapeDialog();
  };

  const isLineType = selectedShape === "line" || selectedShape === "arrow";

  return (
    <Dialog
      title="도형 삽입"
      open={uiState.shapeDialogOpen}
      onClose={closeShapeDialog}
      onApply={handleApply}
      width={420}
    >
      <DialogSection title="도형 종류">
        <div className="grid grid-cols-4 gap-3">
          {SHAPE_OPTIONS.map((shape) => (
            <button
              key={shape.type}
              onClick={() => setSelectedShape(shape.type)}
              className={`flex flex-col items-center justify-center p-4 rounded-lg border-2 transition-colors ${
                selectedShape === shape.type
                  ? "border-blue-500 bg-blue-50 text-blue-700"
                  : "border-gray-200 bg-white hover:border-gray-300 text-gray-600"
              }`}
            >
              {shape.icon}
              <span className="text-xs mt-2">{shape.label}</span>
            </button>
          ))}
        </div>
      </DialogSection>

      <DialogSection title="크기 (mm)">
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-xs text-gray-600 mb-1">
              {isLineType ? "길이" : "너비"}
            </label>
            <input
              type="number"
              value={width}
              onChange={(e) => setWidth(Number(e.target.value))}
              min={5}
              max={200}
              className="w-full px-3 py-2 border border-gray-300 rounded text-sm"
            />
          </div>
          {!isLineType && (
            <div>
              <label className="block text-xs text-gray-600 mb-1">높이</label>
              <input
                type="number"
                value={height}
                onChange={(e) => setHeight(Number(e.target.value))}
                min={5}
                max={200}
                className="w-full px-3 py-2 border border-gray-300 rounded text-sm"
              />
            </div>
          )}
        </div>
      </DialogSection>

      <DialogSection title="미리보기">
        <div className="border border-gray-200 rounded p-4 bg-gray-50 flex items-center justify-center min-h-[120px]">
          <div
            className="relative"
            style={{
              width: `${Math.min(width, 100)}px`,
              height: isLineType ? "2px" : `${Math.min(height, 80)}px`,
            }}
          >
            {selectedShape === "rectangle" && (
              <div className="w-full h-full border-2 border-gray-700 bg-white rounded" />
            )}
            {selectedShape === "ellipse" && (
              <div className="w-full h-full border-2 border-gray-700 bg-white rounded-full" />
            )}
            {selectedShape === "line" && (
              <div className="w-full h-0.5 bg-gray-700" />
            )}
            {selectedShape === "arrow" && (
              <div className="w-full flex items-center">
                <div className="flex-1 h-0.5 bg-gray-700" />
                <div className="w-0 h-0 border-l-[8px] border-l-gray-700 border-y-[4px] border-y-transparent" />
              </div>
            )}
          </div>
        </div>
      </DialogSection>
    </Dialog>
  );
}
