import { cn } from "@/lib/utils";

interface StatTileProps {
  label: string;
  value: string;
  tone?: "default" | "positive" | "negative";
  hint?: string;
}

const TONE_CLASSES: Record<Required<StatTileProps>["tone"], string> = {
  default: "text-zinc-900 dark:text-zinc-50",
  positive: "text-emerald-600 dark:text-emerald-400",
  negative: "text-red-600 dark:text-red-400",
};

export function StatTile({ label, value, tone = "default", hint }: StatTileProps) {
  return (
    <div className="rounded-lg border border-zinc-200 p-4 dark:border-zinc-800">
      <p className="text-xs text-zinc-500 dark:text-zinc-400">{label}</p>
      <p className={cn("mt-1 text-xl font-semibold", TONE_CLASSES[tone])}>{value}</p>
      {hint && <p className="mt-0.5 text-xs text-zinc-500 dark:text-zinc-400">{hint}</p>}
    </div>
  );
}

export function StatTileGrid({ children }: { children: React.ReactNode }) {
  return <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">{children}</div>;
}
