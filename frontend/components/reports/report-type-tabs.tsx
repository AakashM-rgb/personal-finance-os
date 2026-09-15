import { REPORT_LABELS, REPORT_TYPES, type ReportType } from "@/lib/reports";
import { cn } from "@/lib/utils";

interface ReportTypeTabsProps {
  value: ReportType;
  onChange: (type: ReportType) => void;
}

export function ReportTypeTabs({ value, onChange }: ReportTypeTabsProps) {
  return (
    <div className="flex flex-wrap gap-2" role="tablist" aria-label="Report type">
      {REPORT_TYPES.map((type) => (
        <button
          key={type}
          type="button"
          role="tab"
          aria-selected={value === type}
          onClick={() => onChange(type)}
          className={cn(
            "rounded-full px-3 py-1.5 text-sm font-medium transition-colors",
            value === type
              ? "bg-zinc-900 text-white dark:bg-white dark:text-zinc-900"
              : "bg-zinc-100 text-zinc-700 hover:bg-zinc-200 dark:bg-zinc-800 dark:text-zinc-300 dark:hover:bg-zinc-700"
          )}
        >
          {REPORT_LABELS[type]}
        </button>
      ))}
    </div>
  );
}
