import { Card } from "@/components/ui/card";
import type { AuthUser } from "@/lib/auth-context";

function formatDate(isoDateTime: string): string {
  return new Date(isoDateTime).toLocaleDateString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

/** Read-only - there is no backend support yet for editing name/email or
 * changing password, so this section only ever displays account.data. */
export function ProfileSection({ user }: { user: AuthUser }) {
  return (
    <Card className="flex flex-col gap-4">
      <h2 className="text-lg font-semibold text-zinc-900 dark:text-zinc-50">Profile</h2>

      <dl className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div>
          <dt className="text-xs text-zinc-500 dark:text-zinc-400">Full name</dt>
          <dd className="mt-0.5 text-sm font-medium text-zinc-900 dark:text-zinc-50">
            {user.full_name}
          </dd>
        </div>
        <div>
          <dt className="text-xs text-zinc-500 dark:text-zinc-400">Email</dt>
          <dd className="mt-0.5 text-sm font-medium text-zinc-900 dark:text-zinc-50">
            {user.email}
          </dd>
        </div>
        <div>
          <dt className="text-xs text-zinc-500 dark:text-zinc-400">Email verification</dt>
          <dd className="mt-0.5">
            {user.email_verified_at ? (
              <span className="inline-flex rounded-full bg-emerald-100 px-2.5 py-0.5 text-xs font-medium text-emerald-700 dark:bg-emerald-950 dark:text-emerald-400">
                Verified
              </span>
            ) : (
              <span className="inline-flex rounded-full bg-zinc-100 px-2.5 py-0.5 text-xs font-medium text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400">
                Not verified
              </span>
            )}
          </dd>
        </div>
        <div>
          <dt className="text-xs text-zinc-500 dark:text-zinc-400">Member since</dt>
          <dd className="mt-0.5 text-sm font-medium text-zinc-900 dark:text-zinc-50">
            {formatDate(user.created_at)}
          </dd>
        </div>
      </dl>
    </Card>
  );
}
