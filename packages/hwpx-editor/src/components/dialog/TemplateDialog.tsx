"use client";

import { useState, useEffect, useCallback } from "react";
import { useEditorStore } from "@/lib/store";
import { X, Plus, Trash2, FileText } from "lucide-react";

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

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="bg-white rounded-lg shadow-xl w-[500px] max-h-[80vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b">
          <h2 className="text-sm font-semibold">문서 템플릿</h2>
          <button
            onClick={closeDialog}
            className="p-1 hover:bg-gray-100 rounded"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-auto p-4">
          {/* Template List */}
          <div className="space-y-2 mb-4">
            {templates.length === 0 ? (
              <div className="text-center py-8 text-gray-500 text-sm">
                저장된 템플릿이 없습니다.
                <br />
                자주 사용하는 문서를 템플릿으로 추가하세요.
              </div>
            ) : (
              templates.map((tpl) => (
                <div
                  key={tpl.id}
                  className="flex items-center gap-3 p-3 border rounded hover:bg-gray-50 group"
                >
                  <FileText className="w-5 h-5 text-blue-500 flex-shrink-0" />
                  <div className="flex-1 min-w-0">
                    <div className="font-medium text-sm truncate">{tpl.name}</div>
                    <div className="text-xs text-gray-500 truncate">{tpl.path}</div>
                    {tpl.description && (
                      <div className="text-xs text-gray-400 truncate">{tpl.description}</div>
                    )}
                  </div>
                  <button
                    onClick={() => removeTemplate(tpl.id)}
                    className="p-1.5 text-gray-400 hover:text-red-500 hover:bg-red-50 rounded opacity-0 group-hover:opacity-100 transition-opacity"
                    title="삭제"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              ))
            )}
          </div>

          {/* Add Form */}
          {showAddForm ? (
            <div className="border rounded p-3 space-y-2 bg-gray-50">
              <div className="text-xs font-medium text-gray-600 mb-2">새 템플릿 추가</div>
              <div>
                <label className="text-xs text-gray-500">이름</label>
                <input
                  type="text"
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  placeholder="예: 외주용역계약서"
                  className="w-full px-2 py-1.5 text-sm border rounded mt-0.5"
                />
              </div>
              <div>
                <label className="text-xs text-gray-500">파일 경로</label>
                <div className="flex gap-2 mt-0.5">
                  <input
                    type="text"
                    value={newPath}
                    onChange={(e) => setNewPath(e.target.value)}
                    placeholder="/path/to/template.hwp"
                    className="flex-1 px-2 py-1.5 text-sm border rounded"
                  />
                  <button
                    onClick={handleFileSelect}
                    className="px-3 py-1.5 text-sm bg-gray-100 hover:bg-gray-200 rounded"
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
                  placeholder="간단한 설명"
                  className="w-full px-2 py-1.5 text-sm border rounded mt-0.5"
                />
              </div>
              <div className="flex justify-end gap-2 pt-2">
                <button
                  onClick={() => setShowAddForm(false)}
                  className="px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-100 rounded"
                >
                  취소
                </button>
                <button
                  onClick={handleAdd}
                  disabled={!newName.trim() || !newPath.trim()}
                  className="px-3 py-1.5 text-sm bg-blue-500 text-white rounded hover:bg-blue-600 disabled:opacity-50"
                >
                  추가
                </button>
              </div>
            </div>
          ) : (
            <button
              onClick={() => setShowAddForm(true)}
              className="flex items-center justify-center gap-2 w-full py-2 text-sm text-blue-600 hover:bg-blue-50 border border-dashed border-blue-300 rounded"
            >
              <Plus className="w-4 h-4" />
              템플릿 추가
            </button>
          )}
        </div>

        {/* Footer */}
        <div className="px-4 py-3 border-t bg-gray-50 flex justify-end">
          <button
            onClick={closeDialog}
            className="px-4 py-1.5 text-sm bg-gray-200 hover:bg-gray-300 rounded"
          >
            닫기
          </button>
        </div>
      </div>
    </div>
  );
}
