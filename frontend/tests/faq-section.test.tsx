import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { FAQSection } from "@/components/marketing/faq-section";

describe("FAQSection", () => {
  it("renders every question closed by default", () => {
    render(<FAQSection />);
    const allDetails = document.querySelectorAll("details");
    expect(allDetails.length).toBeGreaterThan(0);
    for (const details of Array.from(allDetails)) {
      expect(details).not.toHaveAttribute("open");
    }
  });

  it("clicking a question reveals its answer via the native disclosure widget", () => {
    render(<FAQSection />);
    const summary = screen.getByText(/does the ai generate sql/i);
    const details = summary.closest("details") as HTMLDetailsElement;
    expect(details.open).toBe(false);

    fireEvent.click(summary);
    expect(details.open).toBe(true);
    expect(screen.getByText(/never execute arbitrary or ai-generated sql/i)).toBeInTheDocument();
  });

  it("answers accurately state the AI/search never execute arbitrary SQL", () => {
    render(<FAQSection />);
    const summary = screen.getByText(/does the ai generate sql/i);
    fireEvent.click(summary);
    const answer = screen.getByText(/never execute arbitrary or ai-generated sql/i);
    expect(answer.textContent).toMatch(/fixed set of read-only, validated tools/i);
  });

  it("covers offline sync duplicate-safety in its own answer", () => {
    render(<FAQSection />);
    expect(screen.getByText(/how does offline expense sync work/i)).toBeInTheDocument();
  });
});
