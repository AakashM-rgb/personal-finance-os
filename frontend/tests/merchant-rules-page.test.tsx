import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import MerchantRulesPage from "@/app/(app)/settings/merchant-rules/page";
import { ApiError } from "@/lib/api-client";
import * as authContext from "@/lib/auth-context";
import * as merchantRulesLib from "@/lib/merchant-rules";
import type { MerchantRule } from "@/lib/merchant-rules";

vi.mock("@/lib/auth-context", async () => {
  const actual = await vi.importActual<typeof import("@/lib/auth-context")>("@/lib/auth-context");
  return { ...actual, useAuth: vi.fn() };
});

function mockAuthed() {
  vi.mocked(authContext.useAuth).mockReturnValue({
    user: {
      id: "u1",
      email: "jane@example.com",
      full_name: "Jane Doe",
      is_active: true,
      email_verified_at: "2026-01-05T00:00:00Z",
      created_at: "2026-01-01T00:00:00Z",
    },
    accessToken: "token-123",
    isLoading: false,
    register: vi.fn(),
    login: vi.fn(),
    logout: vi.fn(),
    logoutAll: vi.fn(),
  });
}

function buildRule(overrides: Partial<MerchantRule> = {}): MerchantRule {
  return {
    id: "rule-1",
    merchant_key: "Abc Education",
    category_id: "cat-1",
    category_name: "Education",
    category_icon: "🎓",
    category_color: "#14B8A6",
    created_at: "2026-09-18T00:00:00Z",
    updated_at: "2026-09-18T00:00:00Z",
    ...overrides,
  };
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("MerchantRulesPage", () => {
  it("shows the empty state", async () => {
    mockAuthed();
    vi.spyOn(merchantRulesLib, "listMerchantRules").mockResolvedValue([]);

    render(<MerchantRulesPage />);

    expect(await screen.findByText("No merchant rules yet.")).toBeInTheDocument();
  });

  it("renders a rule as merchant -> category", async () => {
    mockAuthed();
    vi.spyOn(merchantRulesLib, "listMerchantRules").mockResolvedValue([buildRule()]);

    render(<MerchantRulesPage />);

    expect(await screen.findByText("Abc Education")).toBeInTheDocument();
    expect(screen.getByText("→ Education")).toBeInTheDocument();
  });

  it("shows an error state with retry when the list fails to load", async () => {
    mockAuthed();
    vi.spyOn(merchantRulesLib, "listMerchantRules").mockRejectedValue(
      new ApiError(500, { code: "internal_error", message: "Something went wrong.", field_errors: null })
    );

    render(<MerchantRulesPage />);

    expect(await screen.findByText("Something went wrong.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });

  it("removes a rule after confirmation", async () => {
    mockAuthed();
    vi.spyOn(merchantRulesLib, "listMerchantRules")
      .mockResolvedValueOnce([buildRule()])
      .mockResolvedValueOnce([]);
    const deleteSpy = vi.spyOn(merchantRulesLib, "deleteMerchantRule").mockResolvedValue(undefined);

    render(<MerchantRulesPage />);
    fireEvent.click(await screen.findByRole("button", { name: "Remove" }));
    fireEvent.click(await screen.findByRole("button", { name: "Confirm" }));

    await waitFor(() => expect(deleteSpy).toHaveBeenCalledWith("token-123", "rule-1"));
    expect(await screen.findByText("No merchant rules yet.")).toBeInTheDocument();
  });

  it("never renders provider secrets or raw request payloads", async () => {
    mockAuthed();
    vi.spyOn(merchantRulesLib, "listMerchantRules").mockResolvedValue([buildRule()]);

    const { container } = render(<MerchantRulesPage />);
    await screen.findByText("Abc Education");

    const rendered = container.textContent ?? "";
    expect(rendered).not.toMatch(/pin|cvv|otp|password/i);
  });
});
