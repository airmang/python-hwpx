"use client";

import { useState, useCallback } from "react";
import { useEditorStore } from "@/lib/store";
import { Dialog } from "./Dialog";
import { DialogTabs } from "./DialogTabs";
import { DialogSection } from "./DialogSection";

const TABS = ["문단 번호", "글머리표"];

// Numbering style definitions
const NUMBERING_STYLES = [
  { id: "none", level: 0, lines: ["", "", "", ""], label: "없음" },
  { id: "1a", level: 1, lines: ["1.", "가.", "1)", "가)"], label: "1.가.1)가)" },
  { id: "1b", level: 1, lines: ["(1)", "(가)", "(a)", "1)"], label: "(1)(가)(a)1)" },
  { id: "1c", level: 1, lines: ["1)", "가)", "a)", "(1)"], label: "1)가)a)(1)" },
  { id: "1d", level: 1, lines: ["①", "(ㄱ)", "(a)", "1)"], label: "①(ㄱ)(a)1)" },
  { id: "1e", level: 1, lines: ["가)", "a)", "(1)", "(가)"], label: "가)a)(1)(가)" },
  { id: "1f", level: 1, lines: ["(ㄱ)", "(1)", "(a)", "1)"], label: "(ㄱ)(1)(a)1)" },
  { id: "1g", level: 1, lines: ["I.", "A.", "1.", "i)"], label: "I.A.1.i)" },
];

const BULLET_STYLES = [
  { char: "●", id: "1" },
  { char: "•", id: "2" },
  { char: "■", id: "3" },
  { char: "▪", id: "4" },
  { char: "◆", id: "5" },
  { char: "◇", id: "6" },
  { char: "▶", id: "7" },
  { char: "▷", id: "8" },
  { char: "○", id: "9" },
  { char: "□", id: "10" },
  { char: "◇", id: "11" },
  { char: "▷", id: "12" },
  { char: "◎", id: "13" },
  { char: "☑", id: "14" },
  { char: "✓", id: "15" },
  { char: "★", id: "16" },
];

// ── Tab 1: 문단 번호 ─────────────────────────────────────────────────────────

function NumberingTab({ selected, onSelect }: { selected: number; onSelect: (idx: number) => void }) {
  return (
    <>
      <DialogSection title="문단 번호 모양">
        <div className="grid grid-cols-4 gap-2">
          {NUMBERING_STYLES.map((style, idx) => (
            <button
              key={style.id}
              onClick={() => onSelect(idx)}
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

function BulletTab({ selected, onSelect }: { selected: number; onSelect: (idx: number) => void }) {
  return (
    <DialogSection title="글머리표 모양">
      <div className="grid grid-cols-4 gap-2">
        {/* "None" option */}
        <button
          onClick={() => onSelect(0)}
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
            onClick={() => onSelect(idx + 1)}
            className={`p-2 rounded border min-h-[80px] transition-colors ${
              selected === idx + 1
                ? "border-blue-500 bg-blue-50 ring-2 ring-blue-200"
                : "border-gray-200 bg-white hover:border-gray-300"
            }`}
          >
            <div className="space-y-1">
              <div className="flex items-center gap-1">
                <span className="text-sm">{bullet.char}</span>
                <div className="flex-1 h-[1px] bg-gray-300" />
              </div>
              <div className="flex items-center gap-1 ml-3">
                <div className="flex-1 h-[1px] bg-gray-200" />
              </div>
              <div className="flex items-center gap-1">
                <span className="text-sm">{bullet.char}</span>
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

// ── Main Dialog ───────────────────────────────────────────────────────────────

export function BulletNumberDialog() {
  const open = useEditorStore((s) => s.uiState.bulletNumberDialogOpen);
  const closeBulletNumberDialog = useEditorStore((s) => s.closeBulletNumberDialog);
  const applyBullet = useEditorStore((s) => s.applyBullet);
  const applyNumbering = useEditorStore((s) => s.applyNumbering);
  const removeBulletNumbering = useEditorStore((s) => s.removeBulletNumbering);

  const [activeTab, setActiveTab] = useState(0);
  const [numberingSelected, setNumberingSelected] = useState(0);
  const [bulletSelected, setBulletSelected] = useState(0);

  const handleApply = useCallback(() => {
    if (activeTab === 0) {
      // Numbering tab
      if (numberingSelected === 0) {
        removeBulletNumbering();
      } else {
        const style = NUMBERING_STYLES[numberingSelected];
        if (style) {
          applyNumbering(style.level);
        }
      }
    } else if (activeTab === 1) {
      // Bullet tab
      if (bulletSelected === 0) {
        removeBulletNumbering();
      } else {
        const bullet = BULLET_STYLES[bulletSelected - 1];
        if (bullet) {
          applyBullet(bullet.id);
        }
      }
    }
    closeBulletNumberDialog();
  }, [activeTab, numberingSelected, bulletSelected, applyBullet, applyNumbering, removeBulletNumbering, closeBulletNumberDialog]);

  return (
    <Dialog title="문단 번호/글머리표" open={open} onClose={closeBulletNumberDialog} onApply={handleApply} width={620}>
      <DialogTabs tabs={TABS} activeTab={activeTab} onTabChange={setActiveTab} />
      {activeTab === 0 && <NumberingTab selected={numberingSelected} onSelect={setNumberingSelected} />}
      {activeTab === 1 && <BulletTab selected={bulletSelected} onSelect={setBulletSelected} />}
      <div className="flex items-center gap-2 mt-3">
        <button
          onClick={() => { removeBulletNumbering(); closeBulletNumberDialog(); }}
          className="w-7 h-7 rounded border border-gray-300 bg-white text-red-500 hover:bg-red-50 flex items-center justify-center text-sm"
          title="서식 제거"
        >
          ×
        </button>
      </div>
    </Dialog>
  );
}
