/**
 * Local-calendar-day helpers for date pickers. A user picking "5 Oct" means
 * their own 5 Oct (e.g. IST), not 5 Oct in UTC - so the instant sent to the
 * API is local midnight, and an instant shown back in a picker is rendered
 * in local time, matching how transaction dates are displayed.
 */

function pad(n: number): string {
  return String(n).padStart(2, "0");
}

/** A Date as an `<input type="date">` value ("YYYY-MM-DD") in local time. */
export function toLocalDateInputValue(date: Date): string {
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

/** "2026-10-05" -> the ISO instant of local midnight starting that day. */
export function startOfLocalDayIso(dateInputValue: string): string {
  return new Date(`${dateInputValue}T00:00:00`).toISOString();
}

/** "2026-10-05" -> the ISO instant of the last millisecond of that local day. */
export function endOfLocalDayIso(dateInputValue: string): string {
  return new Date(`${dateInputValue}T23:59:59.999`).toISOString();
}
