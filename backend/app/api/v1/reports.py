"""Report endpoints. Every route is authenticated and scoped to the
caller's own data via app.services.report_service. The `/export`
sub-routes render the exact same report data as the JSON routes above
them into a real CSV/Excel/PDF file (see app.services.export_service and
app.services.report_export_service) - never a second, divergent copy of
the numbers."""

from datetime import date

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.services import report_export_service, report_service
from app.services.analytics_calculations import AnalyticsRangePreset
from app.services.export_service import CONTENT_TYPES, ExportFormat, ExportTable, render

router = APIRouter(prefix="/reports", tags=["reports"])


def _export_response(
    table: ExportTable, export_format: ExportFormat, filename_base: str
) -> Response:
    content = render(table, export_format)
    return Response(
        content=content,
        media_type=CONTENT_TYPES[export_format],
        headers={"Content-Disposition": f'attachment; filename="{filename_base}.{export_format}"'},
    )


@router.get("/monthly", response_model=None)
async def get_monthly_report(
    year: int = Query(..., ge=1900, le=3000),
    month: int = Query(..., ge=1, le=12),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    report = await report_service.get_monthly_report(
        db, user_id=current_user.id, year=year, month=month
    )
    return {"data": report, "error": None, "meta": None}


@router.get("/yearly", response_model=None)
async def get_yearly_report(
    year: int = Query(..., ge=1900, le=3000),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    report = await report_service.get_yearly_report(db, user_id=current_user.id, year=year)
    return {"data": report, "error": None, "meta": None}


@router.get("/category", response_model=None)
async def get_category_report(
    range: AnalyticsRangePreset = AnalyticsRangePreset.CURRENT_MONTH,  # noqa: A002
    custom_from: date | None = None,
    custom_to: date | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    report = await report_service.get_category_report(
        db,
        user_id=current_user.id,
        range_preset=range,
        custom_from=custom_from,
        custom_to=custom_to,
    )
    return {"data": report, "error": None, "meta": None}


@router.get("/income", response_model=None)
async def get_income_report(
    range: AnalyticsRangePreset = AnalyticsRangePreset.CURRENT_MONTH,  # noqa: A002
    custom_from: date | None = None,
    custom_to: date | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    report = await report_service.get_income_report(
        db,
        user_id=current_user.id,
        range_preset=range,
        custom_from=custom_from,
        custom_to=custom_to,
    )
    return {"data": report, "error": None, "meta": None}


@router.get("/expense", response_model=None)
async def get_expense_report(
    range: AnalyticsRangePreset = AnalyticsRangePreset.CURRENT_MONTH,  # noqa: A002
    custom_from: date | None = None,
    custom_to: date | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    report = await report_service.get_expense_report(
        db,
        user_id=current_user.id,
        range_preset=range,
        custom_from=custom_from,
        custom_to=custom_to,
    )
    return {"data": report, "error": None, "meta": None}


@router.get("/budget", response_model=None)
async def get_budget_report(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    report = await report_service.get_budget_report(db, user_id=current_user.id)
    return {"data": report, "error": None, "meta": None}


@router.get("/savings", response_model=None)
async def get_savings_report(
    range: AnalyticsRangePreset = AnalyticsRangePreset.CURRENT_MONTH,  # noqa: A002
    custom_from: date | None = None,
    custom_to: date | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    report = await report_service.get_savings_report(
        db,
        user_id=current_user.id,
        range_preset=range,
        custom_from=custom_from,
        custom_to=custom_to,
    )
    return {"data": report, "error": None, "meta": None}


@router.get("/net-worth", response_model=None)
async def get_net_worth_report(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    report = await report_service.get_net_worth_report(db, user_id=current_user.id)
    return {"data": report, "error": None, "meta": None}


# --- exports --------------------------------------------------------------------------


@router.get("/monthly/export")
async def export_monthly_report(
    format: ExportFormat,  # noqa: A002
    year: int = Query(..., ge=1900, le=3000),
    month: int = Query(..., ge=1, le=12),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    report = await report_service.get_monthly_report(
        db, user_id=current_user.id, year=year, month=month
    )
    table = report_export_service.monthly_report_table(report)
    return _export_response(table, format, f"monthly-report-{year}-{month:02d}")


@router.get("/yearly/export")
async def export_yearly_report(
    format: ExportFormat,  # noqa: A002
    year: int = Query(..., ge=1900, le=3000),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    report = await report_service.get_yearly_report(db, user_id=current_user.id, year=year)
    table = report_export_service.yearly_report_table(report)
    return _export_response(table, format, f"yearly-report-{year}")


@router.get("/category/export")
async def export_category_report(
    format: ExportFormat,  # noqa: A002
    range: AnalyticsRangePreset = AnalyticsRangePreset.CURRENT_MONTH,  # noqa: A002
    custom_from: date | None = None,
    custom_to: date | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    report = await report_service.get_category_report(
        db,
        user_id=current_user.id,
        range_preset=range,
        custom_from=custom_from,
        custom_to=custom_to,
    )
    table = report_export_service.category_report_table(report)
    return _export_response(table, format, "category-report")


@router.get("/income/export")
async def export_income_report(
    format: ExportFormat,  # noqa: A002
    range: AnalyticsRangePreset = AnalyticsRangePreset.CURRENT_MONTH,  # noqa: A002
    custom_from: date | None = None,
    custom_to: date | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    report = await report_service.get_income_report(
        db,
        user_id=current_user.id,
        range_preset=range,
        custom_from=custom_from,
        custom_to=custom_to,
    )
    table = report_export_service.income_report_table(report)
    return _export_response(table, format, "income-report")


@router.get("/expense/export")
async def export_expense_report(
    format: ExportFormat,  # noqa: A002
    range: AnalyticsRangePreset = AnalyticsRangePreset.CURRENT_MONTH,  # noqa: A002
    custom_from: date | None = None,
    custom_to: date | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    report = await report_service.get_expense_report(
        db,
        user_id=current_user.id,
        range_preset=range,
        custom_from=custom_from,
        custom_to=custom_to,
    )
    table = report_export_service.expense_report_table(report)
    return _export_response(table, format, "expense-report")


@router.get("/budget/export")
async def export_budget_report(
    format: ExportFormat,  # noqa: A002
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    report = await report_service.get_budget_report(db, user_id=current_user.id)
    table = report_export_service.budget_report_table(report)
    return _export_response(table, format, "budget-report")


@router.get("/savings/export")
async def export_savings_report(
    format: ExportFormat,  # noqa: A002
    range: AnalyticsRangePreset = AnalyticsRangePreset.CURRENT_MONTH,  # noqa: A002
    custom_from: date | None = None,
    custom_to: date | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    report = await report_service.get_savings_report(
        db,
        user_id=current_user.id,
        range_preset=range,
        custom_from=custom_from,
        custom_to=custom_to,
    )
    table = report_export_service.savings_report_table(report)
    return _export_response(table, format, "savings-report")


@router.get("/net-worth/export")
async def export_net_worth_report(
    format: ExportFormat,  # noqa: A002
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    report = await report_service.get_net_worth_report(db, user_id=current_user.id)
    table = report_export_service.net_worth_report_table(report)
    return _export_response(table, format, "net-worth-report")
