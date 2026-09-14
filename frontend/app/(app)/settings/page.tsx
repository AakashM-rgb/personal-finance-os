import Link from "next/link";

import { Card } from "@/components/ui/card";

export default function SettingsPage() {
  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold text-zinc-900 dark:text-zinc-50">Settings</h1>
        <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
          Manage how the app is set up for you.
        </p>
      </div>

      <Link href="/settings/categories">
        <Card className="transition-colors hover:border-zinc-300 dark:hover:border-zinc-700">
          <p className="font-medium text-zinc-900 dark:text-zinc-50">Categories</p>
          <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
            Manage default and custom spending categories.
          </p>
        </Card>
      </Link>
    </div>
  );
}
