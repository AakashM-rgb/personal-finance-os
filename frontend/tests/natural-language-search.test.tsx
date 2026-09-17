import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { NaturalLanguageSearch } from "@/components/search/natural-language-search";
import { ApiError } from "@/lib/api-client";
import * as authContext from "@/lib/auth-context";
import * as searchLib from "@/lib/search";
import type { SearchResponse } from "@/lib/search";

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
    logoutAll: vi.fn(),
  });
}

function baseInterpretation(
  overrides: Partial<SearchResponse["interpretation"]> = {}
): SearchResponse["interpretation"] {
  return {
    search_text: null,
    category_name: null,
    start_date: null,
    end_date: null,
    min_amount_minor: null,
    max_amount_minor: null,
    transaction_type: null,
    is_weekend_only: false,
    subscriptions_only: false,
    sort: "date_desc",
    limit: 20,
    currency: "INR",
    ...overrides,
  };
}

function response(overrides: Partial<SearchResponse> = {}): SearchResponse {
  return {
    interpretation: baseInterpretation(),
    requires_confirmation: false,
    ambiguity_reason: null,
    ambiguous_categories: [],
    results: [],
    result_count: 0,
    total_matching: 0,
    limited: false,
    provider: "deterministic",
    ...overrides,
  };
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("NaturalLanguageSearch", () => {
  it("renders example query chips before any search", () => {
    mockAuthed();
    render(<NaturalLanguageSearch />);
    expect(screen.getByRole("button", { name: "food last month" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "weekend spending" })).toBeInTheDocument();
  });

  it("shows a loading indicator while a search is in flight", async () => {
    mockAuthed();
    let resolveFn: (value: SearchResponse) => void = () => {};
    vi.spyOn(searchLib, "searchFinancial").mockReturnValue(
      new Promise((resolve) => {
        resolveFn = resolve;
      })
    );
    render(<NaturalLanguageSearch />);

    fireEvent.click(screen.getByRole("button", { name: "food last month" }));

    expect(await screen.findByRole("status")).toBeInTheDocument();
    resolveFn(response());
    await waitFor(() => expect(screen.queryByRole("status")).not.toBeInTheDocument());
  });

  it("renders results with interpreted criteria chips on a successful search", async () => {
    mockAuthed();
    vi.spyOn(searchLib, "searchFinancial").mockResolvedValue(
      response({
        interpretation: baseInterpretation({
          category_name: "Food",
          start_date: "2026-02-01",
          end_date: "2026-02-28",
          transaction_type: "expense",
        }),
        results: [
          {
            id: "t1",
            occurred_at: "2026-02-10T12:00:00Z",
            type: "expense",
            amount_minor: 45000,
            currency: "INR",
            category_name: "Food",
            merchant: null,
            description: "Groceries",
          },
        ],
        result_count: 1,
        total_matching: 1,
      })
    );
    render(<NaturalLanguageSearch />);

    fireEvent.click(screen.getByRole("button", { name: "food last month" }));

    await waitFor(() => expect(screen.getByText("Groceries")).toBeInTheDocument());
    expect(screen.getByText("Food")).toBeInTheDocument();
    expect(screen.getByText("2026-02-01 → 2026-02-28")).toBeInTheDocument();
  });

  it("shows an empty state when nothing matches", async () => {
    mockAuthed();
    vi.spyOn(searchLib, "searchFinancial").mockResolvedValue(response());
    render(<NaturalLanguageSearch />);

    fireEvent.click(screen.getByRole("button", { name: "weekend spending" }));

    await waitFor(() =>
      expect(screen.getByText(/no transactions matched that search/i)).toBeInTheDocument()
    );
  });

  it("shows an error message when the request fails", async () => {
    mockAuthed();
    vi.spyOn(searchLib, "searchFinancial").mockRejectedValue(
      new ApiError(429, { code: "rate_limited", message: "Too many requests.", field_errors: null })
    );
    render(<NaturalLanguageSearch />);

    fireEvent.click(screen.getByRole("button", { name: "food last month" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Too many requests.");
  });

  it("shows the ambiguity reason and a confirm button, then re-runs confirmed", async () => {
    mockAuthed();
    const spy = vi
      .spyOn(searchLib, "searchFinancial")
      .mockResolvedValueOnce(
        response({
          requires_confirmation: true,
          ambiguity_reason: "This search is quite general.",
        })
      )
      .mockResolvedValueOnce(response({ result_count: 1, results: [] }));
    render(<NaturalLanguageSearch />);

    fireEvent.change(screen.getByLabelText(/search your finances/i), {
      target: { value: "this month" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));

    await waitFor(() =>
      expect(screen.getByText("This search is quite general.")).toBeInTheDocument()
    );

    fireEvent.click(screen.getByRole("button", { name: "Search anyway" }));

    await waitFor(() => expect(spy).toHaveBeenLastCalledWith("token-123", "this month", { confirmed: true }));
  });

  it("shows ambiguous category candidates and resolves with the chosen one", async () => {
    mockAuthed();
    const spy = vi
      .spyOn(searchLib, "searchFinancial")
      .mockResolvedValueOnce(
        response({
          requires_confirmation: true,
          ambiguity_reason: "Multiple categories could match your search.",
          ambiguous_categories: [
            { id: "cat-1", name: "Car Insurance", icon: "🚗" },
            { id: "cat-2", name: "Car Rental", icon: "🚗" },
          ],
        })
      )
      .mockResolvedValueOnce(response());
    render(<NaturalLanguageSearch />);

    fireEvent.change(screen.getByLabelText(/search your finances/i), { target: { value: "car" } });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));

    await waitFor(() =>
      expect(screen.getByRole("button", { name: /Car Insurance/ })).toBeInTheDocument()
    );

    fireEvent.click(screen.getByRole("button", { name: /Car Insurance/ }));

    await waitFor(() =>
      expect(spy).toHaveBeenLastCalledWith("token-123", "car", { categoryOverrideId: "cat-1" })
    );
  });

  it("clears the search and returns to the example chips", async () => {
    mockAuthed();
    vi.spyOn(searchLib, "searchFinancial").mockResolvedValue(response());
    render(<NaturalLanguageSearch />);

    fireEvent.click(screen.getByRole("button", { name: "food last month" }));
    await waitFor(() =>
      expect(screen.getByText(/no transactions matched that search/i)).toBeInTheDocument()
    );

    fireEvent.click(screen.getByRole("button", { name: "Clear" }));

    expect(screen.queryByText(/no transactions matched that search/i)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "food last month" })).toBeInTheDocument();
  });

  it("notifies the parent when a confirmed/executed search becomes active or inactive", async () => {
    mockAuthed();
    vi.spyOn(searchLib, "searchFinancial").mockResolvedValue(response());
    const onActiveChange = vi.fn();
    render(<NaturalLanguageSearch onActiveChange={onActiveChange} />);

    fireEvent.click(screen.getByRole("button", { name: "food last month" }));
    await waitFor(() => expect(onActiveChange).toHaveBeenLastCalledWith(true));

    fireEvent.click(screen.getByRole("button", { name: "Clear" }));
    expect(onActiveChange).toHaveBeenLastCalledWith(false);
  });

  it("does not mark a search active while it requires confirmation", async () => {
    mockAuthed();
    vi.spyOn(searchLib, "searchFinancial").mockResolvedValue(
      response({ requires_confirmation: true, ambiguity_reason: "Too general." })
    );
    const onActiveChange = vi.fn();
    render(<NaturalLanguageSearch onActiveChange={onActiveChange} />);

    fireEvent.click(screen.getByRole("button", { name: "weekend spending" }));

    await waitFor(() => expect(screen.getByText("Too general.")).toBeInTheDocument());
    expect(onActiveChange).toHaveBeenLastCalledWith(false);
  });
});
