import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { MobileBottomNav } from "@/components/nav/mobile-bottom-nav";
import * as authContext from "@/lib/auth-context";
import * as accountsLib from "@/lib/accounts";
import * as categoriesLib from "@/lib/categories";
import * as transactionsLib from "@/lib/transactions";

const mockUsePathname = vi.fn();
vi.mock("next/navigation", () => ({
  usePathname: () => mockUsePathname(),
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
}));

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
  mockUsePathname.mockReset();
});

describe("MobileBottomNav", () => {
  it("renders Home, Transactions, Add, Analytics, and More", () => {
    mockUsePathname.mockReturnValue("/dashboard");
    mockAuthed();
    render(<MobileBottomNav />);

    expect(screen.getByRole("link", { name: /home/i })).toHaveAttribute("href", "/dashboard");
    expect(screen.getByRole("link", { name: /transactions/i })).toHaveAttribute(
      "href",
      "/transactions"
    );
    expect(screen.getByRole("button", { name: /add expense/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /analytics/i })).toHaveAttribute(
      "href",
      "/analytics"
    );
    expect(screen.getByRole("button", { name: /more options/i })).toBeInTheDocument();
  });

  it("marks the current route's tab as the active page", () => {
    mockUsePathname.mockReturnValue("/transactions");
    mockAuthed();
    render(<MobileBottomNav />);

    expect(screen.getByRole("link", { name: /transactions/i })).toHaveAttribute(
      "aria-current",
      "page"
    );
    expect(screen.getByRole("link", { name: /home/i })).not.toHaveAttribute("aria-current");
  });

  it("marks nested transaction routes as active too (startsWith match)", () => {
    mockUsePathname.mockReturnValue("/transactions/123");
    mockAuthed();
    render(<MobileBottomNav />);

    expect(screen.getByRole("link", { name: /transactions/i })).toHaveAttribute(
      "aria-current",
      "page"
    );
  });

  it("tapping Add opens the Add Expense sheet as a dialog, not a navigation", () => {
    mockUsePathname.mockReturnValue("/dashboard");
    mockAuthed();
    vi.spyOn(accountsLib, "listAccounts").mockResolvedValue([]);
    vi.spyOn(categoriesLib, "listCategories").mockResolvedValue([]);
    vi.spyOn(transactionsLib, "listTransactions").mockResolvedValue({
      transactions: [],
      total: 0,
    });

    render(<MobileBottomNav />);
    fireEvent.click(screen.getByRole("button", { name: /add expense/i }));

    expect(screen.getByRole("dialog", { name: /add expense/i })).toBeInTheDocument();
    // The URL-level route never changed - this is a dialog, not a page.
    expect(mockUsePathname()).toBe("/dashboard");
  });

  it("tapping More opens the more-options menu as a dialog", () => {
    mockUsePathname.mockReturnValue("/dashboard");
    mockAuthed();

    render(<MobileBottomNav />);
    fireEvent.click(screen.getByRole("button", { name: /more options/i }));

    expect(screen.getByRole("dialog", { name: /more/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /settings/i })).toHaveAttribute("href", "/settings");
  });
});
