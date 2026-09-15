import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ReportTypeTabs } from "@/components/reports/report-type-tabs";
import { REPORT_LABELS, REPORT_TYPES } from "@/lib/reports";

describe("ReportTypeTabs", () => {
  it("renders a tab for every report type", () => {
    render(<ReportTypeTabs value="monthly" onChange={vi.fn()} />);
    for (const type of REPORT_TYPES) {
      expect(screen.getByRole("tab", { name: REPORT_LABELS[type] })).toBeInTheDocument();
    }
  });

  it("marks the current report type as selected", () => {
    render(<ReportTypeTabs value="yearly" onChange={vi.fn()} />);
    expect(screen.getByRole("tab", { name: "Yearly Report" })).toHaveAttribute(
      "aria-selected",
      "true"
    );
    expect(screen.getByRole("tab", { name: "Monthly Report" })).toHaveAttribute(
      "aria-selected",
      "false"
    );
  });

  it("calls onChange with the clicked report type", () => {
    const onChange = vi.fn();
    render(<ReportTypeTabs value="monthly" onChange={onChange} />);
    fireEvent.click(screen.getByRole("tab", { name: "Net Worth Report" }));
    expect(onChange).toHaveBeenCalledWith("net-worth");
  });
});
