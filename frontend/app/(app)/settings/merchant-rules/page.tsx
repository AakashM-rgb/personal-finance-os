"use client";

import { useEffect, useState } from "react";

import { MerchantRuleRow } from "@/components/merchant-rules/merchant-rule-row";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError } from "@/lib/api-client";
import { useAuth } from "@/lib/auth-context";
import { deleteMerchantRule, listMerchantRules, type MerchantRule } from "@/lib/merchant-rules";

export default function MerchantRulesPage() {
  const { accessToken } = useAuth();
  const [rules, setRules] = useState<MerchantRule[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reloadToken, setReloadToken] = useState(0);
  const reload = () => setReloadToken((n) => n + 1);

  useEffect(() => {
    if (!accessToken) return;
    let isMounted = true;

    void listMerchantRules(accessToken)
      .then((data) => {
        if (!isMounted) return;
        setRules(data);
        setError(null);
      })
      .catch((err) => {
        if (isMounted) {
          setError(err instanceof ApiError ? err.message : "Failed to load merchant rules.");
        }
      });

    return () => {
      isMounted = false;
    };
  }, [accessToken, reloadToken]);

  async function handleDelete(ruleId: string) {
    if (!accessToken) return;
    await deleteMerchantRule(accessToken, ruleId);
    reload();
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold text-zinc-900 dark:text-zinc-50">Merchant Rules</h1>
        <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
          Categories you&apos;ve taught the app to remember for specific merchants - applied
          automatically to future synced transactions. Created from the &quot;Remember this
          category&quot; option when editing a transaction.
        </p>
      </div>

      {error && (
        <div className="rounded-md border border-red-200 bg-red-50 p-4 text-sm text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-400">
          {error}{" "}
          <button type="button" onClick={reload} className="font-medium underline">
            Try again
          </button>
        </div>
      )}

      {rules === null && !error && (
        <div className="flex flex-col gap-2">
          {[1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-12" />
          ))}
        </div>
      )}

      {rules !== null && (
        <Card>
          {rules.length === 0 ? (
            <p className="py-6 text-center text-sm text-zinc-600 dark:text-zinc-400">
              No merchant rules yet.
            </p>
          ) : (
            rules.map((rule) => (
              <MerchantRuleRow key={rule.id} rule={rule} onDelete={() => handleDelete(rule.id)} />
            ))
          )}
        </Card>
      )}
    </div>
  );
}
