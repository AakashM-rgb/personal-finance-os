import { Card } from "@/components/ui/card";
import { getGoalStatus, type GoalStatus, type SavingsGoal } from "@/lib/goals";
import { formatMoney } from "@/lib/money";
import { cn } from "@/lib/utils";

const STATUS_BADGE: Record<GoalStatus, string> = {
  completed: "bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-400",
  on_track: "bg-blue-100 text-blue-700 dark:bg-blue-950 dark:text-blue-400",
  due_today: "bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-400",
  overdue: "bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-400",
};

const STATUS_LABEL: Record<GoalStatus, string> = {
  completed: "Completed",
  on_track: "On track",
  due_today: "Due today",
  overdue: "Overdue",
};

export function ReportGoalList({ goals }: { goals: SavingsGoal[] }) {
  return (
    <Card>
      <h2 className="text-sm font-medium text-zinc-900 dark:text-zinc-50">Savings goals</h2>
      <p className="text-xs text-zinc-500 dark:text-zinc-400">Progress toward each goal</p>

      {goals.length === 0 ? (
        <p className="mt-4 text-sm text-zinc-500 dark:text-zinc-400">
          You haven&apos;t set any savings goals yet.
        </p>
      ) : (
        <ul className="mt-4 flex flex-col gap-3">
          {goals.map((goal) => {
            const status = getGoalStatus(goal);
            return (
              <li key={goal.id}>
                <div className="flex items-center justify-between text-sm">
                  <span className="text-zinc-700 dark:text-zinc-300">{goal.name}</span>
                  <span
                    className={cn(
                      "rounded-full px-2 py-0.5 text-xs font-medium",
                      STATUS_BADGE[status]
                    )}
                  >
                    {STATUS_LABEL[status]}
                  </span>
                </div>
                <div className="mt-1 h-2.5 w-full overflow-hidden rounded-full bg-zinc-100 dark:bg-zinc-800">
                  <div
                    className="h-full rounded-full bg-blue-600"
                    style={{ width: `${Math.min(goal.progress_percent, 100)}%` }}
                  />
                </div>
                <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
                  {formatMoney(goal.current_amount_minor, goal.currency)} of{" "}
                  {formatMoney(goal.target_amount_minor, goal.currency)} &middot;{" "}
                  {goal.progress_percent.toFixed(1)}%
                </p>
              </li>
            );
          })}
        </ul>
      )}
    </Card>
  );
}
