"use client";

import { useState, useEffect } from "react";
import { useEditorStore } from "@/lib/store";
import { Dialog } from "./Dialog";
import { DialogSection } from "./DialogSection";
import { autoCorrectManager, type AutoCorrectRule } from "@/lib/autocorrect";

export function AutoCorrectDialog() {
  const uiState = useEditorStore((s) => s.uiState);
  const closeAutoCorrectDialog = useEditorStore((s) => s.closeAutoCorrectDialog);

  const [enabled, setEnabled] = useState(true);
  const [rules, setRules] = useState<AutoCorrectRule[]>([]);
  const [newFrom, setNewFrom] = useState("");
  const [newTo, setNewTo] = useState("");

  useEffect(() => {
    if (uiState.autoCorrectDialogOpen) {
      setEnabled(autoCorrectManager.isEnabled());
      setRules(autoCorrectManager.getRules());
    }
  }, [uiState.autoCorrectDialogOpen]);

  const handleApply = () => {
    autoCorrectManager.setEnabled(enabled);
    autoCorrectManager.setRules(rules);
    closeAutoCorrectDialog();
  };

  const handleToggleRule = (from: string) => {
    setRules((prev) =>
      prev.map((r) =>
        r.from === from ? { ...r, enabled: !r.enabled } : r
      )
    );
  };

  const handleDeleteRule = (from: string) => {
    setRules((prev) => prev.filter((r) => r.from !== from));
  };

  const handleAddRule = () => {
    if (!newFrom.trim() || !newTo.trim()) return;
    const existing = rules.find((r) => r.from === newFrom);
    if (existing) {
      setRules((prev) =>
        prev.map((r) =>
          r.from === newFrom ? { ...r, to: newTo, enabled: true } : r
        )
      );
    } else {
      setRules((prev) => [...prev, { from: newFrom, to: newTo, enabled: true }]);
    }
    setNewFrom("");
    setNewTo("");
  };

  const handleReset = () => {
    autoCorrectManager.resetToDefaults();
    setRules(autoCorrectManager.getRules());
    setEnabled(true);
  };

  const inputClass =
    "px-2 py-1.5 text-sm border border-gray-300 rounded bg-white focus:outline-none focus:border-blue-400";

  return (
    <Dialog
      title="자동 고침"
      open={uiState.autoCorrectDialogOpen}
      onClose={closeAutoCorrectDialog}
      onApply={handleApply}
      width={500}
    >
      <div className="flex items-center gap-2 mb-4">
        <input
          type="checkbox"
          id="autocorrect-enabled"
          checked={enabled}
          onChange={(e) => setEnabled(e.target.checked)}
          className="w-4 h-4"
        />
        <label htmlFor="autocorrect-enabled" className="text-sm">
          자동 고침 사용
        </label>
      </div>

      <DialogSection title="새 규칙 추가">
        <div className="flex gap-2 items-end">
          <div className="flex-1">
            <label className="text-xs text-gray-600 block mb-1">입력</label>
            <input
              type="text"
              value={newFrom}
              onChange={(e) => setNewFrom(e.target.value)}
              aria-label="자동 고침 입력 패턴"
              className={`${inputClass} w-full`}
            />
          </div>
          <div className="text-gray-400 pb-2">→</div>
          <div className="flex-1">
            <label className="text-xs text-gray-600 block mb-1">변환</label>
            <input
              type="text"
              value={newTo}
              onChange={(e) => setNewTo(e.target.value)}
              aria-label="자동 고침 변환 패턴"
              className={`${inputClass} w-full`}
            />
          </div>
          <button
            onClick={handleAddRule}
            disabled={!newFrom.trim() || !newTo.trim()}
            className="px-3 py-1.5 text-sm bg-blue-500 text-white rounded hover:bg-blue-600 disabled:bg-gray-300 disabled:cursor-not-allowed"
          >
            추가
          </button>
        </div>
      </DialogSection>

      <DialogSection title="규칙 목록">
        <div className="max-h-48 overflow-y-auto border border-gray-200 rounded">
          {rules.length === 0 ? (
            <div className="p-3 text-sm text-gray-400 text-center">
              등록된 규칙이 없습니다.
            </div>
          ) : (
            rules.map((rule) => (
              <div
                key={rule.from}
                className="flex items-center gap-2 px-3 py-2 border-b border-gray-100 last:border-0 hover:bg-gray-50"
              >
                <input
                  type="checkbox"
                  checked={rule.enabled}
                  onChange={() => handleToggleRule(rule.from)}
                  className="w-4 h-4"
                />
                <span className={`text-sm flex-1 ${!rule.enabled ? "text-gray-400" : ""}`}>
                  <span className="font-mono bg-gray-100 px-1 rounded">{rule.from}</span>
                  {" → "}
                  <span className="font-mono bg-gray-100 px-1 rounded">{rule.to}</span>
                </span>
                <button
                  onClick={() => handleDeleteRule(rule.from)}
                  className="text-red-500 hover:text-red-700 text-sm px-2"
                >
                  삭제
                </button>
              </div>
            ))
          )}
        </div>
      </DialogSection>

      <div className="flex justify-end mt-3">
        <button
          onClick={handleReset}
          className="text-xs text-gray-500 hover:text-gray-700"
        >
          기본값으로 초기화
        </button>
      </div>
    </Dialog>
  );
}
