/**
 * Illustrative, hand-written demo data for the public marketing page only.
 *
 * NOT real user data, NOT a live API response, NOT tied to any account.
 * Every section that renders this clearly labels it "Illustrative example"
 * or "Example" in its own copy - this module exists purely so those
 * sections can reuse the REAL dashboard/budget/goal presentational
 * components (see components/dashboard, components/ai) with internally
 * consistent numbers, rather than each section inventing its own ad hoc
 * shape. Never import this outside app/(marketing).
 */

import type {
  CategoryBreakdownItem,
  HealthScore,
  MonthlySpending,
} from "@/lib/dashboard";
import type { SpendingOverTime } from "@/lib/analytics";

export const DEMO_CURRENCY = "INR";

export const demoStats = {
  totalBalanceMinor: 48265000,
  netWorthMinor: 61520000,
  incomeMinor: 9500000,
  expenseMinor: 5842000,
  savingsMinor: 3658000,
  savingsRatePercent: 38.5,
};

/** The single rounded savings-rate figure shown anywhere on the landing
 * page - the Hero stat card and the Health Score factor detail both read
 * this instead of independently rounding demoStats.savingsRatePercent, so
 * the two numbers can never drift apart when they appear side by side. */
export const demoSavingsRatePercentRounded = Math.round(demoStats.savingsRatePercent);

export const demoMonthlySpending: MonthlySpending = {
  current_month_expense_minor: 5842000,
  previous_month_expense_minor: 6210000,
  percent_change: -5.9,
  daily_average_minor: 194733,
  projected_month_expense_minor: 5842000,
  days_elapsed: 30,
  days_in_month: 30,
};

export const demoCategoryBreakdown: CategoryBreakdownItem[] = [
  { category_id: "1", name: "Shopping", icon: "🛍️", color: "#6366f1", amount_minor: 1150000, percent: 19.7 },
  { category_id: "2", name: "Bills & Utilities", icon: "💡", color: "#f59e0b", amount_minor: 980000, percent: 16.8 },
  { category_id: "3", name: "Food", icon: "🍔", color: "#10b981", amount_minor: 1420000, percent: 24.3 },
  { category_id: "4", name: "Transport", icon: "🚕", color: "#3b82f6", amount_minor: 810000, percent: 13.9 },
  { category_id: "5", name: "Entertainment", icon: "🎬", color: "#ec4899", amount_minor: 620000, percent: 10.6 },
  { category_id: "6", name: "Other", icon: "🏷️", color: "#71717a", amount_minor: 862000, percent: 14.7 },
];

export const demoHealthScore: HealthScore = {
  score: 78,
  label: "Good",
  factors: [
    {
      key: "savings_rate",
      label: "Savings rate",
      weight: 0.3,
      score: 85,
      detail: `You're saving ${demoSavingsRatePercentRounded}% of your income this month.`,
      is_positive: true,
    },
    {
      key: "budget_adherence",
      label: "Budget adherence",
      weight: 0.25,
      score: 72,
      detail: "Most categories are within budget this month.",
      is_positive: true,
    },
    {
      key: "recurring_ratio",
      label: "Recurring cost ratio",
      weight: 0.2,
      score: 65,
      detail: "Recurring bills make up a moderate share of spending.",
      is_positive: false,
    },
  ],
};

export interface DemoTransaction {
  id: string;
  description: string;
  categoryName: string;
  categoryIcon: string;
  categoryColor: string;
  accountName: string;
  type: "income" | "expense" | "transfer";
  amountMinor: number;
}

export const demoRecentTransactions: DemoTransaction[] = [
  { id: "t1", description: "Salary", categoryName: "Income", categoryIcon: "💼", categoryColor: "#10b981", accountName: "Main Bank", type: "income", amountMinor: 9500000 },
  { id: "t2", description: "Amazon", categoryName: "Shopping", categoryIcon: "🛍️", categoryColor: "#6366f1", accountName: "Credit Card", type: "expense", amountMinor: 234000 },
  { id: "t3", description: "Swiggy", categoryName: "Food", categoryIcon: "🍔", categoryColor: "#10b981", accountName: "UPI", type: "expense", amountMinor: 54000 },
  { id: "t4", description: "Electricity bill", categoryName: "Bills & Utilities", categoryIcon: "💡", categoryColor: "#f59e0b", accountName: "Main Bank", type: "expense", amountMinor: 210000 },
  { id: "t5", description: "Uber", categoryName: "Transport", categoryIcon: "🚕", categoryColor: "#3b82f6", accountName: "UPI", type: "expense", amountMinor: 38000 },
];

export interface DemoBudget {
  categoryName: string;
  categoryIcon: string;
  status: "healthy" | "warning" | "near_limit" | "exceeded";
  spentMinor: number;
  amountMinor: number;
  percentUsed: number;
  projectedMonthMinor: number;
}

export const demoBudgets: DemoBudget[] = [
  {
    categoryName: "Transport",
    categoryIcon: "🚕",
    status: "healthy",
    spentMinor: 810000,
    amountMinor: 1000000,
    percentUsed: 81,
    projectedMonthMinor: 940000,
  },
  {
    categoryName: "Food",
    categoryIcon: "🍔",
    status: "near_limit",
    spentMinor: 1420000,
    amountMinor: 1500000,
    percentUsed: 94.7,
    projectedMonthMinor: 1610000,
  },
  {
    categoryName: "Entertainment",
    categoryIcon: "🎬",
    status: "exceeded",
    spentMinor: 620000,
    amountMinor: 500000,
    percentUsed: 124,
    projectedMonthMinor: 680000,
  },
];

export interface DemoGoal {
  name: string;
  currentAmountMinor: number;
  targetAmountMinor: number;
  progressPercent: number;
  targetDateLabel: string;
  requiredMonthlyMinor: number;
}

export const demoGoal: DemoGoal = {
  name: "Emergency Fund",
  currentAmountMinor: 18500000,
  targetAmountMinor: 30000000,
  progressPercent: 61.7,
  targetDateLabel: "31 May 2027",
  requiredMonthlyMinor: 1437500,
};

export const demoSpendingOverTime: SpendingOverTime = {
  granularity: "month",
  trend: { direction: "decreasing", percent_change: -5.9 },
  points: [
    { period: "2026-04-01", amount_minor: 6410000 },
    { period: "2026-05-01", amount_minor: 6120000 },
    { period: "2026-06-01", amount_minor: 6580000 },
    { period: "2026-07-01", amount_minor: 5970000 },
    { period: "2026-08-01", amount_minor: 6210000 },
    { period: "2026-09-01", amount_minor: 5842000 },
  ],
};

export interface DemoConversationTurn {
  role: "user" | "assistant";
  content: string;
}

/** Illustrative only - mirrors the ACTUAL structure the assistant's real
 * answers use (Fact / Calculation / Assumption labels - see
 * components/ai/chat-message-bubble.tsx and backend/app/services/
 * ai_assistant_service.py's system prompt), but this exact conversation
 * never happened and is not tied to any real account. */
export const demoConversation: DemoConversationTurn[] = [
  { role: "user", content: "How much did I spend on food last month?" },
  {
    role: "assistant",
    content:
      "Fact: You spent ₹14,200 on Food last month, across 18 transactions.\nCalculation: That's about 24.3% of last month's total expenses.",
  },
  { role: "user", content: "How does this month compare with last month?" },
  {
    role: "assistant",
    content:
      "Fact: This month's spending is ₹58,420 so far, compared to ₹62,100 last month.\nCalculation: That's a 5.9% decrease.",
  },
];
