import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { MonthNavigator } from "@/components/calendar/month-navigator";

describe("MonthNavigator", () => {
  it("renders the current month and year", () => {
    render(<MonthNavigator year={2026} month={9} onChange={vi.fn()} />);
    expect(screen.getByText("September 2026")).toBeInTheDocument();
  });

  it("goes to the previous month within the same year", () => {
    const onChange = vi.fn();
    render(<MonthNavigator year={2026} month={9} onChange={onChange} />);
    fireEvent.click(screen.getByRole("button", { name: "Previous month" }));
    expect(onChange).toHaveBeenCalledWith(2026, 8);
  });

  it("rolls over to December of the previous year when going back from January", () => {
    const onChange = vi.fn();
    render(<MonthNavigator year={2026} month={1} onChange={onChange} />);
    fireEvent.click(screen.getByRole("button", { name: "Previous month" }));
    expect(onChange).toHaveBeenCalledWith(2025, 12);
  });

  it("goes to the next month within the same year", () => {
    const onChange = vi.fn();
    render(<MonthNavigator year={2026} month={9} onChange={onChange} />);
    fireEvent.click(screen.getByRole("button", { name: "Next month" }));
    expect(onChange).toHaveBeenCalledWith(2026, 10);
  });

  it("rolls over to January of the next year when going forward from December", () => {
    const onChange = vi.fn();
    render(<MonthNavigator year={2026} month={12} onChange={onChange} />);
    fireEvent.click(screen.getByRole("button", { name: "Next month" }));
    expect(onChange).toHaveBeenCalledWith(2027, 1);
  });

  it("jumps to the real current month and year when Today is clicked", () => {
    const onChange = vi.fn();
    render(<MonthNavigator year={2020} month={3} onChange={onChange} />);
    fireEvent.click(screen.getByRole("button", { name: "Today" }));
    const now = new Date();
    expect(onChange).toHaveBeenCalledWith(now.getFullYear(), now.getMonth() + 1);
  });

  it("allows its row to wrap instead of overflowing at narrow widths", () => {
    // Regression test: the four controls (prev, month label, next, Today)
    // plus their gaps didn't fit on one line at 375px wide - found live via
    // Playwright as a 2px horizontal page overflow on the Calendar page.
    // Without flex-wrap here, a too-narrow container has nowhere for the
    // overflowing content to go but past the viewport edge.
    const { container } = render(<MonthNavigator year={2026} month={9} onChange={vi.fn()} />);
    expect(container.firstElementChild).toHaveClass("flex-wrap");
  });
});
