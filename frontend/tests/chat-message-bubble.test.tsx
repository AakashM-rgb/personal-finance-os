import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ChatMessageBubble } from "@/components/ai/chat-message-bubble";

describe("ChatMessageBubble", () => {
  it("renders a user message as plain text", () => {
    render(<ChatMessageBubble role="user" content="How much did I spend on food?" />);
    expect(screen.getByText("How much did I spend on food?")).toBeInTheDocument();
  });

  it("renders an assistant message's plain lines", () => {
    render(<ChatMessageBubble role="assistant" content="In March 2026, you spent 3000.00 INR." />);
    expect(screen.getByText("In March 2026, you spent 3000.00 INR.")).toBeInTheDocument();
  });

  it("emphasizes Assumptions/Calculation/Limitations labels distinctly", () => {
    const content = [
      "Assumptions: this compares 7000.00 INR against your balance.",
      "Calculation: 10000.00 INR - 7000.00 INR = 3000.00 INR remaining.",
      "Limitations: this is not personalized financial advice.",
    ].join("\n");
    render(<ChatMessageBubble role="assistant" content={content} />);

    expect(screen.getByText("Assumptions:")).toBeInTheDocument();
    expect(screen.getByText("Calculation:")).toBeInTheDocument();
    expect(screen.getByText("Limitations:")).toBeInTheDocument();
  });

  it("renders Fact and a parenthetical Estimate label distinctly", () => {
    const content = [
      "Fact: you earned 5000.00 INR this month.",
      "Estimate (a general guideline): save 20% of income.",
    ].join("\n");
    render(<ChatMessageBubble role="assistant" content={content} />);
    expect(screen.getByText("Fact:")).toBeInTheDocument();
    expect(screen.getByText("Estimate (a general guideline):")).toBeInTheDocument();
  });

  it("skips blank lines", () => {
    render(<ChatMessageBubble role="assistant" content={"First line\n\nSecond line"} />);
    expect(screen.getByText("First line")).toBeInTheDocument();
    expect(screen.getByText("Second line")).toBeInTheDocument();
  });
});
