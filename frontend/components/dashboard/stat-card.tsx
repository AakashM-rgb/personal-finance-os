import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";

interface StatCardProps {
  label: string;
  value: string;
  sublabel?: string;
  delta?: { text: string; isGood: boolean } | null;
}

export function StatCard({ label, value, sublabel, delta }: StatCardProps) {
  return (
    <Card className="flex flex-col gap-1">
      <span className="text-sm text-zinc-500 dark:text-zinc-400">{label}</span>
      <span className="text-2xl font-semibold text-zinc-900 [font-variant-numeric:proportional-nums] break-words dark:text-zinc-50">
        {value}
      </span>
      {sublabel && <span className="text-xs text-zinc-500 dark:text-zinc-400">{sublabel}</span>}
      {delta && (
        <span
          className={cn(
            "text-xs font-medium",
            delta.isGood
              ? "text-emerald-600 dark:text-emerald-400"
              : "text-red-600 dark:text-red-400"
          )}
        >
          {delta.text}
        </span>
      )}
    </Card>
  );
}
