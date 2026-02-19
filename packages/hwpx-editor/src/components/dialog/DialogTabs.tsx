"use client";

interface DialogTabsProps {
  tabs: string[];
  activeTab: number;
  onTabChange: (index: number) => void;
}

export function DialogTabs({ tabs, activeTab, onTabChange }: DialogTabsProps) {
  return (
    <div className="flex justify-center gap-0 mb-4">
      {tabs.map((label, idx) => (
        <button
          key={label}
          onClick={() => onTabChange(idx)}
          className={`px-4 py-1.5 text-xs border transition-colors ${
            activeTab === idx
              ? "bg-white border-gray-300 font-semibold text-gray-900 shadow-sm"
              : "bg-transparent border-transparent text-gray-500 hover:text-gray-700"
          } ${idx === 0 ? "rounded-l" : ""} ${idx === tabs.length - 1 ? "rounded-r" : ""}`}
        >
          {label}
        </button>
      ))}
    </div>
  );
}
