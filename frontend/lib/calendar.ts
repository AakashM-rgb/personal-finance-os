import { apiRequest } from "@/lib/api-client";
import type { RecurrenceFrequency } from "@/lib/recurring-transactions";
import type { Transaction, TransactionType } from "@/lib/transactions";

export interface CalendarBill {
  recurring_transaction_id: string;
  name: string;
  type: TransactionType;
  amount_minor: number;
  currency: string;
  frequency: RecurrenceFrequency;
  is_subscription: boolean;
}

export interface CalendarDay {
  date: string;
  income_minor: number;
  expense_minor: number;
  net_minor: number;
  transactions: Transaction[];
  bills: CalendarBill[];
}

export interface CalendarMonth {
  year: number;
  month: number;
  currency: string;
  days: CalendarDay[];
}

export async function getCalendarMonth(
  accessToken: string,
  year: number,
  month: number
): Promise<CalendarMonth> {
  return apiRequest<CalendarMonth>(`/api/v1/calendar?year=${year}&month=${month}`, {
    accessToken,
  });
}
