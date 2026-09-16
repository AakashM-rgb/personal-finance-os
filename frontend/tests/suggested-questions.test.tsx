import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { SuggestedQuestions } from "@/components/ai/suggested-questions";
import { SUGGESTED_QUESTIONS } from "@/lib/ai";

describe("SuggestedQuestions", () => {
  it("renders every suggested question as a button", () => {
    render(<SuggestedQuestions onSelect={vi.fn()} />);
    for (const question of SUGGESTED_QUESTIONS) {
      expect(screen.getByRole("button", { name: question })).toBeInTheDocument();
    }
  });

  it("calls onSelect with the question text when clicked", () => {
    const onSelect = vi.fn();
    render(<SuggestedQuestions onSelect={onSelect} />);
    fireEvent.click(screen.getByRole("button", { name: SUGGESTED_QUESTIONS[0] }));
    expect(onSelect).toHaveBeenCalledWith(SUGGESTED_QUESTIONS[0]);
  });

  it("disables every button when disabled is true", () => {
    render(<SuggestedQuestions onSelect={vi.fn()} disabled />);
    for (const question of SUGGESTED_QUESTIONS) {
      expect(screen.getByRole("button", { name: question })).toBeDisabled();
    }
  });
});
