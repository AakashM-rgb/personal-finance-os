import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { CalendarGrid } from "@/components/calendar/calendar-grid";
import type { CalendarDay, CalendarMonth } from "@/lib/calendar";

function buildDay(date: string, overrides: Partial<CalendarDay> = {}): CalendarDay {
  return {
    date,
    income_minor: 0,
    expense_minor: 0,
    net_minor: 0,
    transactions: [],
    bills: [],
    ...overrides,
  };
}

// September 2026 has 30 days and starts on a Tuesday.
function buildSeptember2026(): CalendarMonth {
  const days: CalendarDay[] = Array.from({ length: 30 }, (_, i) => {
    const day = i + 1;
    const date = `2026-09-${String(day).padStart(2, "0")}`;
    if (day === 5) return buildDay(date, { income_minor: 500000 });
    if (day === 10) {
      return buildDay(date, {
        expense_minor: 120000,
        bills: [
          {
            recurring_transaction_id: "rt-1",
            name: "Internet",
            type: "expense",
            amount_minor: 99900,
            currency: "INR",
            frequency: "monthly",
            is_subscription: false,
          },
        ],
      });
    }
    return buildDay(date);
  });

  return { year: 2026, month: 9, currency: "INR", days };
}

describe("CalendarGrid", () => {
  it("renders one button per day in the month plus the correct leading blanks", () => {
    render(<CalendarGrid data={buildSeptember2026()} onSelectDay={vi.fn()} />);
    // Sept 1, 2026 is a Tuesday -> 2 leading blank cells before day 1.
    expect(screen.getAllByRole("button")).toHaveLength(30);
    expect(screen.getByText("1")).toBeInTheDocument();
    expect(screen.getByText("30")).toBeInTheDocument();
  });

  it("shows income for a day with income and nothing for an empty day", () => {
    render(<CalendarGrid data={buildSeptember2026()} onSelectDay={vi.fn()} />);
    expect(screen.getByText("+₹5,000.00")).toBeInTheDocument();
  });

  it("shows expense and bill count for a day with a scheduled bill", () => {
    render(<CalendarGrid data={buildSeptember2026()} onSelectDay={vi.fn()} />);
    expect(screen.getByText("-₹1,200.00")).toBeInTheDocument();
    expect(screen.getByText("1 bill due")).toBeInTheDocument();
  });

  it("calls onSelectDay with the clicked day's data", () => {
    const onSelectDay = vi.fn();
    const data = buildSeptember2026();
    render(<CalendarGrid data={data} onSelectDay={onSelectDay} />);
    fireEvent.click(screen.getByText("5"));
    expect(onSelectDay).toHaveBeenCalledWith(data.days[4]);
  });
});
