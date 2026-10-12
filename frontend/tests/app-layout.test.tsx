import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AppLayout from "@/app/(app)/layout";
import * as authContext from "@/lib/auth-context";

const mockReplace = vi.fn();

vi.mock("next/navigation", () => ({
  usePathname: () => "/dashboard",
  useRouter: () => ({ push: vi.fn(), replace: mockReplace }),
}));

vi.mock("@/lib/auth-context", async () => {
  const actual = await vi.importActual<typeof import("@/lib/auth-context")>("@/lib/auth-context");
  return { ...actual, useAuth: vi.fn() };
});

vi.mock("@/lib/offline/use-offline-sync", () => ({
  useOfflineSync: () => ({
    queue: [],
    isOnline: true,
    pendingCount: 0,
    needsAttentionCount: 0,
    refresh: vi.fn(),
  }),
}));

function mockAuth(overrides: Partial<ReturnType<typeof authContext.useAuth>>) {
  vi.mocked(authContext.useAuth).mockReturnValue({
    user: null,
    accessToken: null,
    isLoading: false,
    sessionExpired: false,
    connectionIssue: null,
    retrySessionRestore: vi.fn(),
    register: vi.fn(),
    login: vi.fn(),
    logout: vi.fn(),
    logoutAll: vi.fn(),
    ...overrides,
  });
}

afterEach(() => {
  mockReplace.mockReset();
});

describe("AppLayout session gate", () => {
  it("redirects to login once the session is known to be absent", () => {
    mockAuth({});
    render(<AppLayout>page</AppLayout>);

    expect(mockReplace).toHaveBeenCalledWith("/login");
  });

  it("explains a slow restore while the server wakes up, without redirecting", () => {
    mockAuth({ isLoading: true, connectionIssue: "waking" });
    render(<AppLayout>page</AppLayout>);

    expect(screen.getByRole("status")).toHaveTextContent(/waking up the server/i);
    expect(mockReplace).not.toHaveBeenCalled();
  });

  it("offers a retry instead of the login redirect when the server is unreachable", () => {
    const retrySessionRestore = vi.fn();
    mockAuth({ connectionIssue: "unreachable", retrySessionRestore });
    render(<AppLayout>page</AppLayout>);

    expect(screen.getByRole("alert")).toHaveTextContent(/couldn.t reach the server/i);
    expect(mockReplace).not.toHaveBeenCalled();
    expect(screen.queryByText("page")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(retrySessionRestore).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("link", { name: "Go to sign in" })).toHaveAttribute("href", "/login");
  });
});
