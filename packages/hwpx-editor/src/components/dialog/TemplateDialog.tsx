"use client";

import { useState, useEffect, useCallback } from "react";
import { useEditorStore } from "@/lib/store";
import { Plus, Trash2, FileText } from "lucide-react";
import { Dialog } from "./Dialog";

export function TemplateDialog() {
  const isOpen = useEditorStore((s) => s.uiState.templateDialogOpen);
  const closeDialog = useEditorStore((s) => s.closeTemplateDialog);
  const templates = useEditorStore((s) => s.templates);
  const addTemplate = useEditorStore((s) => s.addTemplate);
  const removeTemplate = useEditorStore((s) => s.removeTemplate);
  const loadTemplates = useEditorStore((s) => s.loadTemplates);

  const [newName, setNewName] = useState("");
  const [newPath, setNewPath] = useState("");
  const [newDesc, setNewDesc] = useState("");
  const [showAddForm, setShowAddForm] = useState(false);

  useEffect(() => {
    loadTemplates();
  }, [loadTemplates]);

  const handleAdd = useCallback(() => {
    if (newName.trim() && newPath.trim()) {
      addTemplate(newName.trim(), newPath.trim(), newDesc.trim() || undefined);
      setNewName("");
      setNewPath("");
      setNewDesc("");
      setShowAddForm(false);
    }
  }, [newName, newPath, newDesc, addTemplate]);

  const handleFileSelect = useCallback(async () => {
    // Use file input for path selection
    const input = document.createElement("input");
    input.type = "file";
    input.accept = ".hwp,.hwpx";
    input.onchange = (e) => {
      const file = (e.target as HTMLInputElement).files?.[0];
      if (file) {
        // For web, we store the file name. In Electron, this would be the full path.
        setNewPath(file.name);
        if (!newName) {
          setNewName(file.name.replace(/\.(hwpx?|hwp)$/i, ""));
        }
      }
    };
    input.click();
  }, [newName]);

  if (!isOpen) return null;

  const footer = (
    <div className="flex justify-end">
      <button
        type="button"
        onClick={closeDialog}
        className="h-10 rounded-lg border border-gray-300 bg-white px-4 text-sm font-medium text-gray-700 hover:bg-gray-50"
      >
        닫기
      </button>
    </div>
  );

  return (
    <Dialog
      title="문서 템플릿"
      description="자주 쓰는 문서를 템플릿으로 등록해 빠르게 불러옵니다."
      open={isOpen}
      onClose={closeDialog}
      width={620}
      footer={footer}
    >
      <div className="space-y-4">
        <div className="space-y-2">
          {templates.length === 0 ? (
            <div className="rounded-xl border border-gray-200 bg-gray-50 py-8 text-center text-sm text-gray-500">
              저장된 템플릿이 없습니다.
              <br />
              자주 사용하는 문서를 템플릿으로 추가하세요.
            </div>
          ) : (
            templates.map((tpl) => (
              <div
                key={tpl.id}
                className="group flex items-center gap-3 rounded-xl border border-gray-200 bg-white p-3 hover:bg-gray-50"
              >
                <FileText className="h-5 w-5 flex-shrink-0 text-blue-500" />
                <div className="min-w-0 flex-1">
                  <div className="truncate text-sm font-medium text-gray-800">{tpl.name}</div>
                  <div className="truncate text-xs text-gray-500">{tpl.path}</div>
                  {tpl.description ? (
                    <div className="truncate text-xs text-gray-400">{tpl.description}</div>
                  ) : null}
                </div>
                <button
                  type="button"
                  onClick={() => removeTemplate(tpl.id)}
                  className="rounded-lg p-1.5 text-gray-400 opacity-0 transition-opacity hover:bg-red-50 hover:text-red-500 group-hover:opacity-100"
                  title="삭제"
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              </div>
            ))
          )}
        </div>

        {showAddForm ? (
          <div className="space-y-2 rounded-xl border border-gray-200 bg-gray-50 p-3.5">
            <div className="mb-2 text-xs font-medium text-gray-600">새 템플릿 추가</div>
            <div>
              <label className="text-xs text-gray-500">이름</label>
              <input
                type="text"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                aria-label="템플릿 이름"
                className="mt-0.5 h-9 w-full rounded-lg border border-gray-300 px-2.5 text-sm focus:border-blue-400 focus:outline-none"
              />
            </div>
            <div>
              <label className="text-xs text-gray-500">파일 경로</label>
              <div className="mt-0.5 flex gap-2">
                <input
                  type="text"
                  value={newPath}
                  onChange={(e) => setNewPath(e.target.value)}
                  aria-label="템플릿 파일 경로"
                  className="h-9 flex-1 rounded-lg border border-gray-300 px-2.5 text-sm focus:border-blue-400 focus:outline-none"
                />
                <button
                  type="button"
                  onClick={handleFileSelect}
                  className="h-9 rounded-lg border border-gray-300 bg-white px-3 text-sm text-gray-700 hover:bg-gray-50"
                >
                  찾기
                </button>
              </div>
            </div>
            <div>
              <label className="text-xs text-gray-500">설명 (선택)</label>
              <input
                type="text"
                value={newDesc}
                onChange={(e) => setNewDesc(e.target.value)}
                aria-label="템플릿 설명"
                className="mt-0.5 h-9 w-full rounded-lg border border-gray-300 px-2.5 text-sm focus:border-blue-400 focus:outline-none"
              />
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <button
                type="button"
                onClick={() => setShowAddForm(false)}
                className="h-9 rounded-lg border border-gray-300 bg-white px-3 text-sm text-gray-700 hover:bg-gray-50"
              >
                취소
              </button>
              <button
                type="button"
                onClick={handleAdd}
                disabled={!newName.trim() || !newPath.trim()}
                className="h-9 rounded-lg bg-blue-600 px-3 text-sm font-medium text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
              >
                추가
              </button>
            </div>
          </div>
        ) : (
          <button
            type="button"
            onClick={() => setShowAddForm(true)}
            className="flex h-10 w-full items-center justify-center gap-2 rounded-xl border border-dashed border-blue-300 text-sm font-medium text-blue-600 hover:bg-blue-50"
          >
            <Plus className="h-4 w-4" />
            템플릿 추가
          </button>
        )}
      </div>
    </Dialog>
  );
}
