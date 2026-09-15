"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { Button } from "@/components/ui/button";
import { useAuth } from "@/lib/auth-context";

const NAV_ITEMS = [
  { href: "/dashboard", label: "Dashboard" },
  { href: "/transactions", label: "Transactions" },
  { href: "/budgets", label: "Budgets" },
  { href: "/goals", label: "Goals" },
  { href: "/accounts", label: "Accounts" },
  { href: "/settings", label: "Settings" },
];

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const { user, isLoading, logout } = useAuth();
  const router = useRouter();

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
    <div className="flex flex-1 flex-col sm:flex-row">
      <aside className="flex flex-row items-center justify-between gap-4 border-b border-zinc-200 p-4 sm:w-56 sm:flex-col sm:items-stretch sm:justify-start sm:border-b-0 sm:border-r sm:p-6 dark:border-zinc-800">
        <span className="text-lg font-semibold text-zinc-900 dark:text-zinc-50">Finance App</span>
        <nav className="flex flex-1 gap-2 sm:mt-8 sm:flex-col">
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
        <header className="flex items-center justify-end gap-3 border-b border-zinc-200 px-4 py-3 sm:px-8 dark:border-zinc-800">
          <span className="text-sm text-zinc-600 dark:text-zinc-400">{user.full_name}</span>
          <Button variant="secondary" onClick={() => void logout().then(() => router.replace("/login"))}>
            Log out
          </Button>
        </header>
        <main className="flex-1 p-4 sm:p-8">{children}</main>
      </div>
    </div>
  );
}
