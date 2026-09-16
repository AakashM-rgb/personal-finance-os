import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ChatInput } from "@/components/ai/chat-input";

describe("ChatInput", () => {
  it("sends the trimmed message and clears the input on submit", () => {
    const onSend = vi.fn();
    render(<ChatInput onSend={onSend} isLoading={false} />);
    const textarea = screen.getByLabelText(/ask the financial assistant/i);

    fireEvent.change(textarea, { target: { value: "  Where am I spending the most?  " } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    expect(onSend).toHaveBeenCalledWith("Where am I spending the most?");
    expect(textarea).toHaveValue("");
  });

  it("sends on Enter without Shift", () => {
    const onSend = vi.fn();
    render(<ChatInput onSend={onSend} isLoading={false} />);
    const textarea = screen.getByLabelText(/ask the financial assistant/i);

    fireEvent.change(textarea, { target: { value: "Compare this month with last month." } });
    fireEvent.keyDown(textarea, { key: "Enter", shiftKey: false });

    expect(onSend).toHaveBeenCalledWith("Compare this month with last month.");
  });

  it("does not send on Shift+Enter", () => {
    const onSend = vi.fn();
    render(<ChatInput onSend={onSend} isLoading={false} />);
    const textarea = screen.getByLabelText(/ask the financial assistant/i);

    fireEvent.change(textarea, { target: { value: "multi-line" } });
    fireEvent.keyDown(textarea, { key: "Enter", shiftKey: true });

    expect(onSend).not.toHaveBeenCalled();
  });

  it("does not send an empty or whitespace-only message", () => {
    const onSend = vi.fn();
    render(<ChatInput onSend={onSend} isLoading={false} />);
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    expect(onSend).not.toHaveBeenCalled();
  });

  it("disables the input and button while loading", () => {
    render(<ChatInput onSend={vi.fn()} isLoading />);
    expect(screen.getByLabelText(/ask the financial assistant/i)).toBeDisabled();
    expect(screen.getByRole("button")).toBeDisabled();
  });
});
