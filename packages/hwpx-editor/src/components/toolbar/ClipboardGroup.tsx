"use client";

import { Clipboard, Copy, ClipboardPaste, Paintbrush } from "lucide-react";
import { ToolbarButton } from "./ToolbarButton";
import { RibbonGroup } from "./RibbonGroup";

export function ClipboardGroup() {
  return (
    <RibbonGroup label="클립보드">
      <ToolbarButton
        icon={<Clipboard className="w-5 h-5" />}
        label="잘라내기"
        layout="vertical"
        title="오려두기 (Ctrl+X)"
        onClick={() => document.execCommand("cut")}
      />
      <ToolbarButton
        icon={<Copy className="w-5 h-5" />}
        label="복사"
        layout="vertical"
        title="복사 (Ctrl+C)"
        onClick={() => document.execCommand("copy")}
      />
      <ToolbarButton
        icon={<ClipboardPaste className="w-5 h-5" />}
        label="붙이기"
        layout="vertical"
        title="붙이기 (Ctrl+V)"
        onClick={() => document.execCommand("paste")}
      />
      <ToolbarButton
        icon={<Paintbrush className="w-5 h-5" />}
        label="모양복사"
        layout="vertical"
        title="모양 복사"
        disabled
      />
    </RibbonGroup>
  );
}
