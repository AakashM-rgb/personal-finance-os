import { Card } from "@/components/ui/card";
import type { HealthScore } from "@/lib/dashboard";
import { cn } from "@/lib/utils";

function bandClasses(score: number): { fill: string; track: string } {
  if (score >= 80) return { fill: "bg-emerald-600", track: "bg-emerald-100 dark:bg-emerald-950" };
  if (score >= 60) return { fill: "bg-blue-600", track: "bg-blue-100 dark:bg-blue-950" };
  if (score >= 40) return { fill: "bg-amber-500", track: "bg-amber-100 dark:bg-amber-950" };
  return { fill: "bg-red-600", track: "bg-red-100 dark:bg-red-950" };
}

export function HealthScoreMeter({ healthScore }: { healthScore: HealthScore }) {
  if (healthScore.score === null) {
    return (
      <Card>
        <h2 className="text-sm font-medium text-zinc-700 dark:text-zinc-300">
          Financial Health Score
        </h2>
        <p className="mt-3 text-sm text-zinc-500 dark:text-zinc-400">
          Add some income and expenses this month to see your score.
        </p>
      </Card>
    );
  }

  const { fill, track } = bandClasses(healthScore.score);

  return (
    <Card>
      <div className="flex items-baseline justify-between">
        <h2 className="text-sm font-medium text-zinc-700 dark:text-zinc-300">
          Financial Health Score
        </h2>
        <span className="text-xs font-medium text-zinc-500 dark:text-zinc-400">
          {healthScore.label}
        </span>
      </div>

      <div className="mt-3 flex items-center gap-3">
        <span className="text-3xl font-semibold text-zinc-900 [font-variant-numeric:proportional-nums] dark:text-zinc-50">
          {healthScore.score}
        </span>
        <div className={cn("h-6 flex-1 overflow-hidden rounded-full", track)} role="meter" aria-valuenow={healthScore.score} aria-valuemin={0} aria-valuemax={100}>
          <div
            className={cn("h-full rounded-full", fill)}
            style={{ width: `${healthScore.score}%` }}
          />
        </div>
      </div>

      <ul className="mt-4 flex flex-col gap-2">
        {healthScore.factors
          .filter((f) => f.score !== null)
          .map((factor) => (
            <li key={factor.key} className="flex items-start gap-2 text-sm">
              <span
                className={cn(
                  "mt-0.5 font-semibold",
                  factor.is_positive
                    ? "text-emerald-600 dark:text-emerald-400"
                    : "text-amber-600 dark:text-amber-400"
                )}
                aria-hidden="true"
              >
                {factor.is_positive ? "+" : "−"}
              </span>
              <span className="text-zinc-700 dark:text-zinc-300">{factor.detail}</span>
            </li>
          ))}
      </ul>
    </Card>
  );
}
