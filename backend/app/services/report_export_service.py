"""Converts each report's real, already-computed response into an
ExportTable (see app.services.export_service) - purely a reshaping step.
No calculation happens here; every value comes directly from the report
object a caller already fetched from report_service.
"""

import calendar

from app.schemas.reports import (
    BudgetReport,
    CategoryReport,
    ExpenseReport,
    IncomeReport,
    MonthlyReport,
    NetWorthReport,
    SavingsReport,
    YearlyReport,
)
from app.services.export_formatting import format_money
from app.services.export_service import ExportColumn, ExportTable


def _percent_text(value: float | None) -> str:
    return f"{value:.1f}%" if value is not None else "N/A"


def monthly_report_table(report: MonthlyReport) -> ExportTable:
    month_name = calendar.month_name[report.month]
    return ExportTable(
        title=f"Monthly Report - {month_name} {report.year}",
        subtitle=f"{report.date_from.isoformat()} to {report.date_to.isoformat()}",
        currency=report.currency,
        summary=[
            ("Total income", format_money(report.total_income_minor, report.currency)),
            ("Total expenses", format_money(report.total_expense_minor, report.currency)),
            ("Net cash flow", format_money(report.net_cash_flow_minor, report.currency)),
            ("Savings", format_money(report.savings_minor, report.currency)),
            ("Savings rate", _percent_text(report.savings_rate)),
        ],
        columns=[
            ExportColumn("Category", "text"),
            ExportColumn("Amount", "money"),
            ExportColumn("Percent of expenses", "percent"),
        ],
        rows=[
            [item.name, item.amount_minor, item.percent] for item in report.category_breakdown.items
        ],
    )


def yearly_report_table(report: YearlyReport) -> ExportTable:
    income_by_month = {p.month: p.amount_minor for p in report.monthly_income_trend}
    expense_by_month = {p.month: p.amount_minor for p in report.monthly_expense_trend}
    savings_by_month = {p.month: p.amount_minor for p in report.monthly_savings_trend}
    months = sorted(income_by_month.keys() | expense_by_month.keys() | savings_by_month.keys())

    return ExportTable(
        title=f"Yearly Report - {report.year}",
        subtitle=f"January to December {report.year}",
        currency=report.currency,
        summary=[
            ("Total income", format_money(report.total_income_minor, report.currency)),
            ("Total expenses", format_money(report.total_expense_minor, report.currency)),
            ("Net cash flow", format_money(report.net_cash_flow_minor, report.currency)),
            ("Savings", format_money(report.savings_minor, report.currency)),
            ("Savings rate", _percent_text(report.savings_rate)),
        ],
        columns=[
            ExportColumn("Month", "date"),
            ExportColumn("Income", "money"),
            ExportColumn("Expense", "money"),
            ExportColumn("Savings", "money"),
        ],
        rows=[
            [
                m,
                income_by_month.get(m, 0),
                expense_by_month.get(m, 0),
                savings_by_month.get(m, 0),
            ]
            for m in months
        ],
    )


def category_report_table(report: CategoryReport) -> ExportTable:
    return ExportTable(
        title="Category Report",
        subtitle=f"{report.date_from.isoformat()} to {report.date_to.isoformat()}",
        currency=report.currency,
        summary=[("Total expenses", format_money(report.total_expense_minor, report.currency))],
        columns=[
            ExportColumn("Category", "text"),
            ExportColumn("Amount", "money"),
            ExportColumn("Percent of expenses", "percent"),
            ExportColumn("Transactions", "int"),
        ],
        rows=[
            [item.name, item.amount_minor, item.percent, item.transaction_count]
            for item in report.items
        ],
    )


def income_report_table(report: IncomeReport) -> ExportTable:
    return ExportTable(
        title="Income Report",
        subtitle=f"{report.date_from.isoformat()} to {report.date_to.isoformat()}",
        currency=report.currency,
        summary=[
            ("Total income", format_money(report.total_income_minor, report.currency)),
            ("Transaction count", str(report.transaction_count)),
        ],
        columns=[
            ExportColumn("Source", "text"),
            ExportColumn("Amount", "money"),
            ExportColumn("Percent of income", "percent"),
            ExportColumn("Transactions", "int"),
        ],
        rows=[
            [item.name, item.amount_minor, item.percent, item.transaction_count]
            for item in report.by_source
        ],
    )


def expense_report_table(report: ExpenseReport) -> ExportTable:
    return ExportTable(
        title="Expense Report",
        subtitle=f"{report.date_from.isoformat()} to {report.date_to.isoformat()}",
        currency=report.currency,
        summary=[
            ("Total expenses", format_money(report.total_expense_minor, report.currency)),
            ("Transaction count", str(report.transaction_count)),
            ("Recurring expenses", format_money(report.recurring_expense_minor, report.currency)),
            (
                "Non-recurring expenses",
                format_money(report.non_recurring_expense_minor, report.currency),
            ),
        ],
        columns=[
            ExportColumn("Category", "text"),
            ExportColumn("Amount", "money"),
            ExportColumn("Percent of expenses", "percent"),
            ExportColumn("Transactions", "int"),
        ],
        rows=[
            [item.name, item.amount_minor, item.percent, item.transaction_count]
            for item in report.by_category
        ],
    )


def budget_report_table(report: BudgetReport) -> ExportTable:
    return ExportTable(
        title="Budget Report",
        subtitle="Current month",
        currency=report.currency,
        summary=[
            ("Total budgeted", format_money(report.total_budgeted_minor, report.currency)),
            ("Total spent", format_money(report.total_spent_minor, report.currency)),
            ("Budgets at risk", str(report.at_risk_count)),
            ("Budgets exceeded", str(report.exceeded_count)),
        ],
        columns=[
            ExportColumn("Category", "text"),
            ExportColumn("Budgeted", "money"),
            ExportColumn("Spent", "money"),
            ExportColumn("Remaining", "money"),
            ExportColumn("Used", "percent"),
            ExportColumn("Status", "text"),
        ],
        rows=[
            [
                item.category_name,
                item.amount_minor,
                item.spent_minor,
                item.remaining_minor,
                item.percent_used,
                item.status,
            ]
            for item in report.items
        ],
    )


def savings_report_table(report: SavingsReport) -> ExportTable:
    return ExportTable(
        title="Savings Report",
        subtitle=f"{report.date_from.isoformat()} to {report.date_to.isoformat()}",
        currency=report.currency,
        summary=[
            ("Total income", format_money(report.total_income_minor, report.currency)),
            ("Total expenses", format_money(report.total_expense_minor, report.currency)),
            ("Savings", format_money(report.savings_minor, report.currency)),
            ("Savings rate", _percent_text(report.savings_rate)),
            ("Trend", report.trend_direction.direction or "insufficient data"),
        ],
        columns=[
            ExportColumn("Month", "date"),
            ExportColumn("Income", "money"),
            ExportColumn("Expense", "money"),
            ExportColumn("Savings", "money"),
        ],
        rows=[[p.period, p.income_minor, p.expense_minor, p.savings_minor] for p in report.trend],
    )


def net_worth_report_table(report: NetWorthReport) -> ExportTable:
    return ExportTable(
        title="Net Worth Report",
        subtitle="Current accounts",
        currency=report.currency,
        summary=[
            ("Total assets", format_money(report.total_assets_minor, report.currency)),
            ("Total liabilities", format_money(report.total_liabilities_minor, report.currency)),
            ("Net worth", format_money(report.net_worth_minor, report.currency)),
        ],
        columns=[
            ExportColumn("Account", "text"),
            ExportColumn("Type", "text"),
            ExportColumn("Balance", "money"),
            ExportColumn("Liability?", "text"),
        ],
        rows=[
            [a.name, a.type, a.balance_minor, "Yes" if a.is_liability else "No"]
            for a in report.accounts
        ],
    )
