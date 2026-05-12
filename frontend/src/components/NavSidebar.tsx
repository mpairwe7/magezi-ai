"use client";
import { useEffect, useState } from "react";

type Page = "chat" | "subjects" | "history" | "settings";

const NAV_ITEMS: { id: Page; label: string; icon: string }[] = [
  { id: "chat", label: "Tutor", icon: "M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" },
  { id: "subjects", label: "Subjects", icon: "M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" },
  { id: "history", label: "History", icon: "M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" },
  { id: "settings", label: "Settings", icon: "M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.066 2.573c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.573 1.066c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.066-2.573c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z M15 12a3 3 0 11-6 0 3 3 0 016 0z" },
];

export function MobileTopBar({ onMenuOpen }: { onMenuOpen: () => void }) {
  return (
    <header className="lg:hidden sticky top-0 z-30 bg-[#040a06] px-4 py-3 flex items-center justify-between safe-top">
      <button onClick={onMenuOpen} className="w-10 h-10 flex items-center justify-center rounded-lg text-emerald-300 hover:bg-white/10" aria-label="Open menu">
        <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M4 6h16M4 12h16M4 18h16" />
        </svg>
      </button>
      <span className="text-white font-bold text-sm tracking-tight">Magezi</span>
      <span className="w-2.5 h-2.5 rounded-full bg-emerald-400 animate-pulse-dot" />
    </header>
  );
}

export function MobileBottomNav({ currentPage, onNavigate }: { currentPage: string; onNavigate: (p: Page) => void }) {
  return (
    <nav className="lg:hidden fixed bottom-0 left-0 right-0 z-30 bg-[#040a06] border-t border-emerald-900/30 safe-bottom">
      <div className="flex items-stretch">
        {NAV_ITEMS.map((item) => {
          const active = currentPage === item.id;
          return (
            <button key={item.id} onClick={() => onNavigate(item.id)}
              className={`relative flex-1 flex flex-col items-center justify-center py-2 gap-0.5 min-h-[56px] transition-colors ${active ? "text-emerald-400" : "text-slate-500 active:text-slate-300"}`}
              aria-label={item.label} aria-current={active ? "page" : undefined}
            >
              {active && <div className="absolute top-0 left-1/2 -translate-x-1/2 w-8 h-0.5 bg-emerald-400 rounded-full" />}
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={active ? 2 : 1.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d={item.icon} />
              </svg>
              <span className="text-[10px] font-medium">{item.label}</span>
            </button>
          );
        })}
      </div>
    </nav>
  );
}

export function NavSidebar({ currentPage, onNavigate, open, onClose }: {
  currentPage: string; onNavigate: (p: Page) => void; open: boolean; onClose: () => void;
}) {
  const [collapsed, setCollapsed] = useState(false);

  useEffect(() => {
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape" && open) onClose(); };
    window.addEventListener("keydown", esc);
    if (open) document.body.classList.add("menu-open");
    else document.body.classList.remove("menu-open");
    return () => { window.removeEventListener("keydown", esc); document.body.classList.remove("menu-open"); };
  }, [open, onClose]);

  return (
    <>
      {open && <div className="mobile-overlay lg:hidden" onClick={onClose} aria-hidden="true" />}
      <aside className={`bg-[#040a06] h-full flex flex-col shrink-0 transition-all duration-200 fixed lg:relative z-50 ${open ? "translate-x-0" : "-translate-x-full lg:translate-x-0"} w-64 ${collapsed ? "lg:w-16" : "lg:w-56"}`}
        role="navigation" aria-label="Main navigation">
        <div className="px-4 py-5 flex items-center gap-3 border-b border-emerald-900/30">
          <div className="w-8 h-8 rounded-lg bg-emerald-600 flex items-center justify-center text-white font-bold text-sm shrink-0">M</div>
          <div className={`${collapsed ? "hidden" : ""} animate-fade-in`}>
            <div className="text-white font-bold text-sm">Magezi</div>
            <div className="text-emerald-400/60 text-[10px]">A-Level STEM Tutor</div>
          </div>
          <button onClick={onClose} className="lg:hidden ml-auto w-8 h-8 flex items-center justify-center rounded-lg text-slate-400 hover:text-white hover:bg-white/10" aria-label="Close">
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
        <nav className="flex-1 py-4 px-2 space-y-1 overflow-y-auto">
          {NAV_ITEMS.map((item) => {
            const active = currentPage === item.id;
            return (
              <button key={item.id} onClick={() => { onNavigate(item.id); onClose(); }}
                className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors ${active ? "bg-emerald-500/15 text-emerald-400" : "text-slate-300 hover:bg-white/5 hover:text-white"}`}
                aria-label={item.label} aria-current={active ? "page" : undefined}>
                <svg className="w-5 h-5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d={item.icon} />
                </svg>
                <span className={`${collapsed ? "hidden" : ""} animate-fade-in`}>{item.label}</span>
              </button>
            );
          })}
        </nav>
        <div className="px-3 py-4 border-t border-emerald-900/30">
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse-dot shrink-0" />
            <span className={`text-xs text-slate-300 ${collapsed ? "hidden" : ""}`}>LLM Ready</span>
          </div>
        </div>
        <button onClick={() => setCollapsed(!collapsed)} className="hidden lg:block px-3 py-3 border-t border-emerald-900/30 text-slate-500 hover:text-slate-300 transition-colors" aria-label={collapsed ? "Expand" : "Collapse"}>
          <svg className={`w-4 h-4 mx-auto transition-transform ${collapsed ? "rotate-180" : ""}`} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M11 19l-7-7 7-7m8 14l-7-7 7-7" />
          </svg>
        </button>
      </aside>
    </>
  );
}
