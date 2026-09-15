"use client";

import { useEffect, useState } from "react";

import { GoalCard } from "@/components/goals/goal-card";
import { GoalForm } from "@/components/goals/goal-form";
import { Button } from "@/components/ui/button";
import { Modal } from "@/components/ui/modal";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError } from "@/lib/api-client";
import { useAuth } from "@/lib/auth-context";
import {
  createGoal,
  deleteGoal,
  listGoals,
  updateGoal,
  type SavingsGoal,
  type SavingsGoalCreateInput,
  type SavingsGoalUpdateInput,
} from "@/lib/goals";

type ModalState = { mode: "create" } | { mode: "edit"; goal: SavingsGoal } | null;

export default function GoalsPage() {
  const { accessToken } = useAuth();

  const [goals, setGoals] = useState<SavingsGoal[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [modalState, setModalState] = useState<ModalState>(null);
  const [reloadToken, setReloadToken] = useState(0);

  const reload = () => setReloadToken((n) => n + 1);

  useEffect(() => {
    if (!accessToken) return;
    let isMounted = true;

    void listGoals(accessToken)
      .then((goalsData) => {
        if (!isMounted) return;
        setGoals(goalsData);
        setError(null);
      })
      .catch((err) => {
        if (isMounted) setError(err instanceof ApiError ? err.message : "Failed to load goals.");
      });

    return () => {
      isMounted = false;
    };
  }, [accessToken, reloadToken]);

  async function handleCreate(input: SavingsGoalCreateInput | SavingsGoalUpdateInput) {
    if (!accessToken) return;
    await createGoal(accessToken, input as SavingsGoalCreateInput);
    setModalState(null);
    reload();
  }

  async function handleUpdate(
    goalId: string,
    input: SavingsGoalCreateInput | SavingsGoalUpdateInput
  ) {
    if (!accessToken) return;
    await updateGoal(accessToken, goalId, input as SavingsGoalUpdateInput);
    setModalState(null);
    reload();
  }

  async function handleDelete(goalId: string) {
    if (!accessToken) return;
    await deleteGoal(accessToken, goalId);
    reload();
  }

  const isLoading = goals === null && !error;

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-zinc-900 dark:text-zinc-50">
            Savings Goals
          </h1>
          <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
            Set a target and track your progress toward it.
          </p>
        </div>
        {!isLoading && (
          <Button onClick={() => setModalState({ mode: "create" })}>+ Add goal</Button>
        )}
      </div>

      {error && (
        <div className="rounded-md border border-red-200 bg-red-50 p-4 text-sm text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-400">
          {error}{" "}
          <button type="button" onClick={reload} className="font-medium underline">
            Try again
          </button>
        </div>
      )}

      {isLoading && !error && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {[1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-48" />
          ))}
        </div>
      )}

      {!isLoading && goals !== null && goals.length === 0 && (
        <div className="rounded-xl border border-dashed border-zinc-300 p-10 text-center dark:border-zinc-700">
          <p className="text-sm text-zinc-600 dark:text-zinc-400">
            You haven&apos;t set any savings goals yet.
          </p>
          <Button className="mt-4" onClick={() => setModalState({ mode: "create" })}>
            + Add your first goal
          </Button>
        </div>
      )}

      {!isLoading && goals !== null && goals.length > 0 && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {goals.map((goal) => (
            <GoalCard
              key={goal.id}
              goal={goal}
              onEdit={() => setModalState({ mode: "edit", goal })}
              onDelete={() => handleDelete(goal.id)}
            />
          ))}
        </div>
      )}

      {modalState?.mode === "create" && (
        <Modal title="Add savings goal" onClose={() => setModalState(null)}>
          <GoalForm onSubmit={handleCreate} onCancel={() => setModalState(null)} />
        </Modal>
      )}

      {modalState?.mode === "edit" && (
        <Modal title="Edit savings goal" onClose={() => setModalState(null)}>
          <GoalForm
            goal={modalState.goal}
            onSubmit={(input) => handleUpdate(modalState.goal.id, input)}
            onCancel={() => setModalState(null)}
          />
        </Modal>
      )}
    </div>
  );
}
