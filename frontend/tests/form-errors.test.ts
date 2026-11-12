import { describe, expect, it } from "vitest";

import { ApiError } from "@/lib/api-client";
import { toFormErrors } from "@/lib/form-errors";

function schemaError(fieldErrors: Record<string, string>) {
  return new ApiError(422, {
    code: "validation_error",
    message: "One or more fields are invalid.",
    field_errors: fieldErrors,
  });
}

function serviceError(message: string, fieldErrors: Record<string, string>) {
  return new ApiError(422, { code: "validation_error", message, field_errors: fieldErrors });
}

describe("toFormErrors", () => {
  it("shows a schema error inline under the form's own slot key, in plain language", () => {
    const result = toFormErrors(
      schemaError({ amount_minor: "Input should be greater than 0" }),
      { amount_minor: "amount" }
    );
    expect(result).toEqual({
      fieldErrors: { amount: "Input should be greater than 0." },
      formError: null,
    });
  });

  it("rewrites Pydantic's length and required wording", () => {
    const result = toFormErrors(
      schemaError({
        merchant: "String should have at most 200 characters",
        name: "Field required",
      }),
      { merchant: "merchant", name: "name" }
    );
    expect(result.fieldErrors).toEqual({
      merchant: "Must be 200 characters or fewer.",
      name: "This field is required.",
    });
  });

  it("never drops a schema error the form has no slot for - it goes to form level with a label", () => {
    const result = toFormErrors(
      schemaError({ payment_method: "String should have at most 50 characters" }),
      { amount_minor: "amount" }
    );
    expect(result.fieldErrors).toEqual({});
    expect(result.formError).toBe("Payment method: Must be 50 characters or fewer.");
  });

  it("shows a service rule's sentence next to its field, never the machine code", () => {
    const result = toFormErrors(
      serviceError("Transfers between accounts in different currencies aren't supported yet.", {
        transfer_account_id: "currency mismatch",
      }),
      { transfer_account_id: "transfer_account_id" }
    );
    expect(result.fieldErrors).toEqual({
      transfer_account_id:
        "Transfers between accounts in different currencies aren't supported yet.",
    });
    expect(result.formError).toBeNull();
    expect(JSON.stringify(result)).not.toContain("currency mismatch");
  });

  it("puts a service rule's sentence at form level when the form has no slot for it", () => {
    const result = toFormErrors(
      serviceError("This account is archived.", { account_id: "archived" }),
      {}
    );
    expect(result).toEqual({ fieldErrors: {}, formError: "This account is archived." });
  });

  it("matches nested paths exactly first, then by their first segment", () => {
    expect(
      toFormErrors(schemaError({ "credit_card.credit_limit_minor": "Input should be greater than 0" }), {
        "credit_card.credit_limit_minor": "credit_limit",
      }).fieldErrors
    ).toEqual({ credit_limit: "Input should be greater than 0." });

    expect(
      toFormErrors(schemaError({ "tags.0": "String should have at most 50 characters" }), {
        tags: "tags",
      }).fieldErrors
    ).toEqual({ tags: "Must be 50 characters or fewer." });
  });

  it("strips Pydantic's 'Value error,' prefix from custom validators", () => {
    const result = toFormErrors(
      schemaError({ type: "Value error, Recurring transfers are not supported." }),
      { type: "type" }
    );
    expect(result.fieldErrors.type).toBe("Recurring transfers are not supported.");
  });

  it("uses the backend message when there are no field errors (e.g. a 409)", () => {
    const conflict = new ApiError(409, {
      code: "conflict",
      message: "A budget for this category already exists. Edit it instead.",
      field_errors: null,
    });
    expect(toFormErrors(conflict, {})).toEqual({
      fieldErrors: {},
      formError: "A budget for this category already exists. Edit it instead.",
    });
  });

  it("never exposes a raw network error", () => {
    expect(toFormErrors(new TypeError("Failed to fetch"), {})).toEqual({
      fieldErrors: {},
      formError: "Something went wrong. Please try again.",
    });
  });
});
