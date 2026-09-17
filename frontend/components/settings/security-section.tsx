"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { FormError } from "@/components/ui/form-error";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError } from "@/lib/api-client";
import { useAuth } from "@/lib/auth-context";
import { listSessions, type Session } from "@/lib/sessions";

function formatDateTime(isoDateTime: string): string {
  return new Date(isoDateTime).toLocaleDateString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function SessionRow({ session }: { session: Session }) {
  return (
    <li className="flex flex-col gap-1 border-b border-zinc-100 py-3 last:border-0 dark:border-zinc-800">
      <span className="text-sm font-medium text-zinc-900 dark:text-zinc-50">
        {session.user_agent ?? "Unknown device"}
      </span>
      <span className="text-xs text-zinc-500 dark:text-zinc-400">
        {session.ip_address ? `${session.ip_address} · ` : ""}
        Signed in {formatDateTime(session.created_at)} · Expires {formatDateTime(session.expires_at)}
      </span>
    </li>
  );
}

export function SecuritySection({ accessToken }: { accessToken: string }) {
  const router = useRouter();
  const { logoutAll } = useAuth();

  const [sessions, setSessions] = useState<Session[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [reloadToken, setReloadToken] = useState(0);

  const [isConfirmingLogoutAll, setIsConfirmingLogoutAll] = useState(false);
  const [isLoggingOutAll, setIsLoggingOutAll] = useState(false);
  const [logoutAllError, setLogoutAllError] = useState<string | null>(null);

  useEffect(() => {
    let isMounted = true;
    void listSessions(accessToken)
      .then((data) => {
        if (!isMounted) return;
        setSessions(data);
        setLoadError(null);
      })
      .catch((err) => {
        if (isMounted) {
          setLoadError(err instanceof ApiError ? err.message : "Failed to load sessions.");
        }
      });
    return () => {
      isMounted = false;
    };
  }, [accessToken, reloadToken]);

  async function handleConfirmLogoutAll() {
    setIsLoggingOutAll(true);
    setLogoutAllError(null);
    try {
      await logoutAll();
      router.replace("/login");
    } catch (err) {
      setLogoutAllError(
        err instanceof ApiError ? err.message : "Failed to log out of all devices."
      );
      setIsLoggingOutAll(false);
      setIsConfirmingLogoutAll(false);
    }
  }

  return (
    <Card className="flex flex-col gap-4">
      <div>
        <h2 className="text-lg font-semibold text-zinc-900 dark:text-zinc-50">Security</h2>
        <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
          Devices currently signed in to your account.
        </p>
      </div>

      {loadError && (
        <div className="rounded-md border border-red-200 bg-red-50 p-4 text-sm text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-400">
          {loadError}{" "}
          <button
            type="button"
            onClick={() => setReloadToken((n) => n + 1)}
            className="font-medium underline"
          >
            Try again
          </button>
        </div>
      )}

      {sessions === null && !loadError && (
        <div className="flex flex-col gap-2">
          <Skeleton className="h-10" />
          <Skeleton className="h-10" />
        </div>
      )}

      {sessions !== null && (
        <ul className="flex flex-col">
          {sessions.length === 0 ? (
            <p className="py-2 text-sm text-zinc-600 dark:text-zinc-400">No active sessions.</p>
          ) : (
            sessions.map((session) => <SessionRow key={session.id} session={session} />)
          )}
        </ul>
      )}

      <div className="border-t border-zinc-100 pt-4 dark:border-zinc-800">
        <h3 className="text-sm font-medium text-zinc-900 dark:text-zinc-50">Log out everywhere</h3>
        <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
          This signs out every device above, including the one you&apos;re using right now - you
          will need to log in again immediately.
        </p>

        <FormError message={logoutAllError} />

        <div className="mt-3">
          {isConfirmingLogoutAll ? (
            <div className="flex gap-2">
              <Button
                variant="secondary"
                onClick={() => setIsConfirmingLogoutAll(false)}
                disabled={isLoggingOutAll}
              >
                Cancel
              </Button>
              <Button
                variant="primary"
                className="bg-red-600 hover:bg-red-700 dark:bg-red-600 dark:hover:bg-red-700"
                isLoading={isLoggingOutAll}
                onClick={() => void handleConfirmLogoutAll()}
              >
                Yes, log out of all devices
              </Button>
            </div>
          ) : (
            <Button variant="secondary" onClick={() => setIsConfirmingLogoutAll(true)}>
              Log out of all devices
            </Button>
          )}
        </div>
      </div>
    </Card>
  );
}
