"use client";

import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Modal } from "@/components/ui/modal";
import { Select } from "@/components/ui/select";
import { type Account, listAccounts } from "@/lib/accounts";
import { ApiError } from "@/lib/api-client";
import { useAuth } from "@/lib/auth-context";
import { type Category, listCategories } from "@/lib/categories";
import { deleteDraft, getDraft, isOfflineStorageAvailable, saveDraft } from "@/lib/offline/db";
import { queueOfflineExpense } from "@/lib/offline/sync-queue";
import { parseMoneyToMinorUnits } from "@/lib/money";
import { createTransaction, listTransactions } from "@/lib/transactions";

const DRAFT_SAVE_DEBOUNCE_MS = 400;
const RECENT_LIMIT = 6;

interface AddExpenseSheetProps {
  onClose: () => void;
  /** Called once the expense is either confirmed saved online, or safely
   * queued offline - never called for a validation failure. */
  onCreated: () => void;
}

/** The fast expense-entry flow (CLAUDE.md §18: "recording an expense must
 * take a few seconds"). Amount-first, recent categories/accounts
 * surfaced as one-tap chips, everything else optional and collapsed.
 * Works identically whether the device is online or offline - see
 * handleSave for the shared, duplicate-safe path either way. */
export function AddExpenseSheet({ onClose, onCreated }: AddExpenseSheetProps) {
  const { user, accessToken } = useAuth();
  const amountInputRef = useRef<HTMLInputElement>(null);
  const idempotencyKeyRef = useRef<string>(crypto.randomUUID());

  const [accounts, setAccounts] = useState<Account[] | null>(null);
  const [categories, setCategories] = useState<Category[] | null>(null);
  const [recentCategoryIds, setRecentCategoryIds] = useState<string[]>([]);
  const [recentAccountIds, setRecentAccountIds] = useState<string[]>([]);

  const [amountInput, setAmountInput] = useState("");
  const [categoryId, setCategoryId] = useState<string>("");
  const [accountId, setAccountId] = useState<string>("");
  const [merchant, setMerchant] = useState("");
  const [note, setNote] = useState("");
  const [showDetails, setShowDetails] = useState(false);

  const [draftRestored, setDraftRestored] = useState(false);
  const [storageUnavailable, setStorageUnavailable] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [savedOffline, setSavedOffline] = useState(false);

  // Load accounts/categories + derive "recently used" from real transaction
  // history only - never a guessed/fabricated default.
  useEffect(() => {
    if (!accessToken) return;
    let isMounted = true;

    void Promise.all([
      listAccounts(accessToken),
      listCategories(accessToken),
      listTransactions(accessToken, {
        type: "expense",
        sort_by: "occurred_at",
        sort_dir: "desc",
        limit: 30,
      }),
    ]).then(([accountsData, categoriesData, recent]) => {
      if (!isMounted) return;
      setAccounts(accountsData);
      setCategories(categoriesData);

      const recentCats: string[] = [];
      const recentAccs: string[] = [];
      for (const transaction of recent.transactions) {
        if (transaction.category_id && !recentCats.includes(transaction.category_id)) {
          recentCats.push(transaction.category_id);
        }
        if (!recentAccs.includes(transaction.account_id)) {
          recentAccs.push(transaction.account_id);
        }
      }
      setRecentCategoryIds(recentCats.slice(0, RECENT_LIMIT));
      setRecentAccountIds(recentAccs.slice(0, RECENT_LIMIT));
      // Set the default account as soon as data is available - never wait
      // on the separate (also async) draft-lookup below just to make the
      // form usable; that effect only OVERRIDES this if a draft actually
      // named a different account.
      setAccountId((current) => current || recentAccs[0] || accountsData[0]?.id || "");
    });

    return () => {
      isMounted = false;
    };
  }, [accessToken]);

  // Restore any saved draft for this user, once accounts have loaded so a
  // default account choice doesn't clobber it.
  useEffect(() => {
    if (!user || accounts === null) return;
    let isMounted = true;
    void getDraft(user.id).then((draft) => {
      if (!isMounted || !draft) {
        if (isMounted) {
          setAccountId((current) => current || recentAccountIds[0] || accounts[0]?.id || "");
        }
        return;
      }
      setAmountInput(draft.amountInput);
      setCategoryId(draft.categoryId ?? "");
      setAccountId(draft.accountId ?? recentAccountIds[0] ?? accounts[0]?.id ?? "");
      setMerchant(draft.merchant);
      setNote(draft.note);
      if (draft.merchant || draft.note) setShowDetails(true);
      setDraftRestored(true);
    });
    return () => {
      isMounted = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- runs once accounts arrive, not on every recentAccountIds change
  }, [user, accounts]);

  // The amount input only exists once accounts/categories have loaded (see
  // the isLoading-gated render below) - focusing on the very first mount
  // would silently no-op against a ref that isn't attached to anything yet.
  useEffect(() => {
    if (accounts !== null && categories !== null) {
      amountInputRef.current?.focus();
    }
  }, [accounts, categories]);

  // Debounced draft autosave - a meaningful in-progress entry must never
  // be silently lost to a reload/close.
  useEffect(() => {
    if (!user) return;
    const hasContent = amountInput.trim() !== "" || categoryId || merchant.trim() || note.trim();
    if (!hasContent) return;

    const timeout = window.setTimeout(() => {
      void saveDraft({
        userId: user.id,
        amountInput,
        categoryId: categoryId || null,
        accountId: accountId || null,
        merchant,
        note,
        date: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
      }).catch(() => setStorageUnavailable(true));
    }, DRAFT_SAVE_DEBOUNCE_MS);

    return () => window.clearTimeout(timeout);
  }, [user, amountInput, categoryId, accountId, merchant, note]);

  useEffect(() => {
    void isOfflineStorageAvailable().then((available) => setStorageUnavailable(!available));
  }, []);

  async function handleDiscardDraft() {
    setAmountInput("");
    setCategoryId("");
    setMerchant("");
    setNote("");
    setDraftRestored(false);
    if (user) await deleteDraft(user.id).catch(() => undefined);
  }

  async function handleSave() {
    if (isSubmitting) return; // guards against accidental double-submission (double-tap, double-click)
    if (!user || !accessToken) {
      setError("You need to be signed in to save an expense.");
      return;
    }
    if (!accountId) {
      setError("Choose an account.");
      return;
    }
    const amountMinor = parseMoneyToMinorUnits(amountInput);
    if (amountMinor === null || amountMinor <= 0) {
      setError("Enter a valid amount greater than 0.");
      return;
    }

    setIsSubmitting(true);
    setError(null);

    const payload = {
      account_id: accountId,
      type: "expense" as const,
      amount_minor: amountMinor,
      category_id: categoryId || null,
      merchant: merchant.trim() || null,
      description: note.trim() || null,
    };
    const idempotencyKey = idempotencyKeyRef.current;

    const goOffline = async () => {
      try {
        await queueOfflineExpense(user.id, payload, idempotencyKey);
        await deleteDraft(user.id).catch(() => undefined);
        setSavedOffline(true);
        onCreated();
      } catch {
        // Durable local storage itself failed (private browsing, quota,
        // unsupported browser) - the draft above already tried to persist
        // this; make the limitation explicit rather than pretending it saved.
        setError(
          "Couldn't save this expense - you're offline and local storage isn't available on this device/browser. Please try again once you're back online."
        );
        setIsSubmitting(false);
      }
    };

    if (!navigator.onLine) {
      await goOffline();
      return;
    }

    try {
      await createTransaction(accessToken, payload, idempotencyKey);
      await deleteDraft(user.id).catch(() => undefined);
      onCreated();
    } catch (err) {
      if (err instanceof ApiError) {
        // A definitive answer from the server (validation/auth/etc.) - the
        // user is still online and in control; show it and let them fix
        // the form, never silently queue a request we know is invalid.
        setError(err.message);
        setIsSubmitting(false);
        return;
      }
      // fetch() itself threw - no response was ever received, so we don't
      // know whether the server processed it. Queue it under the SAME
      // idempotency key so a later retry can never create a duplicate.
      await goOffline();
    }
  }

  const isLoading = accounts === null || categories === null;

  return (
    <Modal title="Add expense" onClose={onClose}>
      {isLoading && <p className="text-sm text-zinc-500 dark:text-zinc-400">Loading…</p>}

      {!isLoading && (
        <form
          onSubmit={(event) => {
            event.preventDefault();
            void handleSave();
          }}
          className="flex flex-col gap-4"
        >
          {draftRestored && (
            <div className="flex items-center justify-between rounded-md bg-amber-50 px-3 py-2 text-xs text-amber-800 dark:bg-amber-950 dark:text-amber-300">
              <span>Continuing your unsaved draft.</span>
              <button
                type="button"
                onClick={() => void handleDiscardDraft()}
                className="font-medium underline"
              >
                Discard
              </button>
            </div>
          )}

          <div>
            <label
              htmlFor="add-expense-amount"
              className="text-sm font-medium text-zinc-700 dark:text-zinc-300"
            >
              Amount
            </label>
            <input
              id="add-expense-amount"
              ref={amountInputRef}
              value={amountInput}
              onChange={(e) => setAmountInput(e.target.value)}
              inputMode="decimal"
              autoComplete="off"
              placeholder="0.00"
              className="mt-1 h-16 w-full rounded-lg border border-zinc-300 bg-white px-4 text-3xl font-semibold tabular-nums text-zinc-900 placeholder:text-zinc-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-zinc-900 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-50 dark:placeholder:text-zinc-700"
            />
          </div>

          {categories && categories.length > 0 && (
            <div>
              <span className="text-sm font-medium text-zinc-700 dark:text-zinc-300">
                Category
              </span>
              <div className="mt-1.5 flex flex-wrap gap-2">
                {(recentCategoryIds.length > 0
                  ? recentCategoryIds
                  : categories.slice(0, RECENT_LIMIT).map((c) => c.id)
                ).map((id) => {
                  const category = categories.find((c) => c.id === id);
                  if (!category) return null;
                  const selected = categoryId === id;
                  return (
                    <button
                      key={id}
                      type="button"
                      onClick={() => setCategoryId(selected ? "" : id)}
                      aria-pressed={selected}
                      className={`flex min-h-11 items-center gap-1.5 rounded-full border px-3 py-2 text-sm font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-zinc-900 dark:focus-visible:ring-zinc-100 ${
                        selected
                          ? "border-zinc-900 bg-zinc-900 text-white dark:border-white dark:bg-white dark:text-zinc-900"
                          : "border-zinc-300 text-zinc-700 hover:bg-zinc-50 dark:border-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-900"
                      }`}
                    >
                      <span aria-hidden="true">{category.icon}</span>
                      {category.name}
                    </button>
                  );
                })}
              </div>
              <Select
                value={categoryId}
                onChange={(e) => setCategoryId(e.target.value)}
                className="mt-2"
                aria-label="All categories"
              >
                <option value="">No category</option>
                {categories.map((category) => (
                  <option key={category.id} value={category.id}>
                    {category.icon} {category.name}
                  </option>
                ))}
              </Select>
            </div>
          )}

          {accounts && accounts.length > 0 && (
            <div>
              <label
                htmlFor="add-expense-account"
                className="text-sm font-medium text-zinc-700 dark:text-zinc-300"
              >
                Account
              </label>
              <Select
                id="add-expense-account"
                value={accountId}
                onChange={(e) => setAccountId(e.target.value)}
                className="mt-1.5"
              >
                {[...recentAccountIds, ...accounts.map((a) => a.id)]
                  .filter((id, index, all) => all.indexOf(id) === index)
                  .map((id) => accounts.find((a) => a.id === id))
                  .filter((a): a is Account => a != null)
                  .map((account) => (
                    <option key={account.id} value={account.id}>
                      {account.name}
                    </option>
                  ))}
              </Select>
            </div>
          )}

          {!showDetails && (
            <button
              type="button"
              onClick={() => setShowDetails(true)}
              className="self-start text-sm font-medium text-zinc-600 underline underline-offset-2 dark:text-zinc-400"
            >
              Add merchant / note
            </button>
          )}

          {showDetails && (
            <div className="flex flex-col gap-3">
              <div>
                <label
                  htmlFor="add-expense-merchant"
                  className="text-sm font-medium text-zinc-700 dark:text-zinc-300"
                >
                  Merchant
                </label>
                <Input
                  id="add-expense-merchant"
                  value={merchant}
                  onChange={(e) => setMerchant(e.target.value)}
                  className="mt-1.5"
                  placeholder="Optional"
                />
              </div>
              <div>
                <label
                  htmlFor="add-expense-note"
                  className="text-sm font-medium text-zinc-700 dark:text-zinc-300"
                >
                  Note
                </label>
                <Input
                  id="add-expense-note"
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                  className="mt-1.5"
                  placeholder="Optional"
                />
              </div>
            </div>
          )}

          {storageUnavailable && (
            <p className="text-xs text-amber-700 dark:text-amber-400">
              This device/browser doesn&apos;t support local drafts or offline saving - stay
              online while adding this expense.
            </p>
          )}

          {error && (
            <p role="alert" className="text-sm text-red-600 dark:text-red-400">
              {error}
            </p>
          )}

          {savedOffline && (
            <p role="status" className="text-sm text-amber-700 dark:text-amber-400">
              Saved offline - it will sync automatically once you&apos;re back online.
            </p>
          )}

          <div className="mt-1 flex justify-end gap-2">
            <Button type="button" variant="secondary" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" isLoading={isSubmitting} disabled={!amountInput.trim()}>
              Save
            </Button>
          </div>
        </form>
      )}
    </Modal>
  );
}
