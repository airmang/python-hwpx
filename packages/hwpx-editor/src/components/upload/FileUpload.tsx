"use client";

import { useCallback, useState, useRef } from "react";
import { Upload } from "lucide-react";
import { HwpxDocument } from "@hwpx/core";
import { useEditorStore } from "@/lib/store";

export function FileUpload() {
  const setDocument = useEditorStore((s) => s.setDocument);
  const setLoading = useEditorStore((s) => s.setLoading);
  const setError = useEditorStore((s) => s.setError);

  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const openFile = useCallback(
    async (file: File) => {
      setLoading(true);
      setError(null);
      try {
        const buffer = await file.arrayBuffer();
        const doc = await HwpxDocument.open(buffer);
        setDocument(doc);
      } catch (e) {
        console.error("Failed to open file:", e);
        setError("파일을 열 수 없습니다. HWPX 파일인지 확인하세요.");
      } finally {
        setLoading(false);
      }
    },
    [setDocument, setLoading, setError],
  );

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragging(false);
      const file = e.dataTransfer.files[0];
      if (file) openFile(file);
    },
    [openFile],
  );

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragging(true);
  }, []);

  const handleDragLeave = useCallback(() => {
    setDragging(false);
  }, []);

  const handleChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (file) openFile(file);
      e.target.value = "";
    },
    [openFile],
  );

  return (
    <div
      onDrop={handleDrop}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onClick={() => inputRef.current?.click()}
      className={`cursor-pointer border-2 border-dashed rounded-lg p-8 text-center transition-colors ${
        dragging
          ? "border-blue-400 bg-blue-50"
          : "border-gray-300 hover:border-gray-400"
      }`}
    >
      <Upload className="w-10 h-10 mx-auto mb-3 text-gray-400" />
      <p className="text-gray-600 font-medium">
        HWPX 파일을 드래그하거나 클릭하여 선택
      </p>
      <p className="text-sm text-gray-400 mt-1">.hwpx 파일만 지원</p>
      <input
        ref={inputRef}
        type="file"
        accept=".hwpx"
        className="hidden"
        onChange={handleChange}
      />
    </div>
  );
}
