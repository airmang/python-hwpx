"use client";

import { useState, useCallback } from "react";
import { useEditorStore } from "@/lib/store";
import { FONT_FAMILIES, COLOR_PRESETS } from "@/lib/constants";
import { Dialog } from "./Dialog";
import { DialogTabs } from "./DialogTabs";
import { DialogSection } from "./DialogSection";

const TABS = ["기본", "확장", "테두리/배경"];

// ── Tab 1: 기본 (Basic) ──────────────────────────────────────────────────────

function BasicTab() {
  const extendedFormat = useEditorStore((s) => s.extendedFormat);
  const cf = extendedFormat.char;

  const [fontSize, setFontSize] = useState(cf.fontSize ?? 10);
  const [fontFamily, setFontFamily] = useState(cf.fontFamily ?? "함초롬바탕");
  const [relativeSize, setRelativeSize] = useState(100);
  const [charWidth, setCharWidth] = useState(100);
  const [charPosition, setCharPosition] = useState(0);
  const [letterSpacing, setLetterSpacing] = useState(cf.letterSpacing ?? 0);
  const [textColor, setTextColor] = useState(cf.textColor ?? "#000000");
  const [highlightColor, setHighlightColor] = useState(cf.highlightColor ?? "");

  const [bold, setBold] = useState(cf.bold);
  const [italic, setItalic] = useState(cf.italic);
  const [underline, setUnderline] = useState(cf.underline);
  const [strikethrough, setStrikethrough] = useState(cf.strikethrough);

  const inputClass = "h-7 px-2 text-xs border border-gray-300 rounded bg-white";
  const selectClass = "h-7 px-2 text-xs border border-gray-300 rounded bg-white";

  return (
    <>
      {/* 기준 크기 */}
      <div className="flex items-center gap-2 mb-4">
        <span className="text-xs text-gray-700 w-16">기준 크기</span>
        <input
          type="number"
          step="0.5"
          min={1}
          max={200}
          value={fontSize}
          onChange={(e) => setFontSize(Number(e.target.value))}
          className={`${inputClass} w-20`}
        />
        <select className={`${selectClass} w-14`} defaultValue="pt">
          <option value="pt">pt</option>
        </select>
      </div>

      {/* 언어별 설정 */}
      <DialogSection title="언어별 설정">
        <div className="grid grid-cols-2 gap-x-8 gap-y-2">
          <div className="flex items-center gap-2">
            <span className="text-xs text-gray-600 w-14">언어</span>
            <select className={`${selectClass} flex-1`} defaultValue="대표">
              <option>대표</option>
              <option>한글</option>
              <option>영어</option>
              <option>한자</option>
              <option>일어</option>
            </select>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-xs text-gray-600 w-10">글꼴</span>
            <select
              className={`${selectClass} flex-1`}
              value={fontFamily}
              onChange={(e) => setFontFamily(e.target.value)}
            >
              {FONT_FAMILIES.map((f) => (
                <option key={f} value={f}>{f}</option>
              ))}
            </select>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-xs text-gray-600 w-14">상대 크기</span>
            <input type="number" value={relativeSize} onChange={(e) => setRelativeSize(Number(e.target.value))} className={`${inputClass} flex-1`} />
            <span className="text-[10px] text-gray-400">%</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-xs text-gray-600 w-10">장평</span>
            <input type="number" value={charWidth} onChange={(e) => setCharWidth(Number(e.target.value))} className={`${inputClass} flex-1`} />
            <span className="text-[10px] text-gray-400">%</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-xs text-gray-600 w-14">글자 위치</span>
            <input type="number" value={charPosition} onChange={(e) => setCharPosition(Number(e.target.value))} className={`${inputClass} flex-1`} />
            <span className="text-[10px] text-gray-400">%</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-xs text-gray-600 w-10">자간</span>
            <input type="number" value={letterSpacing} onChange={(e) => setLetterSpacing(Number(e.target.value))} className={`${inputClass} flex-1`} />
            <span className="text-[10px] text-gray-400">%</span>
          </div>
        </div>
      </DialogSection>

      {/* 속성 */}
      <DialogSection title="속성">
        {/* Attribute buttons - styled A buttons */}
        <div className="flex gap-1.5 mb-3 flex-wrap">
          {[
            { label: "A", style: "font-bold", title: "굵게", active: bold, toggle: () => setBold(!bold) },
            { label: "A", style: "italic", title: "기울임", active: italic, toggle: () => setItalic(!italic) },
            { label: "A", style: "underline", title: "밑줄", active: underline, toggle: () => setUnderline(!underline) },
            { label: "A", style: "line-through", title: "취소선", active: strikethrough, toggle: () => setStrikethrough(!strikethrough) },
            { label: "A", style: "font-outline", title: "외곽선", active: false, toggle: () => {} },
            { label: "A", style: "text-shadow", title: "그림자", active: false, toggle: () => {} },
            { label: "A", style: "tracking-wider", title: "양각", active: false, toggle: () => {} },
            { label: "A", style: "tracking-tighter", title: "음각", active: false, toggle: () => {} },
          ].map((attr, i) => (
            <button
              key={i}
              onClick={attr.toggle}
              title={attr.title}
              className={`w-10 h-10 rounded border text-lg flex items-center justify-center transition-colors ${
                attr.active
                  ? "bg-blue-50 border-blue-300 text-blue-700"
                  : "bg-white border-gray-300 text-gray-700 hover:bg-gray-50"
              }`}
            >
              <span className={attr.active ? attr.style : ""}>{attr.label}</span>
            </button>
          ))}
          {/* Spacer */}
          <div className="w-2" />
          {/* Additional attribute buttons (위 첨자, 아래 첨자, etc.) */}
          {["위첨자", "아래첨자", "보통"].map((title, i) => (
            <button
              key={`extra-${i}`}
              title={title}
              className="w-10 h-10 rounded border bg-white border-gray-300 text-gray-700 hover:bg-gray-50 flex items-center justify-center"
            >
              <span className="text-[9px]">{title.slice(0, 2)}</span>
            </button>
          ))}
        </div>

        {/* Color pickers */}
        <div className="flex items-center gap-6">
          <div className="flex items-center gap-2">
            <span className="text-xs text-gray-600">글자 색</span>
            <div className="relative">
              <input
                type="color"
                value={textColor}
                onChange={(e) => setTextColor(e.target.value)}
                className="w-24 h-7 rounded border border-gray-300 cursor-pointer"
              />
            </div>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-xs text-gray-600">음영 색</span>
            <select
              className={`${selectClass} w-28`}
              value={highlightColor}
              onChange={(e) => setHighlightColor(e.target.value)}
            >
              <option value="">색 없음</option>
              {COLOR_PRESETS.map((c) => (
                <option key={c} value={c}>{c}</option>
              ))}
            </select>
          </div>
        </div>
      </DialogSection>
    </>
  );
}

// ── Tab 2: 확장 (Extended) ────────────────────────────────────────────────────

function ExtendedTab() {
  const selectClass = "h-7 px-2 text-xs border border-gray-300 rounded bg-white";
  const inputClass = "h-7 px-2 text-xs border border-gray-300 rounded bg-white";

  return (
    <>
      {/* 그림자 */}
      <DialogSection title="그림자">
        <div className="flex items-center gap-6 mb-2">
          {["없음", "비연속", "연속"].map((label, i) => (
            <label key={label} className="flex items-center gap-1.5 text-xs text-gray-700">
              <input type="radio" name="shadow" defaultChecked={i === 0} className="w-3.5 h-3.5" />
              {label}
            </label>
          ))}
        </div>
        <div className="grid grid-cols-2 gap-x-8 gap-y-2">
          <div className="flex items-center gap-2">
            <span className="text-xs text-gray-400 w-12">X 방향</span>
            <input type="number" disabled className={`${inputClass} flex-1`} />
            <span className="text-[10px] text-gray-400">%</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-xs text-gray-400 w-12">Y 방향</span>
            <input type="number" disabled className={`${inputClass} flex-1`} />
            <span className="text-[10px] text-gray-400">%</span>
          </div>
        </div>
        <div className="flex items-center gap-2 mt-2">
          <span className="text-xs text-gray-400 w-12">색</span>
          <select disabled className={`${selectClass} flex-1`}>
            <option>검정</option>
          </select>
        </div>
      </DialogSection>

      {/* 밑줄 */}
      <DialogSection title="밑줄">
        <div className="grid grid-cols-2 gap-x-8 gap-y-2">
          <div className="flex items-center gap-2">
            <span className="text-xs text-gray-600 w-10">위치</span>
            <select className={`${selectClass} flex-1`} defaultValue="없음">
              <option>없음</option>
              <option>글자 아래</option>
              <option>글자 가운데</option>
              <option>글자 위</option>
            </select>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-xs text-gray-400 w-10">색</span>
            <select disabled className={`${selectClass} flex-1`}>
              <option>검정</option>
            </select>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-xs text-gray-400 w-10">종류</span>
            <select disabled className={`${selectClass} flex-1`}>
              <option>실선</option>
            </select>
          </div>
        </div>
      </DialogSection>

      {/* 취소선 */}
      <DialogSection title="취소선">
        <div className="grid grid-cols-2 gap-x-8 gap-y-2">
          <div className="flex items-center gap-2">
            <span className="text-xs text-gray-600 w-10">모양</span>
            <select className={`${selectClass} flex-1`} defaultValue="선 없음">
              <option>선 없음</option>
              <option>실선</option>
              <option>이중선</option>
            </select>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-xs text-gray-600 w-10">색</span>
            <input type="color" defaultValue="#000000" className="w-24 h-7 rounded border border-gray-300" />
          </div>
        </div>
      </DialogSection>

      {/* 기타 */}
      <DialogSection title="기타">
        <div className="grid grid-cols-2 gap-x-8 gap-y-2">
          <div className="flex items-center gap-2">
            <span className="text-xs text-gray-600 w-10">외곽선</span>
            <select className={`${selectClass} flex-1`} defaultValue="없음">
              <option>없음</option>
              <option>실선</option>
              <option>이중선</option>
            </select>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-xs text-gray-600 w-10">강조점</span>
            <select className={`${selectClass} flex-1`} defaultValue="없음">
              <option>없음</option>
              <option>점</option>
              <option>원</option>
            </select>
          </div>
        </div>
        <div className="flex items-center gap-6 mt-2">
          <label className="flex items-center gap-1.5 text-xs text-gray-600">
            <input type="checkbox" className="w-3.5 h-3.5" />
            글꼴에 어울리는 빈 칸
          </label>
          <label className="flex items-center gap-1.5 text-xs text-gray-600">
            <input type="checkbox" className="w-3.5 h-3.5" />
            커닝
          </label>
        </div>
      </DialogSection>
    </>
  );
}

// ── Tab 3: 테두리/배경 (Border/Background) ────────────────────────────────────

function BorderBackgroundTab() {
  const selectClass = "h-7 px-2 text-xs border border-gray-300 rounded bg-white";

  return (
    <>
      {/* 테두리 */}
      <DialogSection title="테두리">
        <div className="flex gap-4">
          <div className="flex-1 space-y-2">
            <div className="flex items-center gap-2">
              <span className="text-xs text-gray-600 w-10">종류</span>
              <select className={`${selectClass} flex-1`} defaultValue="선 없음">
                <option>선 없음</option>
                <option>실선</option>
                <option>점선</option>
                <option>파선</option>
                <option>이중선</option>
              </select>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-xs text-gray-600 w-10">굵기</span>
              <select className={`${selectClass} flex-1`} defaultValue="0.1 mm">
                <option>0.1 mm</option>
                <option>0.12 mm</option>
                <option>0.15 mm</option>
                <option>0.2 mm</option>
                <option>0.3 mm</option>
                <option>0.4 mm</option>
                <option>0.5 mm</option>
                <option>1.0 mm</option>
              </select>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-xs text-gray-600 w-10">색</span>
              <input type="color" defaultValue="#000000" className="w-24 h-7 rounded border border-gray-300" />
            </div>
          </div>
          {/* Preview */}
          <div className="w-44 h-28 border border-gray-300 rounded bg-white flex items-center justify-center">
            <span className="text-[10px] text-gray-300">미리보기</span>
          </div>
        </div>
      </DialogSection>

      {/* 배경 */}
      <DialogSection title="배경">
        <div className="grid grid-cols-2 gap-x-8 gap-y-2">
          <div className="flex items-center gap-2">
            <span className="text-xs text-gray-600 w-12">면 색</span>
            <select className={`${selectClass} flex-1`} defaultValue="색 없음">
              <option>색 없음</option>
              <option>흰색</option>
              <option>검정</option>
            </select>
          </div>
        </div>
        <div className="grid grid-cols-2 gap-x-8 gap-y-2 mt-2">
          <div className="flex items-center gap-2">
            <span className="text-xs text-gray-600 w-12">무늬 색</span>
            <input type="color" defaultValue="#c0c0c0" className="w-24 h-7 rounded border border-gray-300" />
          </div>
          <div className="flex items-center gap-2">
            <span className="text-xs text-gray-600 w-12">무늬 모양</span>
            <select className={`${selectClass} flex-1`} defaultValue="">
              <option value="">없음</option>
            </select>
          </div>
        </div>
      </DialogSection>
    </>
  );
}

// ── Main Dialog ───────────────────────────────────────────────────────────────

export function CharFormatDialog() {
  const open = useEditorStore((s) => s.uiState.charFormatDialogOpen);
  const closeCharFormatDialog = useEditorStore((s) => s.closeCharFormatDialog);
  const [activeTab, setActiveTab] = useState(0);

  const handleApply = useCallback(() => {
    // Apply changes from the dialog
    // For now, close the dialog (values are already applied via sidebar)
    closeCharFormatDialog();
  }, [closeCharFormatDialog]);

  return (
    <Dialog title="글자 모양" open={open} onClose={closeCharFormatDialog} onApply={handleApply} width={580}>
      <DialogTabs tabs={TABS} activeTab={activeTab} onTabChange={setActiveTab} />
      {activeTab === 0 && <BasicTab />}
      {activeTab === 1 && <ExtendedTab />}
      {activeTab === 2 && <BorderBackgroundTab />}

      {/* 미리보기 */}
      <div className="mt-4">
        <div className="text-xs font-bold text-gray-800 mb-1.5">미리보기</div>
        <div className="bg-white border border-gray-200 rounded-md p-4 min-h-[60px] flex items-end">
          <span className="text-sm text-gray-600">한글Eng123漢字あいう※☉</span>
        </div>
      </div>
    </Dialog>
  );
}
