"use client";

import { useEffect, useState } from "react";
import { useEditorStore } from "@/lib/store";
import { Dialog } from "./Dialog";

interface WordCountStats {
  characters: number;
  charactersNoSpaces: number;
  words: number;
  paragraphs: number;
  lines: number;
  pages: number;
}

function countStats(text: string, pageCount: number): WordCountStats {
  const lines = text.split("\n");
  const paragraphs = lines.filter((line) => line.trim().length > 0);
  const characters = text.length;
  const charactersNoSpaces = text.replace(/\s/g, "").length;

  // Count words (Korean: treat each character as a word, English: split by spaces)
  let words = 0;
  const segments = text.split(/\s+/).filter((s) => s.length > 0);
  for (const segment of segments) {
    // Count Korean characters individually
    const koreanChars = (segment.match(/[\uAC00-\uD7AF]/g) || []).length;
    // Count English words (sequences of non-Korean characters)
    const nonKorean = segment.replace(/[\uAC00-\uD7AF]/g, " ").split(/\s+/).filter((s) => s.length > 0);
    words += koreanChars + nonKorean.length;
  }

  return {
    characters,
    charactersNoSpaces,
    words,
    paragraphs: paragraphs.length,
    lines: lines.length,
    pages: pageCount,
  };
}

export function WordCountDialog() {
  const uiState = useEditorStore((s) => s.uiState);
  const closeWordCountDialog = useEditorStore((s) => s.closeWordCountDialog);
  const doc = useEditorStore((s) => s.doc);
  const viewModel = useEditorStore((s) => s.viewModel);

  const [stats, setStats] = useState<WordCountStats | null>(null);

  useEffect(() => {
    if (uiState.wordCountDialogOpen && doc && viewModel) {
      const text = doc.text;
      const sectionCount = viewModel.sections.length;
      setStats(countStats(text, sectionCount));
    }
  }, [uiState.wordCountDialogOpen, doc, viewModel]);

  const statItems = stats
    ? [
        { label: "글자 수 (공백 제외)", value: stats.charactersNoSpaces.toLocaleString(), highlight: true },
        { label: "글자 수 (공백 포함)", value: stats.characters.toLocaleString() },
        { label: "낱말 수", value: stats.words.toLocaleString() },
        { label: "문단 수", value: stats.paragraphs.toLocaleString() },
        { label: "줄 수", value: stats.lines.toLocaleString() },
        { label: "쪽 수", value: stats.pages.toLocaleString() },
      ]
    : [];

  return (
    <Dialog
      title="글자 수 세기"
      open={uiState.wordCountDialogOpen}
      onClose={closeWordCountDialog}
      width={320}
    >
      <div className="space-y-1.5">
        {statItems.map((item, idx) => (
          <div
            key={item.label}
            className={`flex justify-between items-center py-1.5 px-2 rounded ${
              idx === 0 ? "bg-blue-50 border border-blue-200" : "bg-gray-50"
            }`}
          >
            <span className={`text-xs ${idx === 0 ? "text-blue-700 font-medium" : "text-gray-600"}`}>
              {item.label}
            </span>
            <span className={`text-sm font-medium ${idx === 0 ? "text-blue-800" : "text-gray-800"}`}>
              {item.value}
            </span>
          </div>
        ))}
      </div>

      <div className="flex justify-end mt-4">
        <button
          onClick={closeWordCountDialog}
          className="px-4 py-1.5 text-xs border border-gray-300 rounded bg-white hover:bg-gray-50 text-gray-700"
        >
          닫기
        </button>
      </div>
    </Dialog>
  );
}
