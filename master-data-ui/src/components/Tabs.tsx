"use client";

import { ChevronDown } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useTranslations } from "next-intl";

interface TabItem {
  id: string;
  label: string;
}

interface TabsProps {
  tabs: TabItem[];
  active: string;
  onChange: (id: string) => void;
}

const MAX_VISIBLE_TABS = 5;

export default function Tabs({ tabs, active, onChange }: TabsProps) {
  const t = useTranslations();
  const [isMoreOpen, setIsMoreOpen] = useState(false);
  const moreMenuRef = useRef<HTMLDivElement | null>(null);

  const visibleTabs = tabs.slice(0, MAX_VISIBLE_TABS);
  const moreTabs = tabs.slice(MAX_VISIBLE_TABS);
  const hasMoreTabs = moreTabs.length > 0;
  const isMoreActive = hasMoreTabs && moreTabs.some((tab) => tab.id === active);
  const activeMoreTab = moreTabs.find((tab) => tab.id === active);

  useEffect(() => {
    if (!isMoreOpen) return;

    const handleClickOutside = (event: MouseEvent) => {
      if (
        moreMenuRef.current &&
        !moreMenuRef.current.contains(event.target as Node)
      ) {
        setIsMoreOpen(false);
      }
    };

    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [isMoreOpen]);

  useEffect(() => {
    setIsMoreOpen(false);
  }, [active]);

  return (
    <div className="flex flex-wrap items-end gap-2 mb-0 ml-5" role="tablist">
      {visibleTabs.map((tab) => {
        const isActive = active === tab.id;
        return (
          <button
            key={tab.id}
            type="button"
            role="tab"
            aria-selected={isActive}
            className={`inline-flex items-center justify-center gap-1.5 min-w-30 max-w-45 px-6 py-3 border-none rounded-t-[10px] rounded-b-none bg-[#e1e1e1] text-black text-[18px] font-semibold leading-[1.3] cursor-pointer transition-colors duration-150 ${isActive ? "bg-[#f5bb1a]" : "hover:bg-[#d4d4d4]"}`}
            onClick={() => onChange(tab.id)}
          >
            <span className="block w-full overflow-hidden text-ellipsis whitespace-nowrap text-center">
              {tab.label}
            </span>
          </button>
        );
      })}

      {hasMoreTabs && (
        <div className="relative" ref={moreMenuRef}>
          <button
            type="button"
            className={`inline-flex items-center justify-center gap-1.5 min-w-30 max-w-45 px-4 py-2 border-none rounded-t-[10px] rounded-b-none bg-[#e1e1e1] text-black text-lg font-medium leading-[1.3] cursor-pointer transition-colors duration-150 ${isMoreActive ? "bg-[#f5bb1a]" : "hover:bg-[#d4d4d4]"}`}
            onClick={() => setIsMoreOpen((prev) => !prev)}
            aria-expanded={isMoreOpen}
            aria-haspopup="listbox"
          >
            <span className="block w-full overflow-hidden text-ellipsis whitespace-nowrap text-center">
              {activeMoreTab ? activeMoreTab.label : t("more")}
            </span>
            <ChevronDown
              className={`w-5 h-5 shrink-0 transition-transform duration-150 ${isMoreOpen ? "rotate-180" : ""}`}
              aria-hidden
            />
          </button>

          {isMoreOpen && (
            <div className="absolute left-0 top-full z-50 min-w-30 max-w-62.5 bg-white border border-[#f5bb1a] rounded-b-[10px] rounded-tr-[10px] shadow-[0_2px_6px_rgba(0,0,0,0.25)] overflow-hidden" role="listbox">
              {moreTabs.map((tab) => {
                const isActive = active === tab.id;
                return (
                  <button
                    key={tab.id}
                    type="button"
                    role="option"
                    aria-selected={isActive}
                    className={`block w-full px-4 py-2 border-none bg-transparent text-black text-lg font-medium text-left cursor-pointer transition-colors duration-150 ${isActive ? "bg-[rgba(245,187,26,0.25)] font-semibold" : "hover:bg-[rgba(245,187,26,0.25)]"}`}
                    onClick={() => onChange(tab.id)}
                  >
                    {tab.label}
                  </button>
                );
              })}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
