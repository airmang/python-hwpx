"use client";

import { useState, useCallback, useMemo } from "react";
import { useEditorStore } from "@/lib/store";
import { Dialog } from "./Dialog";
import { DialogTabs } from "./DialogTabs";

// ── Character categories ─────────────────────────────────────────────────────

interface CharCategory {
  label: string;
  chars: string[];
}

const CATEGORIES: CharCategory[] = [
  {
    label: "특수 문자",
    chars: [
      "※", "☆", "★", "○", "●", "◎", "◇", "◆", "□", "■", "△", "▲", "▽", "▼", "◁", "◀", "▷", "▶",
      "♤", "♠", "♡", "♥", "♧", "♣", "♢", "♦", "☎", "☏", "☜", "☞", "♨", "☀", "☁", "☂",
      "♬", "♪", "♩", "♭", "♯", "†", "‡", "¶", "§", "©", "®", "™", "℃", "℉", "㎜", "㎝",
      "㎞", "㎡", "㎥", "㏄", "㎏", "㎎", "㎍", "㎖", "㎗", "ℓ", "㎐", "㎑", "㎒", "㎓", "㎔", "㏊",
      "㏘", "㏗", "㎴", "㎵", "㎶", "㎷", "㎸", "㎹", "㎺", "㎻", "㎼", "㎽", "㎾", "㎿", "㎀", "㎁",
      "㎂", "㎃", "㎄", "㎈", "㎉", "㎊", "㎋", "㎌", "㎕", "㎙", "㎚", "㎛", "㎟", "㎠", "㎢", "㎣",
    ],
  },
  {
    label: "원/괄호 문자",
    chars: [
      "①", "②", "③", "④", "⑤", "⑥", "⑦", "⑧", "⑨", "⑩", "⑪", "⑫", "⑬", "⑭", "⑮",
      "⑴", "⑵", "⑶", "⑷", "⑸", "⑹", "⑺", "⑻", "⑼", "⑽", "⑾", "⑿", "⒀", "⒁", "⒂",
      "Ⓐ", "Ⓑ", "Ⓒ", "Ⓓ", "Ⓔ", "Ⓕ", "Ⓖ", "Ⓗ", "Ⓘ", "Ⓙ", "Ⓚ", "Ⓛ", "Ⓜ", "Ⓝ", "Ⓞ",
      "Ⓟ", "Ⓠ", "Ⓡ", "Ⓢ", "Ⓣ", "Ⓤ", "Ⓥ", "Ⓦ", "Ⓧ", "Ⓨ", "Ⓩ",
      "ⓐ", "ⓑ", "ⓒ", "ⓓ", "ⓔ", "ⓕ", "ⓖ", "ⓗ", "ⓘ", "ⓙ", "ⓚ", "ⓛ", "ⓜ", "ⓝ", "ⓞ",
      "ⓟ", "ⓠ", "ⓡ", "ⓢ", "ⓣ", "ⓤ", "ⓥ", "ⓦ", "ⓧ", "ⓨ", "ⓩ",
      "㉠", "㉡", "㉢", "㉣", "㉤", "㉥", "㉦", "㉧", "㉨", "㉩", "㉪", "㉫", "㉬", "㉭",
      "㈀", "㈁", "㈂", "㈃", "㈄", "㈅", "㈆", "㈇", "㈈", "㈉", "㈊", "㈋", "㈌", "㈍",
    ],
  },
  {
    label: "수학 기호",
    chars: [
      "±", "×", "÷", "≠", "≤", "≥", "∞", "∴", "∵", "∈", "∋", "⊂", "⊃", "⊆", "⊇", "∪",
      "∩", "∧", "∨", "¬", "⇒", "⇔", "∀", "∃", "∅", "∇", "∂", "∫", "∬", "∮", "√", "∑",
      "∏", "≡", "≒", "≪", "≫", "∝", "∠", "⊥", "⌒", "∥", "∼", "≈", "⊙", "∘", "⊕", "⊗",
      "⁰", "¹", "²", "³", "⁴", "⁵", "⁶", "⁷", "⁸", "⁹", "⁺", "⁻", "⁼", "⁽", "⁾", "ⁿ",
      "₀", "₁", "₂", "₃", "₄", "₅", "₆", "₇", "₈", "₉", "₊", "₋", "₌", "₍", "₎",
      "¼", "½", "¾", "⅓", "⅔", "⅕", "⅖", "⅗", "⅘", "⅙", "⅚", "⅛", "⅜", "⅝", "⅞",
    ],
  },
  {
    label: "화살표",
    chars: [
      "←", "→", "↑", "↓", "↔", "↕", "↖", "↗", "↘", "↙", "⇐", "⇒", "⇑", "⇓", "⇔", "⇕",
      "↠", "↣", "↦", "↩", "↪", "↰", "↱", "↲", "↳", "↴", "↵", "↶", "↷", "↺", "↻",
      "⟵", "⟶", "⟷", "⟸", "⟹", "⟺",
      "➔", "➘", "➙", "➚", "➛", "➜", "➝", "➞", "➟", "➠", "➡", "➢", "➣", "➤", "➥", "➦",
    ],
  },
  {
    label: "도형",
    chars: [
      "■", "□", "▢", "▣", "▤", "▥", "▦", "▧", "▨", "▩", "▪", "▫", "▬", "▭", "▮", "▯",
      "▰", "▱", "▲", "△", "▴", "▵", "▶", "▷", "▸", "▹", "►", "▻", "▼", "▽", "▾", "▿",
      "◀", "◁", "◂", "◃", "◄", "◅", "◆", "◇", "◈", "◉", "◊", "○", "◌", "◍", "◎", "●",
      "◐", "◑", "◒", "◓", "◔", "◕", "◖", "◗", "◘", "◙", "◚", "◛", "◜", "◝", "◞", "◟",
      "◠", "◡", "◢", "◣", "◤", "◥", "◦", "◧", "◨", "◩", "◪", "◫", "◬", "◭", "◮", "◯",
    ],
  },
  {
    label: "선 그리기",
    chars: [
      "─", "━", "│", "┃", "┄", "┅", "┆", "┇", "┈", "┉", "┊", "┋",
      "┌", "┍", "┎", "┏", "┐", "┑", "┒", "┓", "└", "┕", "┖", "┗",
      "┘", "┙", "┚", "┛", "├", "┝", "┞", "┟", "┠", "┡", "┢", "┣",
      "┤", "┥", "┦", "┧", "┨", "┩", "┪", "┫", "┬", "┭", "┮", "┯",
      "┰", "┱", "┲", "┳", "┴", "┵", "┶", "┷", "┸", "┹", "┺", "┻",
      "┼", "┽", "┾", "┿", "╀", "╁", "╂", "╃", "╄", "╅", "╆", "╇",
      "╈", "╉", "╊", "╋", "╌", "╍", "╎", "╏",
      "═", "║", "╒", "╓", "╔", "╕", "╖", "╗", "╘", "╙", "╚", "╛",
      "╜", "╝", "╞", "╟", "╠", "╡", "╢", "╣", "╤", "╥", "╦", "╧",
      "╨", "╩", "╪", "╫", "╬",
    ],
  },
  {
    label: "그리스/라틴",
    chars: [
      "Α", "Β", "Γ", "Δ", "Ε", "Ζ", "Η", "Θ", "Ι", "Κ", "Λ", "Μ", "Ν", "Ξ", "Ο", "Π",
      "Ρ", "Σ", "Τ", "Υ", "Φ", "Χ", "Ψ", "Ω",
      "α", "β", "γ", "δ", "ε", "ζ", "η", "θ", "ι", "κ", "λ", "μ", "ν", "ξ", "ο", "π",
      "ρ", "σ", "τ", "υ", "φ", "χ", "ψ", "ω",
      "À", "Á", "Â", "Ã", "Ä", "Å", "Æ", "Ç", "È", "É", "Ê", "Ë", "Ì", "Í", "Î", "Ï",
      "Ð", "Ñ", "Ò", "Ó", "Ô", "Õ", "Ö", "Ø", "Ù", "Ú", "Û", "Ü", "Ý", "Þ", "ß",
      "à", "á", "â", "ã", "ä", "å", "æ", "ç", "è", "é", "ê", "ë", "ì", "í", "î", "ï",
      "ð", "ñ", "ò", "ó", "ô", "õ", "ö", "ø", "ù", "ú", "û", "ü", "ý", "þ", "ÿ",
    ],
  },
  {
    label: "한글 자모",
    chars: [
      "ㄱ", "ㄲ", "ㄳ", "ㄴ", "ㄵ", "ㄶ", "ㄷ", "ㄸ", "ㄹ", "ㄺ", "ㄻ", "ㄼ", "ㄽ", "ㄾ", "ㄿ", "ㅀ",
      "ㅁ", "ㅂ", "ㅃ", "ㅄ", "ㅅ", "ㅆ", "ㅇ", "ㅈ", "ㅉ", "ㅊ", "ㅋ", "ㅌ", "ㅍ", "ㅎ",
      "ㅏ", "ㅐ", "ㅑ", "ㅒ", "ㅓ", "ㅔ", "ㅕ", "ㅖ", "ㅗ", "ㅘ", "ㅙ", "ㅚ", "ㅛ", "ㅜ", "ㅝ", "ㅞ",
      "ㅟ", "ㅠ", "ㅡ", "ㅢ", "ㅣ",
      "ㆍ", "ㆎ",
    ],
  },
  {
    label: "일본어",
    chars: [
      "ぁ", "あ", "ぃ", "い", "ぅ", "う", "ぇ", "え", "ぉ", "お", "か", "が", "き", "ぎ", "く", "ぐ",
      "け", "げ", "こ", "ご", "さ", "ざ", "し", "じ", "す", "ず", "せ", "ぜ", "そ", "ぞ", "た", "だ",
      "ち", "ぢ", "っ", "つ", "づ", "て", "で", "と", "ど", "な", "に", "ぬ", "ね", "の", "は", "ば",
      "ァ", "ア", "ィ", "イ", "ゥ", "ウ", "ェ", "エ", "ォ", "オ", "カ", "ガ", "キ", "ギ", "ク", "グ",
      "ケ", "ゲ", "コ", "ゴ", "サ", "ザ", "シ", "ジ", "ス", "ズ", "セ", "ゼ", "ソ", "ゾ", "タ", "ダ",
      "チ", "ヂ", "ッ", "ツ", "ヅ", "テ", "デ", "ト", "ド", "ナ", "ニ", "ヌ", "ネ", "ノ", "ハ", "バ",
    ],
  },
  {
    label: "기타 기호",
    chars: [
      "、", "。", "〃", "〈", "〉", "《", "》", "「", "」", "『", "』", "【", "】", "〔", "〕", "〖",
      "〗", "〘", "〙", "〚", "〛", "〜", "〝", "〞", "〟", "〰",
      "✁", "✂", "✃", "✄", "✆", "✇", "✈", "✉", "✌", "✍", "✎", "✏", "✐", "✑", "✒", "✓",
      "✔", "✕", "✖", "✗", "✘", "✙", "✚", "✛", "✜", "✝", "✞", "✟", "✠", "✡", "✢", "✣",
      "✤", "✥", "✦", "✧", "✩", "✪", "✫", "✬", "✭", "✮", "✯", "✰", "✱", "✲", "✳", "✴",
      "✵", "✶", "✷", "✸", "✹", "✺", "✻", "✼", "✽", "✾", "✿", "❀", "❁", "❂", "❃", "❄",
    ],
  },
];

const TAB_LABELS = CATEGORIES.map((c) => c.label);

// ── Helpers ──────────────────────────────────────────────────────────────────

function charCodeInfo(ch: string): string {
  const cp = ch.codePointAt(0);
  if (cp === undefined) return "";
  return `U+${cp.toString(16).toUpperCase().padStart(4, "0")}`;
}

// ── Main Dialog ──────────────────────────────────────────────────────────────

export function CharMapDialog() {
  const open = useEditorStore((s) => s.uiState.charMapDialogOpen);
  const closeCharMapDialog = useEditorStore((s) => s.closeCharMapDialog);
  const insertTextAtCursor = useEditorStore((s) => s.insertTextAtCursor);

  const [activeTab, setActiveTab] = useState(0);
  const [selected, setSelected] = useState<string | null>(null);
  const [recentChars, setRecentChars] = useState<string[]>([]);

  const category = CATEGORIES[activeTab]!;

  const handleCharClick = useCallback((ch: string) => {
    setSelected(ch);
  }, []);

  const handleCharDoubleClick = useCallback((ch: string) => {
    insertTextAtCursor(ch);
    setRecentChars((prev) => {
      const next = [ch, ...prev.filter((c) => c !== ch)];
      return next.slice(0, 32);
    });
  }, [insertTextAtCursor]);

  const handleInsert = useCallback(() => {
    if (!selected) return;
    insertTextAtCursor(selected);
    setRecentChars((prev) => {
      const next = [selected, ...prev.filter((c) => c !== selected)];
      return next.slice(0, 32);
    });
  }, [selected, insertTextAtCursor]);

  const selectedInfo = useMemo(() => {
    if (!selected) return "";
    return charCodeInfo(selected);
  }, [selected]);

  return (
    <Dialog title="문자표" open={open} onClose={closeCharMapDialog} onApply={handleInsert} width={640}>
      {/* Category tabs — use a compact horizontal scroll instead of DialogTabs for many categories */}
      <div className="flex gap-0 mb-3 overflow-x-auto border-b border-gray-200 pb-0">
        {TAB_LABELS.map((label, idx) => (
          <button
            key={label}
            onClick={() => { setActiveTab(idx); setSelected(null); }}
            className={`px-3 py-1.5 text-xs whitespace-nowrap border-b-2 transition-colors ${
              activeTab === idx
                ? "border-blue-500 text-blue-700 font-semibold"
                : "border-transparent text-gray-500 hover:text-gray-700"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {/* Character grid */}
      <div className="grid gap-0 border border-gray-300 rounded bg-white overflow-hidden"
        style={{ gridTemplateColumns: "repeat(16, 1fr)" }}
      >
        {category.chars.map((ch, idx) => (
          <button
            key={`${ch}-${idx}`}
            onClick={() => handleCharClick(ch)}
            onDoubleClick={() => handleCharDoubleClick(ch)}
            className={`aspect-square flex items-center justify-center text-sm border border-gray-100 hover:bg-blue-50 transition-colors ${
              selected === ch
                ? "bg-blue-100 ring-2 ring-blue-400 ring-inset font-bold"
                : "bg-white"
            }`}
            title={`${ch} (${charCodeInfo(ch)})`}
          >
            {ch}
          </button>
        ))}
      </div>

      {/* Info bar */}
      <div className="flex items-center justify-between mt-3">
        <div className="flex items-center gap-3">
          {selected && (
            <>
              <span className="text-2xl">{selected}</span>
              <span className="text-xs text-gray-500">{selectedInfo}</span>
            </>
          )}
          {!selected && (
            <span className="text-xs text-gray-400">문자를 선택하세요. 더블 클릭으로 바로 입력합니다.</span>
          )}
        </div>
        <button
          onClick={handleInsert}
          disabled={!selected}
          className={`px-4 py-1.5 text-xs rounded border ${
            selected
              ? "bg-blue-500 text-white border-blue-600 hover:bg-blue-600"
              : "bg-gray-100 text-gray-400 border-gray-200 cursor-default"
          }`}
        >
          넣기
        </button>
      </div>

      {/* Recent characters */}
      {recentChars.length > 0 && (
        <div className="mt-3">
          <div className="text-xs font-bold text-gray-700 mb-1">최근 사용</div>
          <div className="flex flex-wrap gap-0.5">
            {recentChars.map((ch, idx) => (
              <button
                key={`recent-${idx}`}
                onClick={() => handleCharClick(ch)}
                onDoubleClick={() => handleCharDoubleClick(ch)}
                className="w-7 h-7 flex items-center justify-center text-sm border border-gray-200 rounded hover:bg-blue-50 bg-white"
                title={`${ch} (${charCodeInfo(ch)})`}
              >
                {ch}
              </button>
            ))}
          </div>
        </div>
      )}
    </Dialog>
  );
}
