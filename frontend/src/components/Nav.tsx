"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV_ITEMS = [
  { href: "/", label: "Dashboard", icon: "▦" },
  { href: "/agents", label: "Agents", icon: "◈" },
  { href: "/probability", label: "Probability", icon: "◯" },
  { href: "/backtest", label: "Backtest", icon: "↻" },
  { href: "/journal", label: "Journal", icon: "▤" },
];

export default function Nav() {
  const pathname = usePathname();

  return (
    <aside className="w-16 md:w-56 bg-bg-secondary border-r border-border flex flex-col">
      {/* Logo */}
      <div className="p-4 border-b border-border">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded bg-accent-primary flex items-center justify-center text-bg-primary font-bold text-sm">
            A
          </div>
          <span className="hidden md:block font-semibold text-sm">
            Aegis Quant
          </span>
        </div>
      </div>

      {/* Nav items */}
      <nav className="flex-1 py-4">
        {NAV_ITEMS.map((item) => {
          const isActive =
            item.href === "/"
              ? pathname === "/"
              : pathname.startsWith(item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`flex items-center gap-3 px-4 py-3 text-sm transition-colors ${
                isActive
                  ? "bg-bg-tertiary text-accent-primary border-r-2 border-accent-primary"
                  : "text-[var(--fg-muted)] hover:text-[var(--fg)] hover:bg-bg-tertiary"
              }`}
            >
              <span className="text-base w-6 text-center">{item.icon}</span>
              <span className="hidden md:block">{item.label}</span>
            </Link>
          );
        })}
      </nav>

      {/* Footer */}
      <div className="p-4 border-t border-border">
        <div className="hidden md:block text-xs text-[var(--fg-muted)]">
          v0.1.0 · Phase 8
        </div>
      </div>
    </aside>
  );
}
