/**
 * The single place money is formatted or parsed on the frontend - values are
 * always integer minor units (paise) on the wire, exactly like the backend.
 * Every conversion here uses integer/string math, never `parseFloat(x) * 100`
 * style arithmetic, so display never introduces the rounding errors that
 * floating-point money math is prone to.
 */

/** Every currency this app supports, wherever a user picks one (accounts,
 * settings, goals) - kept small and explicit rather than open-ended,
 * matching the backend's own app.schemas.account.SUPPORTED_CURRENCIES. */
export const CURRENCIES = ["INR", "USD", "EUR", "GBP", "JPY"] as const;

/**
 * The largest magnitude a money value may have, in minor units -- mirrors
 * `MAX_MONEY_MINOR` in backend/app/schemas/money.py, which the API enforces.
 *
 * Two reasons this is a parsing rule and not just a server concern. A typed
 * amount above `Number.MAX_SAFE_INTEGER` (about 9x10^15) cannot survive
 * `parseInt` exactly, so without a ceiling the app would silently send a
 * *different* number than the user typed -- the one thing money handling here
 * must never do. And rejecting it at the input turns a server 422 into
 * immediate inline feedback (CLAUDE.md §7: client validation mirrors the
 * backend's constraints).
 */
export const MAX_MONEY_MINOR = 10 ** 13;

const DECIMALS_BY_CURRENCY: Record<string, number> = {
  INR: 2,
  USD: 2,
  EUR: 2,
  GBP: 2,
  JPY: 0,
};

function decimalsFor(currency: string): number {
  return DECIMALS_BY_CURRENCY[currency] ?? 2;
}

/** Formats integer minor units as a localized currency string, e.g. 3245000 -> "₹32,450.00". */
export function formatMoney(amountMinor: number, currency = "INR"): string {
  const decimals = decimalsFor(currency);
  const factor = 10 ** decimals;
  const major = amountMinor / factor;
  const locale = currency === "INR" ? "en-IN" : "en-US";
  return new Intl.NumberFormat(locale, {
    style: "currency",
    currency,
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(major);
}

/** Formats integer minor units as a plain editable number string, e.g. 3245000 -> "32450.00". */
export function minorUnitsToInputValue(amountMinor: number, currency = "INR"): string {
  const decimals = decimalsFor(currency);
  if (decimals === 0) return String(amountMinor);

  const factor = 10 ** decimals;
  const sign = amountMinor < 0 ? "-" : "";
  const abs = Math.abs(amountMinor);
  const whole = Math.floor(abs / factor);
  const fraction = String(abs % factor).padStart(decimals, "0");
  return `${sign}${whole}.${fraction}`;
}

/**
 * Parses a user-typed amount (e.g. "1,234.5") into integer minor units.
 * Returns null if the input isn't a valid amount for the given currency,
 * which includes any magnitude above `MAX_MONEY_MINOR` -- callers already
 * surface null as "enter a valid amount", and a number too large to represent
 * exactly is not a valid amount.
 */
export function parseMoneyToMinorUnits(input: string, currency = "INR"): number | null {
  const decimals = decimalsFor(currency);
  const cleaned = input.trim().replace(/,/g, "");
  if (cleaned === "") return null;

  if (decimals === 0) {
    if (!/^-?\d+$/.test(cleaned)) return null;
    return withinBounds(parseInt(cleaned, 10));
  }

  const pattern = new RegExp(`^(-)?(\\d+)(?:\\.(\\d{1,${decimals}}))?$`);
  const match = cleaned.match(pattern);
  if (!match) return null;

  const [, sign, wholePart, fractionPart = ""] = match;
  const paddedFraction = fractionPart.padEnd(decimals, "0");
  const magnitude = parseInt(wholePart + paddedFraction, 10);
  return withinBounds(sign ? -magnitude : magnitude);
}

/** null for anything outside the representable, API-accepted range. */
function withinBounds(amountMinor: number): number | null {
  if (!Number.isSafeInteger(amountMinor)) return null;
  if (Math.abs(amountMinor) > MAX_MONEY_MINOR) return null;
  return amountMinor;
}
