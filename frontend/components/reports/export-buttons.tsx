"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import type { ExportFormat } from "@/lib/reports";

interface ExportButtonsProps {
  onExport: (format: ExportFormat) => Promise<void>;
}

const FORMATS: { format: ExportFormat; label: string }[] = [
  { format: "csv", label: "CSV" },
  { format: "xlsx", label: "Excel" },
  { format: "pdf", label: "PDF" },
];

export function ExportButtons({ onExport }: ExportButtonsProps) {
  const [pending, setPending] = useState<ExportFormat | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleClick(format: ExportFormat) {
    setPending(format);
    setError(null);
    try {
      await onExport(format);
    } catch {
      setError("Failed to generate the export. Please try again.");
    } finally {
      setPending(null);
    }
  }

  return (
    <div className="flex items-center gap-2">
      {FORMATS.map(({ format, label }) => (
        <Button
          key={format}
          variant="secondary"
          isLoading={pending === format}
          disabled={pending !== null && pending !== format}
          onClick={() => void handleClick(format)}
        >
          Export {label}
        </Button>
      ))}
      {error && <span className="text-xs text-red-600 dark:text-red-400">{error}</span>}
    </div>
  );
}
