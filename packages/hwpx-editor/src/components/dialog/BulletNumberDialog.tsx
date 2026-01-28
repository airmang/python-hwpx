"use client";

import { useState, useCallback } from "react";
import { useEditorStore } from "@/lib/store";
import { Dialog } from "./Dialog";
import { DialogTabs } from "./DialogTabs";
import { DialogSection } from "./DialogSection";

const TABS = ["문단 번호", "글머리표", "그림 글머리표"];

// Numbering style definitions
const NUMBERING_STYLES = [
  { id: "none", lines: ["", "", "", ""], label: "없음" },
  { id: "1a", lines: ["1.", "가.", "1)", "가)"], label: "1.가.1)가)" },
  { id: "1b", lines: ["(1)", "(가)", "(a)", "1)"], label: "(1)(가)(a)1)" },
  { id: "1c", lines: ["1)", "가)", "a)", "(1)"], label: "1)가)a)(1)" },
  { id: "1d", lines: ["①", "(ㄱ)", "(a)", "1)"], label: "①(ㄱ)(a)1)" },
  { id: "1e", lines: ["가)", "a)", "(1)", "(가)"], label: "가)a)(1)(가)" },
  { id: "1f", lines: ["(ㄱ)", "(1)", "(a)", "1)"], label: "(ㄱ)(1)(a)1)" },
  { id: "1g", lines: ["I.", "A.", "1.", "i)"], label: "I.A.1.i)" },
];

const BULLET_STYLES = [
  "●", "•", "■", "▪", "◆", "◇", "▶", "▷",
  "○", "□", "◇", "▷", "◎", "☑", "✓", "★",
];

// ── Tab 1: 문단 번호 ─────────────────────────────────────────────────────────

function NumberingTab() {
  const [selected, setSelected] = useState(0);

  return (
    <>
      <DialogSection title="각주 내용 번호 속성">
        <div className="flex items-center gap-4 mb-2">
          {["앞 번호 목록에 이어", "이전 번호 목록에 이어"].map((label) => (
            <label key={label} className="flex items-center gap-1.5 text-xs text-gray-400">
              <input type="radio" name="numCont" disabled className="w-3.5 h-3.5" />
              {label}
            </label>
          ))}
        </div>
        <label className="flex items-center gap-1.5 text-xs text-gray-700">
          <input type="radio" name="numCont" defaultChecked className="w-3.5 h-3.5" />
          새 번호 목록 시작
        </label>
        <div className="flex items-center gap-2 mt-1.5 ml-5">
          <span className="text-xs text-gray-600">1 수준 시작 번호</span>
          <input type="number" defaultValue={1} className="h-7 px-2 text-xs border border-gray-300 rounded bg-white w-28" />
        </div>
      </DialogSection>

      <DialogSection title="문단 번호 모양">
        <div className="grid grid-cols-4 gap-2">
          {NUMBERING_STYLES.map((style, idx) => (
            <button
              key={style.id}
              onClick={() => setSelected(idx)}
              className={`p-2 rounded border text-left min-h-[80px] transition-colors ${
                selected === idx
                  ? "border-blue-500 bg-blue-50 ring-2 ring-blue-200"
                  : "border-gray-200 bg-white hover:border-gray-300"
              }`}
            >
              {idx === 0 ? (
                <div className="flex items-center justify-center h-full">
                  <div className="w-8 h-8 border border-gray-300 rounded flex items-center justify-center">
                    <svg width="16" height="16" viewBox="0 0 16 16">
                      <line x1="2" y1="14" x2="14" y2="2" stroke="#dc2626" strokeWidth="1.5" />
                    </svg>
                  </div>
                </div>
              ) : (
                <div className="space-y-0.5">
                  {style.lines.map((line, li) => (
                    <div key={li} className="flex items-center gap-1">
                      <span className="text-[9px] text-gray-700 w-6">{line}</span>
                      <div className="flex-1 h-[1px] bg-gray-300" />
                    </div>
                  ))}
                </div>
              )}
            </button>
          ))}
        </div>
      </DialogSection>
    </>
  );
}

// ── Tab 2: 글머리표 ──────────────────────────────────────────────────────────

function BulletTab() {
  const [selected, setSelected] = useState(0);

  return (
    <DialogSection title="글머리표 모양">
      <div className="grid grid-cols-4 gap-2">
        {/* "None" option */}
        <button
          onClick={() => setSelected(0)}
          className={`p-3 rounded border min-h-[80px] flex items-center justify-center transition-colors ${
            selected === 0
              ? "border-blue-500 bg-blue-50 ring-2 ring-blue-200"
              : "border-gray-200 bg-white hover:border-gray-300"
          }`}
        >
          <div className="w-8 h-8 border border-gray-300 rounded flex items-center justify-center">
            <svg width="16" height="16" viewBox="0 0 16 16">
              <line x1="2" y1="14" x2="14" y2="2" stroke="#dc2626" strokeWidth="1.5" />
            </svg>
          </div>
        </button>
        {/* Bullet styles */}
        {BULLET_STYLES.map((bullet, idx) => (
          <button
            key={idx}
            onClick={() => setSelected(idx + 1)}
            className={`p-2 rounded border min-h-[80px] transition-colors ${
              selected === idx + 1
                ? "border-blue-500 bg-blue-50 ring-2 ring-blue-200"
                : "border-gray-200 bg-white hover:border-gray-300"
            }`}
          >
            <div className="space-y-1">
              <div className="flex items-center gap-1">
                <span className="text-sm">{bullet}</span>
                <div className="flex-1 h-[1px] bg-gray-300" />
              </div>
              <div className="flex items-center gap-1 ml-3">
                <div className="flex-1 h-[1px] bg-gray-200" />
              </div>
              <div className="flex items-center gap-1">
                <span className="text-sm">{bullet}</span>
                <div className="flex-1 h-[1px] bg-gray-300" />
              </div>
              <div className="flex items-center gap-1 ml-3">
                <div className="flex-1 h-[1px] bg-gray-200" />
              </div>
            </div>
          </button>
        ))}
      </div>
    </DialogSection>
  );
}

// ── Tab 3: 그림 글머리표 ──────────────────────────────────────────────────────

function PictureBulletTab() {
  return (
    <DialogSection title="그림 글머리표">
      <div className="text-xs text-gray-400 text-center py-8">
        그림 글머리표를 선택하세요. (미지원)
      </div>
    </DialogSection>
  );
}

// ── Main Dialog ───────────────────────────────────────────────────────────────

export function BulletNumberDialog() {
  const open = useEditorStore((s) => s.uiState.bulletNumberDialogOpen);
  const closeBulletNumberDialog = useEditorStore((s) => s.closeBulletNumberDialog);
  const [activeTab, setActiveTab] = useState(0);

  const handleApply = useCallback(() => {
    closeBulletNumberDialog();
  }, [closeBulletNumberDialog]);

  return (
    <Dialog title="문단 번호/글머리표" open={open} onClose={closeBulletNumberDialog} onApply={handleApply} width={620}>
      <DialogTabs tabs={TABS} activeTab={activeTab} onTabChange={setActiveTab} />
      {activeTab === 0 && <NumberingTab />}
      {activeTab === 1 && <BulletTab />}
      {activeTab === 2 && <PictureBulletTab />}

      <div className="flex items-center gap-2 mt-3">
        <button disabled className="h-7 px-3 text-xs border border-gray-300 rounded bg-white text-gray-400">
          사용자 정의...
        </button>
        <button disabled className="w-7 h-7 rounded border border-gray-300 bg-white text-red-400 flex items-center justify-center text-sm">
          ×
        </button>
      </div>
    </Dialog>
  );
}
