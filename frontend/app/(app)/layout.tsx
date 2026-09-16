"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { MobileBottomNav } from "@/components/nav/mobile-bottom-nav";
import { SyncStatusIndicator } from "@/components/nav/sync-status-indicator";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/lib/auth-context";
import { useOfflineSync } from "@/lib/offline/use-offline-sync";

const NAV_ITEMS = [
  { href: "/dashboard", label: "Dashboard" },
  { href: "/ai", label: "AI Assistant" },
  { href: "/analytics", label: "Analytics" },
  { href: "/calendar", label: "Calendar" },
  { href: "/reports", label: "Reports" },
  { href: "/transactions", label: "Transactions" },
  { href: "/receipts", label: "Receipts" },
  { href: "/recurring-transactions", label: "Recurring" },
  { href: "/subscriptions", label: "Subscriptions" },
  { href: "/budgets", label: "Budgets" },
  { href: "/goals", label: "Goals" },
  { href: "/accounts", label: "Accounts" },
  { href: "/settings", label: "Settings" },
];

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const { user, isLoading, logout, accessToken } = useAuth();
  const router = useRouter();
  const offlineSync = useOfflineSync(user?.id ?? null, accessToken);

  useEffect(() => {
    if (!isLoading && !user) {
      router.replace("/login");
    }
  }, [isLoading, user, router]);

  if (isLoading) {
    return (
      <div className="flex flex-1 items-center justify-center">
        <p className="text-sm text-zinc-500 dark:text-zinc-400">Loading your account…</p>
      </div>
    );
  }

  if (!user) {
    // Redirect is in flight (see effect above); render nothing meanwhile.
    return null;
  }

  return (
    <div className="flex flex-1 flex-col md:flex-row">
      {/* Tablet-landscape and up: persistent sidebar. Below that, the
          MobileBottomNav (rendered further down) is the primary nav - this
          is a distinct layout for touch/one-handed use, never a shrunk
          copy of this sidebar (CLAUDE.md §18). */}
      <aside className="hidden border-r border-zinc-200 p-6 md:flex md:w-56 md:flex-col md:items-stretch dark:border-zinc-800">
        <span className="text-lg font-semibold text-zinc-900 dark:text-zinc-50">Finance App</span>
        <nav className="mt-8 flex flex-1 flex-col gap-2">
          {NAV_ITEMS.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className="rounded-md px-3 py-2 text-sm font-medium text-zinc-700 hover:bg-zinc-100 dark:text-zinc-300 dark:hover:bg-zinc-800"
            >
              {item.label}
            </Link>
          ))}
        </nav>
      </aside>

      <div className="flex flex-1 flex-col">
        <header className="flex items-center justify-between gap-3 border-b border-zinc-200 px-4 py-3 sm:justify-end md:px-8 dark:border-zinc-800">
          <span className="text-lg font-semibold text-zinc-900 md:hidden dark:text-zinc-50">
            Finance App
          </span>
          <div className="flex items-center gap-3">
            <SyncStatusIndicator state={offlineSync} />
            <span className="hidden text-sm text-zinc-600 sm:inline dark:text-zinc-400">
              {user.full_name}
            </span>
            <Button
              variant="secondary"
              onClick={() => void logout().then(() => router.replace("/login"))}
            >
              Log out
            </Button>
          </div>
        </header>
        <main className="flex-1 p-4 pb-24 sm:p-8 md:pb-8">{children}</main>
      </div>

      <MobileBottomNav onExpenseCreated={offlineSync.refresh} />
    </div>
  );
}
