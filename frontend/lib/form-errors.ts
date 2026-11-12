import { ApiError } from "@/lib/api-client";

/** The fixed `message` the backend sends for a Pydantic (schema-level)
 * validation failure - see backend/app/core/errors.py. Its `field_errors`
 * hold readable Pydantic messages per field. Any other 422 comes from a
 * service rule (ValidationAppError), whose `message` is the readable
 * sentence and whose `field_errors` values are short machine codes
 * ("required", "currency mismatch", "not found") never meant for display. */
const SCHEMA_VALIDATION_MESSAGE = "One or more fields are invalid.";

const UNKNOWN_FAILURE_MESSAGE = "Something went wrong. Please try again.";

export interface FormErrors {
  /** Keyed by the form's own field keys, ready to render inline. */
  fieldErrors: Record<string, string>;
  /** A form-level message, or null when every problem is shown inline. */
  formError: string | null;
}

/** Turns Pydantic's wording into user-facing copy for the common cases. */
function humanizeSchemaMessage(message: string): string {
  if (message === "Field required") return "This field is required.";
  const maxLength = message.match(/^String should have at most (\d+) characters?$/);
  if (maxLength) return `Must be ${maxLength[1]} characters or fewer.`;
  const minLength = message.match(/^String should have at least (\d+) characters?$/);
  if (minLength) {
    return minLength[1] === "1" ? "This field is required." : `Must be at least ${minLength[1]} characters.`;
  }
  const text = message.replace(/^Value error, /, "");
  const sentence = text.charAt(0).toUpperCase() + text.slice(1);
  return /[.!?]$/.test(sentence) ? sentence : `${sentence}.`;
}

/** "merchant" -> "Merchant", "target_amount_minor" -> "Target amount". */
function labelFor(apiField: string): string {
  const words = apiField.split(".")[0].replace(/_minor$/, "").replace(/_id$/, "").replace(/_/g, " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}

/**
 * Maps a failed submit onto a form's inline field errors plus, when needed, a
 * form-level message - so a validation failure is never silent. `fieldMap`
 * maps each backend field the form renders an error slot for (e.g.
 * "amount_minor") to that slot's key (e.g. "amount"); nested paths such as
 * "credit_card.credit_limit_minor" or "tags.0" match an exact entry first,
 * then their first segment.
 *
 * - Service-rule errors show the backend's sentence next to the field it
 *   names (never the raw code), or at form level if the form has no slot.
 * - Schema errors show each field's message inline; anything the form has no
 *   slot for is listed at form level with a readable field label.
 * - Anything that isn't a backend error envelope gets a generic message,
 *   never a raw network/parse error string.
 */
export function toFormErrors(error: unknown, fieldMap: Record<string, string>): FormErrors {
  if (!(error instanceof ApiError)) {
    return { fieldErrors: {}, formError: UNKNOWN_FAILURE_MESSAGE };
  }
  const entries = Object.entries(error.fieldErrors ?? {});
  if (entries.length === 0) {
    return { fieldErrors: {}, formError: error.message };
  }

  const isSchemaError = error.message === SCHEMA_VALIDATION_MESSAGE;
  const fieldErrors: Record<string, string> = {};
  const unplaced: string[] = [];

  for (const [apiField, detail] of entries) {
    const slot = fieldMap[apiField] ?? fieldMap[apiField.split(".")[0]];
    const message = isSchemaError ? humanizeSchemaMessage(detail) : error.message;
    if (slot === undefined) {
      unplaced.push(isSchemaError ? `${labelFor(apiField)}: ${message}` : message);
    } else if (!(slot in fieldErrors)) {
      fieldErrors[slot] = message;
    }
  }

  const formError = unplaced.length > 0 ? [...new Set(unplaced)].join(" ") : null;
  return { fieldErrors, formError };
}
