"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { NotificationsSection } from "@/components/settings/notifications-section";
import { PreferencesSection } from "@/components/settings/preferences-section";
import { ProfileSection } from "@/components/settings/profile-section";
import { SecuritySection } from "@/components/settings/security-section";
import { ApiError } from "@/lib/api-client";
import { useAuth } from "@/lib/auth-context";
import { getSettings, type UserSettings } from "@/lib/settings";

export default function SettingsPage() {
  const { user, accessToken } = useAuth();
  const [settings, setSettings] = useState<UserSettings | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    if (!accessToken) return;
    let isMounted = true;

    void getSettings(accessToken)
      .then((data) => {
        if (!isMounted) return;
        setSettings(data);
        setError(null);
      })
      .catch((err) => {
        if (isMounted) {
          setError(err instanceof ApiError ? err.message : "Failed to load settings.");
        }
      });

    return () => {
      isMounted = false;
    };
  }, [accessToken, reloadToken]);

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold text-zinc-900 dark:text-zinc-50">Settings</h1>
        <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
          Manage how the app is set up for you.
        </p>
      </div>

      {error && (
        <div className="rounded-md border border-red-200 bg-red-50 p-4 text-sm text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-400">
          {error}{" "}
          <button
            type="button"
            onClick={() => setReloadToken((n) => n + 1)}
            className="font-medium underline"
          >
            Try again
          </button>
        </div>
      )}

      {user && <ProfileSection user={user} />}

      {settings === null && !error && (
        <div className="flex flex-col gap-3">
          <Skeleton className="h-40" />
          <Skeleton className="h-52" />
        </div>
      )}

      {settings !== null && accessToken && (
        <>
          <PreferencesSection accessToken={accessToken} settings={settings} />
          <NotificationsSection accessToken={accessToken} settings={settings} />
          <SecuritySection accessToken={accessToken} />
        </>
      )}

      <Link href="/settings/categories">
        <Card className="transition-colors hover:border-zinc-300 dark:hover:border-zinc-700">
          <p className="font-medium text-zinc-900 dark:text-zinc-50">Categories</p>
          <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
            Manage default and custom spending categories.
          </p>
        </Card>
      </Link>

      <Link href="/settings/connected-accounts">
        <Card className="transition-colors hover:border-zinc-300 dark:hover:border-zinc-700">
          <p className="font-medium text-zinc-900 dark:text-zinc-50">Connected Accounts</p>
          <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
            Automatically import transactions from linked financial accounts (read-only).
          </p>
        </Card>
      </Link>
    </div>
  );
}
