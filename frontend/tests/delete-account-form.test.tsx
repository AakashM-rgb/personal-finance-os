import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { DELETE_CONFIRMATION, DeleteAccountForm } from "@/components/settings/delete-account-form";
import { ApiError } from "@/lib/api-client";
import * as authContext from "@/lib/auth-context";

const replace = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace }) }));

vi.mock("@/lib/auth-context", async () => {
  const actual = await vi.importActual<typeof import("@/lib/auth-context")>("@/lib/auth-context");
  return { ...actual, useAuth: vi.fn() };
});

function mockAuth(deleteAccount: (password: string) => Promise<void>) {
  vi.mocked(authContext.useAuth).mockReturnValue({
    user: null,
    accessToken: "token",
    isLoading: false,
    register: vi.fn(),
    login: vi.fn(),
    logout: vi.fn(),
    logoutAll: vi.fn(),
    changePassword: vi.fn(),
    deleteAccount,
    sessionExpired: false,
    connectionIssue: null,
    retrySessionRestore: vi.fn(),
  });
}

function fill(password: string, confirmation: string) {
  fireEvent.change(screen.getByLabelText("Password"), { target: { value: password } });
  fireEvent.change(screen.getByLabelText(`Type ${DELETE_CONFIRMATION} to confirm`), {
    target: { value: confirmation },
  });
}

function submit() {
  fireEvent.click(screen.getByRole("button", { name: "Delete my account" }));
}

afterEach(() => {
  vi.restoreAllMocks();
  replace.mockReset();
});

describe("DeleteAccountForm", () => {
  it("says plainly that deletion is permanent", () => {
    mockAuth(vi.fn());
    render(<DeleteAccountForm />);

    expect(screen.getByText(/permanently deletes your account/)).toBeInTheDocument();
    expect(screen.getByText(/can.t be undone/)).toBeInTheDocument();
  });

  it("does nothing until the password and the confirmation word are both given", () => {
    const deleteAccount = vi.fn();
    mockAuth(deleteAccount);
    render(<DeleteAccountForm />);

    submit();
    expect(screen.getByText("Enter your password to confirm.")).toBeInTheDocument();
    expect(screen.getByText(`Type ${DELETE_CONFIRMATION} to confirm.`)).toBeInTheDocument();

    fill("correcthorse123", "delete"); // wrong case is not the confirmation
    submit();
    expect(deleteAccount).not.toHaveBeenCalled();
  });

  it("deletes with the password and leaves the app", async () => {
    const deleteAccount = vi.fn().mockResolvedValue(undefined);
    mockAuth(deleteAccount);
    render(<DeleteAccountForm />);

    fill("correcthorse123", DELETE_CONFIRMATION);
    submit();

    await waitFor(() => expect(replace).toHaveBeenCalledWith("/login"));
    expect(deleteAccount).toHaveBeenCalledWith("correcthorse123");
  });

  it("shows a wrong password on the password field and stays put", async () => {
    mockAuth(
      vi.fn().mockRejectedValue(
        new ApiError(422, {
          code: "validation_error",
          message: "Your password is incorrect.",
          field_errors: { password: "incorrect" },
        })
      )
    );
    render(<DeleteAccountForm />);

    fill("not-it", DELETE_CONFIRMATION);
    submit();

    expect(await screen.findByText("Your password is incorrect.")).toBeInTheDocument();
    expect(replace).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Delete my account" })).not.toBeDisabled();
  });

  it("shows a readable message when the request fails outright", async () => {
    mockAuth(vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    render(<DeleteAccountForm />);

    fill("correcthorse123", DELETE_CONFIRMATION);
    submit();

    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(replace).not.toHaveBeenCalled();
  });
});
