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
 * Returns null if the input isn't a valid amount for the given currency.
 */
export function parseMoneyToMinorUnits(input: string, currency = "INR"): number | null {
  const decimals = decimalsFor(currency);
  const cleaned = input.trim().replace(/,/g, "");
  if (cleaned === "") return null;

  if (decimals === 0) {
    return /^-?\d+$/.test(cleaned) ? parseInt(cleaned, 10) : null;
  }

  const pattern = new RegExp(`^(-)?(\\d+)(?:\\.(\\d{1,${decimals}}))?$`);
  const match = cleaned.match(pattern);
  if (!match) return null;

  const [, sign, wholePart, fractionPart = ""] = match;
  const paddedFraction = fractionPart.padEnd(decimals, "0");
  const magnitude = parseInt(wholePart + paddedFraction, 10);
  return sign ? -magnitude : magnitude;
}
