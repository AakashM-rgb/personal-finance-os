import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SecuritySection } from "@/components/settings/security-section";
import { ApiError } from "@/lib/api-client";
import * as authContext from "@/lib/auth-context";
import * as sessionsLib from "@/lib/sessions";

const mockPush = vi.fn();
const mockReplace = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush, replace: mockReplace }),
}));

vi.mock("@/lib/auth-context", async () => {
  const actual = await vi.importActual<typeof import("@/lib/auth-context")>("@/lib/auth-context");
  return { ...actual, useAuth: vi.fn() };
});

afterEach(() => {
  vi.restoreAllMocks();
  mockPush.mockClear();
  mockReplace.mockClear();
});

describe("SecuritySection", () => {
  it("lists active sessions once loaded", async () => {
    vi.mocked(authContext.useAuth).mockReturnValue({
      user: null,
      accessToken: "token",
      isLoading: false,
      register: vi.fn(),
      login: vi.fn(),
      logout: vi.fn(),
      logoutAll: vi.fn(),
    });
    vi.spyOn(sessionsLib, "listSessions").mockResolvedValue([
      {
        id: "s1",
        user_agent: "Safari on macOS",
        ip_address: "198.51.100.1",
        created_at: "2026-01-10T08:00:00Z",
        expires_at: "2026-02-09T08:00:00Z",
      },
    ]);

    render(<SecuritySection accessToken="token" />);

    expect(await screen.findByText("Safari on macOS")).toBeInTheDocument();
    expect(screen.getByText(/198\.51\.100\.1/)).toBeInTheDocument();
  });

  it("shows an error with retry when sessions fail to load", async () => {
    vi.mocked(authContext.useAuth).mockReturnValue({
      user: null,
      accessToken: "token",
      isLoading: false,
      register: vi.fn(),
      login: vi.fn(),
      logout: vi.fn(),
      logoutAll: vi.fn(),
    });
    vi.spyOn(sessionsLib, "listSessions").mockRejectedValue(
      new ApiError(500, { code: "internal_error", message: "Failed to load sessions.", field_errors: null })
    );

    render(<SecuritySection accessToken="token" />);

    expect(await screen.findByText("Failed to load sessions.")).toBeInTheDocument();
  });

  it("requires confirmation before logging out of all devices, then redirects to login", async () => {
    const logoutAll = vi.fn().mockResolvedValue(undefined);
    vi.mocked(authContext.useAuth).mockReturnValue({
      user: null,
      accessToken: "token",
      isLoading: false,
      register: vi.fn(),
      login: vi.fn(),
      logout: vi.fn(),
      logoutAll,
    });
    vi.spyOn(sessionsLib, "listSessions").mockResolvedValue([]);

    render(<SecuritySection accessToken="token" />);
    await waitFor(() => expect(sessionsLib.listSessions).toHaveBeenCalled());

    const triggerButton = screen.getByRole("button", { name: "Log out of all devices" });
    fireEvent.click(triggerButton);

    // logoutAll must not fire until the destructive action is confirmed.
    expect(logoutAll).not.toHaveBeenCalled();
    expect(screen.getByText(/signs out every device above/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Yes, log out of all devices" }));

    await waitFor(() => expect(logoutAll).toHaveBeenCalled());
    await waitFor(() => expect(mockReplace).toHaveBeenCalledWith("/login"));
  });

  it("cancelling the confirmation does not log out", async () => {
    const logoutAll = vi.fn();
    vi.mocked(authContext.useAuth).mockReturnValue({
      user: null,
      accessToken: "token",
      isLoading: false,
      register: vi.fn(),
      login: vi.fn(),
      logout: vi.fn(),
      logoutAll,
    });
    vi.spyOn(sessionsLib, "listSessions").mockResolvedValue([]);

    render(<SecuritySection accessToken="token" />);
    fireEvent.click(screen.getByRole("button", { name: "Log out of all devices" }));
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));

    expect(logoutAll).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Log out of all devices" })).toBeInTheDocument();
  });
});
