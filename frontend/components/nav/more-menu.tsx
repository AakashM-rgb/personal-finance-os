"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";

import { Modal } from "@/components/ui/modal";
import { useAuth } from "@/lib/auth-context";

const MORE_LINKS = [
  { href: "/ai", label: "AI Assistant", icon: "✨" },
  { href: "/calendar", label: "Calendar", icon: "📅" },
  { href: "/reports", label: "Reports", icon: "🧾" },
  { href: "/receipts", label: "Receipts", icon: "🧾" },
  { href: "/recurring-transactions", label: "Recurring", icon: "🔁" },
  { href: "/subscriptions", label: "Subscriptions", icon: "📺" },
  { href: "/budgets", label: "Budgets", icon: "🎯" },
  { href: "/goals", label: "Goals", icon: "🏁" },
  { href: "/accounts", label: "Accounts", icon: "🏦" },
  { href: "/settings", label: "Settings", icon: "⚙️" },
];

/** The mobile "More" tab (CLAUDE.md §18) - reuses every existing route
 * rather than introducing new ones; this is purely a navigation surface
 * for the sections that don't fit in the 5-item bottom bar. */
export function MoreMenu({ onClose }: { onClose: () => void }) {
  const { user, logout } = useAuth();
  const router = useRouter();

  return (
    <Modal title="More" onClose={onClose}>
      <nav aria-label="More sections">
        <ul className="grid grid-cols-2 gap-2">
          {MORE_LINKS.map((link) => (
            <li key={link.href}>
              <Link
                href={link.href}
                onClick={onClose}
                className="flex min-h-11 items-center gap-2 rounded-md px-3 py-2.5 text-sm font-medium text-zinc-700 hover:bg-zinc-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-zinc-900 dark:text-zinc-300 dark:hover:bg-zinc-900 dark:focus-visible:ring-zinc-100"
              >
                <span aria-hidden="true">{link.icon}</span>
                {link.label}
              </Link>
            </li>
          ))}
        </ul>
      </nav>

      <div className="mt-4 flex items-center justify-between border-t border-zinc-100 pt-4 dark:border-zinc-800">
        <span className="text-sm text-zinc-600 dark:text-zinc-400">{user?.full_name}</span>
        <button
          type="button"
          onClick={() => {
            onClose();
            void logout().then(() => router.replace("/login"));
          }}
          className="min-h-11 rounded-md px-3 text-sm font-medium text-red-600 hover:bg-red-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-600 dark:text-red-400 dark:hover:bg-red-950"
        >
          Log out
        </button>
      </div>
    </Modal>
  );
}
