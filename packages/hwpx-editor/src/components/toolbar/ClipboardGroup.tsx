"use client";

import { Clipboard, Copy, ClipboardPaste, Paintbrush } from "lucide-react";
import { ToolbarButton } from "./ToolbarButton";
import { RibbonGroup } from "./RibbonGroup";

export function ClipboardGroup() {
  return (
    <RibbonGroup label="클립보드">
      <ToolbarButton
        icon={<Clipboard className="w-4 h-4" />}
        title="오려두기 (Ctrl+X)"
        onClick={() => document.execCommand("cut")}
      />
      <ToolbarButton
        icon={<Copy className="w-4 h-4" />}
        title="복사 (Ctrl+C)"
        onClick={() => document.execCommand("copy")}
      />
      <ToolbarButton
        icon={<ClipboardPaste className="w-4 h-4" />}
        title="붙이기 (Ctrl+V)"
        onClick={() => document.execCommand("paste")}
      />
      <ToolbarButton
        icon={<Paintbrush className="w-4 h-4" />}
        title="모양 복사"
        disabled
      />
    </RibbonGroup>
  );
}
