"use client";

import { Card } from "@/components/ui/card";
import { useAuth } from "@/lib/auth-context";

export default function DashboardPage() {
  const { user } = useAuth();

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold text-zinc-900 dark:text-zinc-50">
          Welcome, {user?.full_name.split(" ")[0]}
        </h1>
        <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
          Your accounts, transactions, and insights will show up here.
        </p>
      </div>

      <Card>
        <p className="text-sm text-zinc-600 dark:text-zinc-400">
          You haven&apos;t added any accounts or transactions yet. The dashboard, budgets,
          goals, and analytics land in the next phases of this project.
        </p>
      </Card>
    </div>
  );
}
