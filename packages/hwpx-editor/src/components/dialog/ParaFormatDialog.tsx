"use client";

import { useState, useCallback } from "react";
import { useEditorStore } from "@/lib/store";
import { Dialog } from "./Dialog";
import { DialogTabs } from "./DialogTabs";
import { DialogSection } from "./DialogSection";

const TABS = ["기본", "확장", "탭 설정", "테두리/배경"];

// ── Tab 1: 기본 (Basic) ──────────────────────────────────────────────────────

function BasicTab() {
  const extendedFormat = useEditorStore((s) => s.extendedFormat);
  const pf = extendedFormat.para;

  const [alignment, setAlignment] = useState<string>(pf.alignment);
  const [marginLeft, setMarginLeft] = useState(pf.indentLeft);
  const [marginRight, setMarginRight] = useState(pf.indentRight);
  const [firstLineMode, setFirstLineMode] = useState<"보통" | "들여쓰기" | "내어쓰기">("보통");
  const [firstLineValue, setFirstLineValue] = useState(pf.firstLineIndent);
  const [lineSpacingType] = useState("글자에 따라");
  const [lineSpacingValue, setLineSpacingValue] = useState(Math.round(pf.lineSpacing * 100));
  const [spacingBefore, setSpacingBefore] = useState(pf.spacingBefore);
  const [spacingAfter, setSpacingAfter] = useState(pf.spacingAfter);

  const inputClass = "h-7 px-2 text-xs border border-gray-300 rounded bg-white";
  const selectClass = "h-7 px-2 text-xs border border-gray-300 rounded bg-white";

  const alignments: { value: string; label: string }[] = [
    { value: "LEFT", label: "왼쪽 정렬" },
    { value: "CENTER", label: "가운데 정렬" },
    { value: "RIGHT", label: "오른쪽 정렬" },
    { value: "JUSTIFY", label: "양쪽 정렬" },
    { value: "DISTRIBUTE", label: "배분 정렬" },
    { value: "BOTH", label: "나눠쓰기" },
  ];

  return (
    <>
      {/* 정렬 방식 */}
      <DialogSection title="정렬 방식">
        <div className="flex gap-1.5">
          {alignments.map((a) => (
            <button
              key={a.value}
              onClick={() => setAlignment(a.value)}
              title={a.label}
              className={`w-12 h-9 rounded border flex items-center justify-center transition-colors ${
                alignment === a.value
                  ? "bg-blue-50 border-blue-300"
                  : "bg-white border-gray-300 hover:bg-gray-50"
              }`}
            >
              <svg width="20" height="14" viewBox="0 0 20 14" fill="none">
                {a.value === "LEFT" && (
                  <>
                    <line x1="2" y1="2" x2="16" y2="2" stroke="currentColor" strokeWidth="1.5" />
                    <line x1="2" y1="5" x2="12" y2="5" stroke="currentColor" strokeWidth="1.5" />
                    <line x1="2" y1="8" x2="14" y2="8" stroke="currentColor" strokeWidth="1.5" />
                    <line x1="2" y1="11" x2="10" y2="11" stroke="currentColor" strokeWidth="1.5" />
                  </>
                )}
                {a.value === "CENTER" && (
                  <>
                    <line x1="3" y1="2" x2="17" y2="2" stroke="currentColor" strokeWidth="1.5" />
                    <line x1="5" y1="5" x2="15" y2="5" stroke="currentColor" strokeWidth="1.5" />
                    <line x1="4" y1="8" x2="16" y2="8" stroke="currentColor" strokeWidth="1.5" />
                    <line x1="6" y1="11" x2="14" y2="11" stroke="currentColor" strokeWidth="1.5" />
                  </>
                )}
                {a.value === "RIGHT" && (
                  <>
                    <line x1="4" y1="2" x2="18" y2="2" stroke="currentColor" strokeWidth="1.5" />
                    <line x1="8" y1="5" x2="18" y2="5" stroke="currentColor" strokeWidth="1.5" />
                    <line x1="6" y1="8" x2="18" y2="8" stroke="currentColor" strokeWidth="1.5" />
                    <line x1="10" y1="11" x2="18" y2="11" stroke="currentColor" strokeWidth="1.5" />
                  </>
                )}
                {(a.value === "JUSTIFY" || a.value === "DISTRIBUTE" || a.value === "BOTH") && (
                  <>
                    <line x1="2" y1="2" x2="18" y2="2" stroke="currentColor" strokeWidth="1.5" />
                    <line x1="2" y1="5" x2="18" y2="5" stroke="currentColor" strokeWidth="1.5" />
                    <line x1="2" y1="8" x2="18" y2="8" stroke="currentColor" strokeWidth="1.5" />
                    <line x1="2" y1="11" x2={a.value === "JUSTIFY" ? "14" : "18"} y2="11" stroke="currentColor" strokeWidth="1.5" />
                  </>
                )}
              </svg>
            </button>
          ))}
        </div>
      </DialogSection>

      {/* 여백 + 첫 줄 */}
      <div className="flex gap-4 mb-4">
        <div className="flex-1">
          <DialogSection title="여백">
            <div className="space-y-2">
              <div className="flex items-center gap-2">
                <span className="text-xs text-gray-600 w-12">왼쪽</span>
                <input type="number" step="0.1" value={marginLeft} onChange={(e) => setMarginLeft(Number(e.target.value))} className={`${inputClass} flex-1`} />
                <span className="text-[10px] text-gray-400">pt</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-xs text-gray-600 w-12">오른쪽</span>
                <input type="number" step="0.1" value={marginRight} onChange={(e) => setMarginRight(Number(e.target.value))} className={`${inputClass} flex-1`} />
                <span className="text-[10px] text-gray-400">pt</span>
              </div>
            </div>
          </DialogSection>
        </div>
        <div className="flex-1">
          <DialogSection title="첫 줄">
            <div className="space-y-1.5">
              {["보통", "들여쓰기", "내어쓰기"].map((label) => (
                <label key={label} className="flex items-center gap-1.5 text-xs text-gray-700">
                  <input
                    type="radio"
                    name="firstLine"
                    checked={firstLineMode === label}
                    onChange={() => setFirstLineMode(label as typeof firstLineMode)}
                    className="w-3.5 h-3.5"
                  />
                  {label}
                </label>
              ))}
              <div className="flex items-center gap-1 mt-1">
                <input
                  type="number"
                  step="0.1"
                  value={firstLineValue}
                  onChange={(e) => setFirstLineValue(Number(e.target.value))}
                  disabled={firstLineMode === "보통"}
                  className={`${inputClass} w-24 disabled:opacity-40`}
                />
                <span className="text-[10px] text-gray-400">pt</span>
              </div>
            </div>
          </DialogSection>
        </div>
      </div>

      {/* 간격 */}
      <DialogSection title="간격">
        <div className="grid grid-cols-2 gap-x-8 gap-y-2">
          <div className="flex items-center gap-2">
            <span className="text-xs text-gray-600 w-12">줄 간격</span>
            <select className={`${selectClass} flex-1`} defaultValue={lineSpacingType}>
              <option>글자에 따라</option>
              <option>고정 값</option>
              <option>최소</option>
            </select>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-xs text-gray-600 w-12">문단 위</span>
            <input type="number" step="0.1" value={spacingBefore} onChange={(e) => setSpacingBefore(Number(e.target.value))} className={`${inputClass} flex-1`} />
            <span className="text-[10px] text-gray-400">pt</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-xs text-gray-600 w-12" />
            <input type="number" value={lineSpacingValue} onChange={(e) => setLineSpacingValue(Number(e.target.value))} className={`${inputClass} flex-1`} />
            <span className="text-[10px] text-gray-400">%</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-xs text-gray-600 w-12">문단 아래</span>
            <input type="number" step="0.1" value={spacingAfter} onChange={(e) => setSpacingAfter(Number(e.target.value))} className={`${inputClass} flex-1`} />
            <span className="text-[10px] text-gray-400">pt</span>
          </div>
        </div>
        <label className="flex items-center gap-1.5 text-xs text-gray-600 mt-2">
          <input type="checkbox" defaultChecked className="w-3.5 h-3.5" />
          편집 용지의 줄 격자 사용
        </label>
      </DialogSection>

      {/* 줄 나눔 기준 */}
      <DialogSection title="줄 나눔 기준">
        <div className="grid grid-cols-2 gap-x-8 gap-y-2">
          <div className="flex items-center gap-2">
            <span className="text-xs text-gray-600 w-12">한글 단위</span>
            <select className={`${selectClass} flex-1`} defaultValue="글자">
              <option>글자</option>
              <option>어절</option>
            </select>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-xs text-gray-600 w-12">최소 공백</span>
            <input type="number" defaultValue={100} className={`${inputClass} flex-1`} />
            <span className="text-[10px] text-gray-400">%</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-xs text-gray-600 w-12">영어 단위</span>
            <select className={`${selectClass} flex-1`} defaultValue="단어">
              <option>단어</option>
              <option>하이픈</option>
            </select>
          </div>
        </div>
      </DialogSection>
    </>
  );
}

// ── Tab 2: 확장 (Extended) ────────────────────────────────────────────────────

function ExtendedTab() {
  return (
    <>
      {/* 문단 종류 */}
      <DialogSection title="문단 종류">
        <div className="grid grid-cols-2 gap-x-8 gap-y-1.5">
          {["없음", "글머리표 문단", "개요 문단", "번호 문단"].map((label, i) => (
            <label key={label} className="flex items-center gap-1.5 text-xs text-gray-700">
              <input type="radio" name="paraType" defaultChecked={i === 0} className="w-3.5 h-3.5" />
              {label}
            </label>
          ))}
        </div>
        <div className="flex items-center gap-2 mt-2">
          <span className="text-xs text-gray-400 w-10">수준</span>
          <select disabled className="h-7 px-2 text-xs border border-gray-300 rounded bg-white flex-1 disabled:opacity-40">
            <option>1 수준</option>
          </select>
        </div>
      </DialogSection>

      {/* 기타 */}
      <DialogSection title="기타">
        <div className="grid grid-cols-2 gap-x-8 gap-y-1.5">
          {[
            "외톨이줄 보호", "다음 문단과 함께",
            "문단 보호", "문단 앞에서 항상 쪽 나눔",
            "글꼴에 어울리는 줄 높이", "한 줄로 입력",
            "한글과 영어 간격을 자동 조절", "한글과 숫자 간격을 자동 조절",
          ].map((label) => (
            <label key={label} className="flex items-center gap-1.5 text-xs text-gray-600">
              <input type="checkbox" className="w-3.5 h-3.5" />
              {label}
            </label>
          ))}
        </div>
        <div className="flex items-center gap-2 mt-3 pt-2 border-t border-gray-200">
          <span className="text-xs text-gray-600 w-14">세로 정렬</span>
          <select className="h-7 px-2 text-xs border border-gray-300 rounded bg-white flex-1" defaultValue="글꼴 기준">
            <option>글꼴 기준</option>
            <option>위쪽</option>
            <option>가운데</option>
            <option>아래쪽</option>
          </select>
        </div>
      </DialogSection>
    </>
  );
}

// ── Tab 3: 탭 설정 (Tab Settings) ─────────────────────────────────────────────

function TabSettingsTab() {
  const selectClass = "h-7 px-2 text-xs border border-gray-300 rounded bg-white";
  const inputClass = "h-7 px-2 text-xs border border-gray-300 rounded bg-white";

  return (
    <>
      {/* 탭 종류 */}
      <DialogSection title="탭 종류">
        <div className="flex items-center gap-4 mb-2">
          {["왼쪽", "오른쪽", "가운데", "소수점"].map((label, i) => (
            <label key={label} className="flex items-center gap-1.5 text-xs text-gray-700">
              <input type="radio" name="tabType" defaultChecked={i === 0} className="w-3.5 h-3.5" />
              {label}
            </label>
          ))}
        </div>
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2">
            <span className="text-xs text-gray-600">채울 모양</span>
            <select className={`${selectClass} w-28`} defaultValue="선 없음">
              <option>선 없음</option>
              <option>점선</option>
              <option>실선</option>
            </select>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-xs text-gray-600">탭 위치</span>
            <input type="number" step="0.1" defaultValue={5.0} className={`${inputClass} w-20`} />
            <span className="text-[10px] text-gray-400">pt</span>
            <button className="h-7 px-3 text-xs border border-gray-300 rounded bg-white hover:bg-gray-50">
              추가
            </button>
          </div>
        </div>
      </DialogSection>

      {/* 탭 목록 + 지운 탭 목록 */}
      <div className="flex gap-4">
        <div className="flex-1">
          <DialogSection title="탭 목록">
            <div className="border border-gray-200 rounded bg-white min-h-[100px]">
              <div className="grid grid-cols-2 text-[10px] text-gray-500 border-b border-gray-200 px-2 py-1">
                <span>위치</span>
                <span>종류</span>
              </div>
              <div className="px-2 py-1 text-[10px] text-gray-400">
                (없음)
              </div>
            </div>
          </DialogSection>
        </div>
        <div className="flex flex-col justify-center gap-1 pt-6">
          <button className="w-7 h-7 rounded border border-gray-300 bg-white text-red-500 hover:bg-red-50 flex items-center justify-center text-sm">
            ×
          </button>
          <button className="w-7 h-7 rounded border border-gray-300 bg-white text-red-500 hover:bg-red-50 flex items-center justify-center text-sm">
            ×
          </button>
        </div>
        <div className="flex-1">
          <DialogSection title="지운 탭 목록">
            <div className="border border-gray-200 rounded bg-white min-h-[100px]">
              <div className="px-2 py-1 text-[10px] text-gray-400">
                (없음)
              </div>
            </div>
          </DialogSection>
        </div>
      </div>

      {/* 편집 + 기본 탭 */}
      <DialogSection title="편집">
        <div className="flex items-center gap-6">
          <label className="flex items-center gap-1.5 text-xs text-gray-600">
            <input type="checkbox" className="w-3.5 h-3.5" />
            내어쓰기용 자동 탭
          </label>
          <label className="flex items-center gap-1.5 text-xs text-gray-600">
            <input type="checkbox" className="w-3.5 h-3.5" />
            문단 오른쪽 끝 자동 탭
          </label>
        </div>
      </DialogSection>
      <DialogSection title="기본 탭">
        <div className="flex items-center gap-2">
          <span className="text-xs text-gray-600">구역 기본 탭 간격 :</span>
          <span className="text-xs text-gray-800 font-medium">40.0 pt</span>
          <button className="h-7 px-3 text-xs border border-gray-300 rounded bg-white hover:bg-gray-50 ml-2">
            변경
          </button>
        </div>
      </DialogSection>
    </>
  );
}

// ── Tab 4: 테두리/배경 ─────────────────────────────────────────────────────────

function ParaBorderBackgroundTab() {
  const selectClass = "h-7 px-2 text-xs border border-gray-300 rounded bg-white";
  const inputClass = "h-7 px-2 text-xs border border-gray-300 rounded bg-white";

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
              </select>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-xs text-gray-600 w-10">굵기</span>
              <select className={`${selectClass} flex-1`} defaultValue="0.1 mm">
                <option>0.1 mm</option>
                <option>0.3 mm</option>
                <option>0.5 mm</option>
                <option>1.0 mm</option>
              </select>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-xs text-gray-600 w-10">색</span>
              <input type="color" defaultValue="#000000" className="w-24 h-7 rounded border border-gray-300" />
            </div>
            <label className="flex items-center gap-1.5 text-xs text-gray-600 mt-1">
              <input type="checkbox" className="w-3.5 h-3.5" />
              문단 테두리 연결
            </label>
            <label className="flex items-center gap-1.5 text-xs text-gray-600">
              <input type="checkbox" defaultChecked className="w-3.5 h-3.5" />
              선 모양 바로 적용
            </label>
          </div>
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

      {/* 간격 */}
      <DialogSection title="간격">
        <div className="grid grid-cols-2 gap-x-4 gap-y-2">
          <div className="flex items-center gap-2">
            <span className="text-xs text-gray-600 w-10">왼쪽</span>
            <input type="number" step="0.01" defaultValue={0} className={`${inputClass} flex-1`} />
            <span className="text-[10px] text-gray-400">mm</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-xs text-gray-600 w-10">오른쪽</span>
            <input type="number" step="0.01" defaultValue={0} className={`${inputClass} flex-1`} />
            <span className="text-[10px] text-gray-400">mm</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-xs text-gray-600 w-10">위쪽</span>
            <input type="number" step="0.01" defaultValue={0} className={`${inputClass} flex-1`} />
            <span className="text-[10px] text-gray-400">mm</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-xs text-gray-600 w-10">아래쪽</span>
            <input type="number" step="0.01" defaultValue={0} className={`${inputClass} flex-1`} />
            <span className="text-[10px] text-gray-400">mm</span>
          </div>
        </div>
        <label className="flex items-center gap-1.5 text-xs text-gray-600 mt-2">
          <input type="checkbox" className="w-3.5 h-3.5" />
          문단 여백 무시
        </label>
      </DialogSection>
    </>
  );
}

// ── Main Dialog ───────────────────────────────────────────────────────────────

export function ParaFormatDialog() {
  const open = useEditorStore((s) => s.uiState.paraFormatDialogOpen);
  const closeParaFormatDialog = useEditorStore((s) => s.closeParaFormatDialog);
  const [activeTab, setActiveTab] = useState(0);

  const handleApply = useCallback(() => {
    closeParaFormatDialog();
  }, [closeParaFormatDialog]);

  return (
    <Dialog title="문단 모양" open={open} onClose={closeParaFormatDialog} onApply={handleApply} width={580}>
      <DialogTabs tabs={TABS} activeTab={activeTab} onTabChange={setActiveTab} />
      {activeTab === 0 && <BasicTab />}
      {activeTab === 1 && <ExtendedTab />}
      {activeTab === 2 && <TabSettingsTab />}
      {activeTab === 3 && <ParaBorderBackgroundTab />}

      {/* 미리보기 (only for basic tab) */}
      {activeTab === 0 && (
        <div className="mt-4">
          <div className="text-xs font-bold text-gray-800 mb-1.5">미리보기</div>
          <div className="bg-white border border-gray-200 rounded-md p-3 min-h-[70px]">
            <div className="text-[9px] text-gray-500 leading-relaxed">
              이전 문단 이전 문단 이전 문단 이전 문단 이전 문단 이전 문단 이전 문단 이전 문단 이전 문단 이전 문단 이전 문단 이전 문단 이전 문단
            </div>
            <div className="text-[9px] text-gray-700 leading-relaxed mt-1">
              가나다라AaBbCc12345 가나다라AaBbCc12345 가나다라AaBbCc12345
            </div>
          </div>
        </div>
      )}
    </Dialog>
  );
}
