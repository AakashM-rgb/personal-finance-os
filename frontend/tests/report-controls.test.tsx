import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ReportControls } from "@/components/reports/report-controls";

const baseProps = {
  year: 2026,
  month: 9,
  onYearChange: vi.fn(),
  onMonthChange: vi.fn(),
  range: "current_month" as const,
  customFrom: "2026-09-01",
  customTo: "2026-09-15",
  onRangeChange: vi.fn(),
  onCustomFromChange: vi.fn(),
  onCustomToChange: vi.fn(),
};

describe("ReportControls", () => {
  it("shows a month and year picker for the monthly report", () => {
    render(<ReportControls {...baseProps} reportType="monthly" />);
    expect(screen.getByLabelText("Month")).toBeInTheDocument();
    expect(screen.getByLabelText("Year")).toHaveValue(2026);
  });

  it("calls onMonthChange and onYearChange when the monthly picker changes", () => {
    const onMonthChange = vi.fn();
    const onYearChange = vi.fn();
    render(
      <ReportControls
        {...baseProps}
        reportType="monthly"
        onMonthChange={onMonthChange}
        onYearChange={onYearChange}
      />
    );
    fireEvent.change(screen.getByLabelText("Month"), { target: { value: "3" } });
    expect(onMonthChange).toHaveBeenCalledWith(3);
    fireEvent.change(screen.getByLabelText("Year"), { target: { value: "2025" } });
    expect(onYearChange).toHaveBeenCalledWith(2025);
  });

  it("shows only a year picker for the yearly report", () => {
    render(<ReportControls {...baseProps} reportType="yearly" />);
    expect(screen.queryByLabelText("Month")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Year")).toHaveValue(2026);
  });

  it("shows a date-range selector for range-based reports", () => {
    render(<ReportControls {...baseProps} reportType="category" />);
    expect(screen.getByLabelText("Date range")).toBeInTheDocument();
  });

  it("reveals custom date inputs when the custom range is selected", () => {
    render(<ReportControls {...baseProps} reportType="income" range="custom" />);
    expect(screen.getByLabelText("From")).toBeInTheDocument();
    expect(screen.getByLabelText("To")).toBeInTheDocument();
  });

  it("renders no controls for the budget report", () => {
    const { container } = render(<ReportControls {...baseProps} reportType="budget" />);
    expect(container).toBeEmptyDOMElement();
  });

  it("renders no controls for the net worth report", () => {
    const { container } = render(<ReportControls {...baseProps} reportType="net-worth" />);
    expect(container).toBeEmptyDOMElement();
  });
});
