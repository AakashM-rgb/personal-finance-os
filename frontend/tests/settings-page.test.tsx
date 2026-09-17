import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import SettingsPage from "@/app/(app)/settings/page";
import { ApiError } from "@/lib/api-client";
import * as authContext from "@/lib/auth-context";
import * as sessionsLib from "@/lib/sessions";
import * as settingsLib from "@/lib/settings";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}));

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

afterEach(() => {
  vi.restoreAllMocks();
});

describe("SettingsPage", () => {
  it("shows loading skeletons before settings resolve", () => {
    mockAuthed();
    vi.spyOn(settingsLib, "getSettings").mockReturnValue(new Promise(() => {}));
    vi.spyOn(sessionsLib, "listSessions").mockReturnValue(new Promise(() => {}));

    render(<SettingsPage />);
    expect(screen.getByText("Settings")).toBeInTheDocument();
    // Profile renders immediately from the already-known auth user.
    expect(screen.getByText("Jane Doe")).toBeInTheDocument();
    // Preferences/Security haven't rendered yet.
    expect(screen.queryByText("Preferences")).not.toBeInTheDocument();
  });

  it("renders profile, preferences, and security once settings and sessions load", async () => {
    mockAuthed();
    vi.spyOn(settingsLib, "getSettings").mockResolvedValue({
      currency: "INR",
      theme: "system",
      ai_enabled: true,
    });
    vi.spyOn(sessionsLib, "listSessions").mockResolvedValue([
      {
        id: "s1",
        user_agent: "Chrome on Windows",
        ip_address: "203.0.113.5",
        created_at: "2026-01-10T08:00:00Z",
        expires_at: "2026-02-09T08:00:00Z",
      },
    ]);

    render(<SettingsPage />);

    await waitFor(() => expect(screen.getByText("Preferences")).toBeInTheDocument());
    expect(screen.getByText("jane@example.com")).toBeInTheDocument();
    expect(screen.getByText("Verified")).toBeInTheDocument();
    expect(screen.getByText("Security")).toBeInTheDocument();
    expect(await screen.findByText("Chrome on Windows")).toBeInTheDocument();
    expect(screen.getByText("Categories")).toBeInTheDocument();
  });

  it("shows an error state with retry when settings fail to load", async () => {
    mockAuthed();
    vi.spyOn(settingsLib, "getSettings").mockRejectedValue(
      new ApiError(500, { code: "internal_error", message: "Something went wrong.", field_errors: null })
    );
    vi.spyOn(sessionsLib, "listSessions").mockResolvedValue([]);

    render(<SettingsPage />);

    expect(await screen.findByText("Something went wrong.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });

  it("shows 'Not verified' when the account has no verified email", async () => {
    vi.mocked(authContext.useAuth).mockReturnValue({
      user: {
        id: "u1",
        email: "jane@example.com",
        full_name: "Jane Doe",
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
    vi.spyOn(settingsLib, "getSettings").mockResolvedValue({
      currency: "INR",
      theme: "system",
      ai_enabled: true,
    });
    vi.spyOn(sessionsLib, "listSessions").mockResolvedValue([]);

    render(<SettingsPage />);

    expect(await screen.findByText("Not verified")).toBeInTheDocument();
  });
});
