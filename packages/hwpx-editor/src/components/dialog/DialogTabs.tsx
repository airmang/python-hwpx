"use client";

interface DialogTabsProps {
  tabs: string[];
  activeTab: number;
  onTabChange: (index: number) => void;
}

export function DialogTabs({ tabs, activeTab, onTabChange }: DialogTabsProps) {
  return (
    <div className="mb-5 flex w-full gap-1 rounded-xl border border-gray-200 bg-gray-100 p-1">
      {tabs.map((label, idx) => (
        <button
          key={label}
          onClick={() => onTabChange(idx)}
          className={`h-9 flex-1 rounded-lg border text-sm transition-colors ${
            activeTab === idx
              ? "border-gray-300 bg-white font-semibold text-gray-900 shadow-sm"
              : "border-transparent bg-transparent text-gray-500 hover:text-gray-700"
          }`}
        >
          {label}
        </button>
      ))}
    </div>
  );
}
