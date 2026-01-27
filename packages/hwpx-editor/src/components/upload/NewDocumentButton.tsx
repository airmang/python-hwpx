"use client";

import { useCallback } from "react";
import { FilePlus } from "lucide-react";
import { useEditorStore } from "@/lib/store";
import { createNewDocument } from "@/lib/skeleton-loader";

export function NewDocumentButton() {
  const setDocument = useEditorStore((s) => s.setDocument);
  const setLoading = useEditorStore((s) => s.setLoading);
  const setError = useEditorStore((s) => s.setError);

  const handleClick = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const doc = await createNewDocument();
      setDocument(doc);
    } catch (e) {
      console.error("Failed to create new document:", e);
      setError("새 문서를 만들 수 없습니다.");
    } finally {
      setLoading(false);
    }
  }, [setDocument, setLoading, setError]);

  return (
    <button
      onClick={handleClick}
      className="flex items-center gap-2 px-4 py-2 bg-green-500 text-white rounded-lg hover:bg-green-600 transition-colors"
    >
      <FilePlus className="w-5 h-5" />
      새 문서
    </button>
  );
}
