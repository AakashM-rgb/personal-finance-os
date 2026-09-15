"use client";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { ANALYTICS_RANGES, ANALYTICS_RANGE_LABELS, type AnalyticsRange } from "@/lib/analytics";

interface DateRangeSelectorProps {
  range: AnalyticsRange;
  customFrom: string;
  customTo: string;
  onRangeChange: (range: AnalyticsRange) => void;
  onCustomFromChange: (value: string) => void;
  onCustomToChange: (value: string) => void;
}

export function DateRangeSelector({
  range,
  customFrom,
  customTo,
  onRangeChange,
  onCustomFromChange,
  onCustomToChange,
}: DateRangeSelectorProps) {
  return (
    <div className="flex flex-wrap items-end gap-3">
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="analytics-range">Date range</Label>
        <Select
          id="analytics-range"
          value={range}
          onChange={(e) => onRangeChange(e.target.value as AnalyticsRange)}
          className="w-48"
        >
          {ANALYTICS_RANGES.map((r) => (
            <option key={r} value={r}>
              {ANALYTICS_RANGE_LABELS[r]}
            </option>
          ))}
        </Select>
      </div>

      {range === "custom" && (
        <>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="analytics-custom-from">From</Label>
            <Input
              id="analytics-custom-from"
              type="date"
              value={customFrom}
              onChange={(e) => onCustomFromChange(e.target.value)}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="analytics-custom-to">To</Label>
            <Input
              id="analytics-custom-to"
              type="date"
              value={customTo}
              onChange={(e) => onCustomToChange(e.target.value)}
            />
          </div>
        </>
      )}
    </div>
  );
}
