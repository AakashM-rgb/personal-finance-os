import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ChangePasswordForm } from "@/components/settings/change-password-form";
import { ApiError } from "@/lib/api-client";
import * as authContext from "@/lib/auth-context";
import type { ChangePasswordInput } from "@/lib/auth-context";
import { checkPasswordRules, isPasswordValid } from "@/lib/password-rules";

vi.mock("@/lib/auth-context", async () => {
  const actual = await vi.importActual<typeof import("@/lib/auth-context")>("@/lib/auth-context");
  return { ...actual, useAuth: vi.fn() };
});

function mockAuth(changePassword: (input: ChangePasswordInput) => Promise<void>) {
  vi.mocked(authContext.useAuth).mockReturnValue({
    user: null,
    accessToken: "token",
    isLoading: false,
    register: vi.fn(),
    login: vi.fn(),
    logout: vi.fn(),
    logoutAll: vi.fn(),
    changePassword,
    sessionExpired: false,
    connectionIssue: null,
    retrySessionRestore: vi.fn(),
  });
}

function fill(current: string, next: string, confirm: string) {
  fireEvent.change(screen.getByLabelText("Current password"), { target: { value: current } });
  fireEvent.change(screen.getByLabelText("New password"), { target: { value: next } });
  fireEvent.change(screen.getByLabelText("Confirm new password"), { target: { value: confirm } });
}

function submit() {
  fireEvent.click(screen.getByRole("button", { name: "Change password" }));
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("password rules", () => {
  it("mirror the backend strength rules", () => {
    expect(isPasswordValid("brandnew456")).toBe(true);
    expect(isPasswordValid("short1")).toBe(false);
    expect(isPasswordValid("onlyletters")).toBe(false);
    expect(isPasswordValid("1234567890")).toBe(false);
    expect(isPasswordValid(`a1${"x".repeat(127)}`)).toBe(false);
    expect(checkPasswordRules("abc").map((rule) => rule.isMet)).toEqual([false, true, false]);
  });
});

describe("ChangePasswordForm", () => {
  it("submits, clears the fields and shows success", async () => {
    const changePassword = vi.fn().mockResolvedValue(undefined);
    mockAuth(changePassword);
    render(<ChangePasswordForm />);

    fill("correcthorse123", "brandnew456", "brandnew456");
    submit();

    expect(await screen.findByRole("status")).toHaveTextContent(/password changed/i);
    expect(changePassword).toHaveBeenCalledWith({
      current_password: "correcthorse123",
      new_password: "brandnew456",
      confirm_password: "brandnew456",
    });
    expect(screen.getByLabelText("Current password")).toHaveValue("");
    expect(screen.getByLabelText("New password")).toHaveValue("");
  });

  it("blocks a confirmation mismatch without calling the API", () => {
    const changePassword = vi.fn();
    mockAuth(changePassword);
    render(<ChangePasswordForm />);

    fill("correcthorse123", "brandnew456", "brandnew457");
    submit();

    expect(screen.getByText("Passwords don't match.")).toBeInTheDocument();
    expect(changePassword).not.toHaveBeenCalled();
  });

  it("blocks a weak password and shows live rule feedback", () => {
    const changePassword = vi.fn();
    mockAuth(changePassword);
    render(<ChangePasswordForm />);

    fill("correcthorse123", "short", "short");
    expect(screen.getByText(/At least 8 characters/).closest("li")).toHaveTextContent("(not met)");
    expect(screen.getByText(/Contains a letter/).closest("li")).toHaveTextContent("(met)");
    submit();

    expect(screen.getByText(/doesn't meet the requirements/i)).toBeInTheDocument();
    expect(changePassword).not.toHaveBeenCalled();
  });

  it("blocks a new password identical to the current one", () => {
    const changePassword = vi.fn();
    mockAuth(changePassword);
    render(<ChangePasswordForm />);

    fill("correcthorse123", "correcthorse123", "correcthorse123");
    submit();

    expect(
      screen.getByText("New password must be different from your current password.")
    ).toBeInTheDocument();
    expect(changePassword).not.toHaveBeenCalled();
  });

  it("shows the backend's incorrect-current-password error on that field", async () => {
    const changePassword = vi.fn().mockRejectedValue(
      new ApiError(422, {
        code: "validation_error",
        message: "Your current password is incorrect.",
        field_errors: { current_password: "incorrect" },
      })
    );
    mockAuth(changePassword);
    render(<ChangePasswordForm />);

    fill("wrongpass123", "brandnew456", "brandnew456");
    submit();

    expect(await screen.findByText("Your current password is incorrect.")).toBeInTheDocument();
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("shows a generic message for a non-API failure", async () => {
    mockAuth(vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    render(<ChangePasswordForm />);

    fill("correcthorse123", "brandnew456", "brandnew456");
    submit();

    expect(await screen.findByText("Something went wrong. Please try again.")).toBeInTheDocument();
  });

  it("toggles password visibility per field", () => {
    mockAuth(vi.fn());
    render(<ChangePasswordForm />);

    const field = screen.getByLabelText("New password");
    expect(field).toHaveAttribute("type", "password");
    fireEvent.click(screen.getByRole("button", { name: "Show new password" }));
    expect(field).toHaveAttribute("type", "text");
    expect(screen.getByLabelText("Current password")).toHaveAttribute("type", "password");
    fireEvent.click(screen.getByRole("button", { name: "Hide new password" }));
    expect(field).toHaveAttribute("type", "password");
  });

  it("disables the submit button while the request is in flight", async () => {
    let resolve: () => void = () => {};
    mockAuth(vi.fn(() => new Promise<void>((r) => (resolve = r))));
    render(<ChangePasswordForm />);

    fill("correcthorse123", "brandnew456", "brandnew456");
    submit();

    await waitFor(() => expect(screen.getByRole("button", { name: "Please wait…" })).toBeDisabled());
    resolve();
    expect(await screen.findByRole("status")).toBeInTheDocument();
  });
});
