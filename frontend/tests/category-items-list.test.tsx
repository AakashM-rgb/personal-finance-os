import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { CategoryItemsList } from "@/components/reports/category-items-list";
import type { CategoryReportItem } from "@/lib/reports";

describe("CategoryItemsList", () => {
  it("shows the empty message when there are no items", () => {
    render(
      <CategoryItemsList items={[]} currency="INR" emptyMessage="No expenses recorded yet." />
    );
    expect(screen.getByText("No expenses recorded yet.")).toBeInTheDocument();
  });

  it("renders each category's amount, percent share, and transaction count", () => {
    const items: CategoryReportItem[] = [
      {
        category_id: "cat-1",
        name: "Groceries",
        icon: "🛒",
        color: "#059669",
        amount_minor: 300000,
        percent: 60,
        transaction_count: 4,
      },
    ];
    render(<CategoryItemsList items={items} currency="INR" emptyMessage="empty" />);
    expect(screen.getByText("Groceries")).toBeInTheDocument();
    expect(screen.getByText(/₹3,000\.00/)).toBeInTheDocument();
    expect(screen.getByText(/60\.0%/)).toBeInTheDocument();
    expect(screen.getByText(/4 txns/)).toBeInTheDocument();
  });

  it("explicitly labels uncategorized spending rather than silently dropping it", () => {
    const items: CategoryReportItem[] = [
      {
        category_id: null,
        name: "Uncategorized",
        icon: "❓",
        color: "#71717a",
        amount_minor: 50000,
        percent: 10,
        transaction_count: 1,
      },
    ];
    render(<CategoryItemsList items={items} currency="INR" emptyMessage="empty" />);
    expect(screen.getByText("Uncategorized")).toBeInTheDocument();
    expect(screen.getByText(/1 txn(?!s)/)).toBeInTheDocument();
  });
});
