import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AiAssistantPage from "@/app/(app)/ai/page";
import { ApiError } from "@/lib/api-client";
import * as aiLib from "@/lib/ai";
import * as authContext from "@/lib/auth-context";

vi.mock("@/lib/auth-context", async () => {
  const actual = await vi.importActual<typeof import("@/lib/auth-context")>("@/lib/auth-context");
  return { ...actual, useAuth: vi.fn() };
});

function mockAuthed() {
  vi.mocked(authContext.useAuth).mockReturnValue({
    user: {
      id: "u1",
      email: "a@b.com",
      full_name: "A B",
      is_active: true,
      email_verified_at: null,
      created_at: "2026-01-01T00:00:00Z",
    },
    accessToken: "token-123",
    isLoading: false,
    register: vi.fn(),
    login: vi.fn(),
    logout: vi.fn(),
  });
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("AiAssistantPage", () => {
  it("renders the empty state with suggested questions", () => {
    mockAuthed();
    render(<AiAssistantPage />);
    expect(screen.getByText(/ask a question about your finances/i)).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Where am I spending the most?" })
    ).toBeInTheDocument();
  });

  it("sends a message and renders the assistant's response", async () => {
    mockAuthed();
    vi.spyOn(aiLib, "askAssistant").mockResolvedValue({
      answer: "Fact: you spent 3000.00 INR on Food this month.",
      tools_used: [{ tool_name: "get_category_spending", ok: true }],
      provider: "mock",
      disclaimer: "This is not licensed financial advice.",
    });
    render(<AiAssistantPage />);

    fireEvent.click(screen.getByRole("button", { name: "Where am I spending the most?" }));

    await waitFor(() =>
      expect(screen.getByText(/you spent 3000.00 INR on Food this month/i)).toBeInTheDocument()
    );
    // The question now appears twice: as the user's own chat bubble, and
    // still as a suggested question for a follow-up.
    expect(screen.getAllByText("Where am I spending the most?").length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText("This is not licensed financial advice.")).toBeInTheDocument();
  });

  it("shows a loading indicator while waiting for a response", async () => {
    mockAuthed();
    let resolveFn: (value: aiLib.AssistantResponse) => void = () => {};
    vi.spyOn(aiLib, "askAssistant").mockReturnValue(
      new Promise((resolve) => {
        resolveFn = resolve;
      })
    );
    render(<AiAssistantPage />);

    fireEvent.click(screen.getByRole("button", { name: "Where am I spending the most?" }));

    expect(await screen.findByRole("status")).toHaveTextContent(/analyzing your financial data/i);

    resolveFn({ answer: "done", tools_used: [], provider: "mock", disclaimer: "d" });
    await waitFor(() => expect(screen.queryByRole("status")).not.toBeInTheDocument());
  });

  it("shows an error message when the request fails", async () => {
    mockAuthed();
    vi.spyOn(aiLib, "askAssistant").mockRejectedValue(
      new ApiError(429, { code: "rate_limited", message: "Too many requests.", field_errors: null })
    );
    render(<AiAssistantPage />);

    fireEvent.click(screen.getByRole("button", { name: "Where am I spending the most?" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Too many requests.");
  });

  it("shows a demo-mode note when the provider is mock", async () => {
    mockAuthed();
    vi.spyOn(aiLib, "askAssistant").mockResolvedValue({
      answer: "hi",
      tools_used: [],
      provider: "mock",
      disclaimer: "d",
    });
    render(<AiAssistantPage />);

    fireEvent.click(screen.getByRole("button", { name: "Where am I spending the most?" }));

    await waitFor(() => expect(screen.getByText(/demo mode/i)).toBeInTheDocument());
  });
});
