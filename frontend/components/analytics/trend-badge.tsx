import { resolveTrendTone, type TrendInfo } from "@/lib/analytics";
import { cn } from "@/lib/utils";

const TONE_STYLES: Record<string, string> = {
  positive: "bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-400",
  negative: "bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-400",
  neutral: "bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400",
  unknown: "bg-zinc-100 text-zinc-500 dark:bg-zinc-800 dark:text-zinc-400",
};

const DIRECTION_LABEL: Record<string, string> = {
  increasing: "Increasing",
  decreasing: "Decreasing",
  flat: "Flat",
};

interface TrendBadgeProps {
  trend: TrendInfo;
  /** Whether an "increasing" direction is good news for this chart. */
  increasingIsGood: boolean;
}

export function TrendBadge({ trend, increasingIsGood }: TrendBadgeProps) {
  const tone = resolveTrendTone(trend.direction, increasingIsGood);

  if (trend.direction === null) {
    return (
      <span className={cn("rounded-full px-2.5 py-0.5 text-xs font-medium", TONE_STYLES.unknown)}>
        Not enough data yet
      </span>
    );
  }

  const percentText =
    trend.percent_change !== null
      ? ` (${trend.percent_change > 0 ? "+" : ""}${trend.percent_change}%)`
      : "";

  return (
    <span className={cn("rounded-full px-2.5 py-0.5 text-xs font-medium", TONE_STYLES[tone])}>
      {DIRECTION_LABEL[trend.direction]}
      {percentText}
    </span>
  );
}
