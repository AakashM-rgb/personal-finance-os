"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";

import { AddExpenseSheet } from "@/components/expense-entry/add-expense-sheet";
import { MoreMenu } from "@/components/nav/more-menu";

interface NavLinkItem {
  href: string;
  label: string;
  icon: string;
  isActive: (pathname: string) => boolean;
}

const LEFT_ITEMS: NavLinkItem[] = [
  { href: "/dashboard", label: "Home", icon: "🏠", isActive: (p) => p === "/dashboard" },
  {
    href: "/transactions",
    label: "Transactions",
    icon: "📋",
    isActive: (p) => p.startsWith("/transactions"),
  },
];

const RIGHT_ITEMS: NavLinkItem[] = [
  {
    href: "/analytics",
    label: "Analytics",
    icon: "📊",
    isActive: (p) => p.startsWith("/analytics"),
  },
];

/** The primary mobile navigation (CLAUDE.md §18): Home, Transactions, Add,
 * Analytics, More. Hidden from `md:` up, where the sidebar in
 * app/(app)/layout.tsx takes over - this is never a shrunk-down version
 * of that sidebar, it's a distinct, touch-optimized layout. "Add" opens a
 * sheet rather than navigating, so it never disturbs browser back/forward
 * history, and stays reachable in a single tap from anywhere in the app. */
export function MobileBottomNav({ onExpenseCreated }: { onExpenseCreated?: () => void }) {
  const pathname = usePathname();
  const [isAddOpen, setIsAddOpen] = useState(false);
  const [isMoreOpen, setIsMoreOpen] = useState(false);

  return (
    <>
      <nav
        aria-label="Primary"
        className="fixed inset-x-0 bottom-0 z-40 border-t border-zinc-200 bg-white/95 backdrop-blur-sm md:hidden dark:border-zinc-800 dark:bg-zinc-950/95"
        style={{ paddingBottom: "env(safe-area-inset-bottom)" }}
      >
        <div className="flex items-stretch justify-around">
          {LEFT_ITEMS.map((item) => (
            <TabLink key={item.href} item={item} active={item.isActive(pathname)} />
          ))}

          <button
            type="button"
            onClick={() => setIsAddOpen(true)}
            aria-label="Add expense"
            className="flex flex-1 flex-col items-center justify-center gap-0.5 py-1 focus-visible:outline-none"
          >
            <span
              aria-hidden="true"
              className="flex h-12 w-12 -translate-y-3 items-center justify-center rounded-full bg-zinc-900 text-2xl font-light text-white shadow-lg ring-4 ring-white transition-transform active:scale-95 dark:bg-white dark:text-zinc-900 dark:ring-zinc-950"
            >
              +
            </span>
            <span className="-mt-2 text-[11px] font-medium text-zinc-600 dark:text-zinc-400">
              Add
            </span>
          </button>

          {RIGHT_ITEMS.map((item) => (
            <TabLink key={item.href} item={item} active={item.isActive(pathname)} />
          ))}

          <button
            type="button"
            onClick={() => setIsMoreOpen(true)}
            aria-label="More options"
            aria-haspopup="dialog"
            className="flex min-h-11 flex-1 flex-col items-center justify-center gap-0.5 py-2 text-[11px] font-medium text-zinc-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-zinc-900 dark:text-zinc-400 dark:focus-visible:ring-zinc-100"
          >
            <span aria-hidden="true" className="text-lg">
              ☰
            </span>
            More
          </button>
        </div>
      </nav>

      {isAddOpen && (
        <AddExpenseSheet
          onClose={() => setIsAddOpen(false)}
          onCreated={() => {
            setIsAddOpen(false);
            onExpenseCreated?.();
          }}
        />
      )}
      {isMoreOpen && <MoreMenu onClose={() => setIsMoreOpen(false)} />}
    </>
  );
}

function TabLink({ item, active }: { item: NavLinkItem; active: boolean }) {
  return (
    <Link
      href={item.href}
      aria-current={active ? "page" : undefined}
      className={`flex min-h-11 flex-1 flex-col items-center justify-center gap-0.5 py-2 text-[11px] font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-zinc-900 dark:focus-visible:ring-zinc-100 ${
        active ? "text-zinc-900 dark:text-zinc-50" : "text-zinc-500 dark:text-zinc-400"
      }`}
    >
      <span aria-hidden="true" className="text-lg">
        {item.icon}
      </span>
      {item.label}
    </Link>
  );
}
