"""The development/mock OCR provider - used whenever no external OCR
service is configured (see app.ocr.factory). It is NOT a simulation of a
real OCR/ML engine and never pretends to be one:

- For a PDF, it extracts the file's REAL embedded text (via pypdf) and
  runs the deterministic, documented heuristics in
  app.ocr.text_extraction over it. Every value returned was genuinely
  read from the file's own text - nothing is invented.
- For an image (JPG/PNG), there is no real OCR engine wired up in this
  environment, and CLAUDE.md/PRODUCT_SPEC deliberately keep external
  OCR optional - so this provider honestly returns no extracted values
  at all (confidence 0.0) rather than fabricate a guess. The human
  review screen (Part 6) still works normally: the user fills in every
  field themselves.

`provider` on the result is always "mock" - never a real vendor name -
so nothing downstream can mistake this for a real external call.
"""

import io

from app.ocr.base import OcrExtractionResult
from app.ocr.text_extraction import (
    extract_date,
    extract_items,
    extract_merchant,
    extract_tax_minor,
    extract_total_minor,
)

_PROVIDER_NAME = "mock"


def _extract_pdf_text(file_bytes: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(file_bytes))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def _confidence(
    *, merchant_found: bool, date_found: bool, total_found: bool, tax_found: bool
) -> float:
    """A simple, documented heuristic - the fraction of the fields this
    provider looks for that it actually found, weighting the total (the
    single most important field for a receipt) twice - never a fabricated
    machine-learning-style score."""
    weights = [
        (merchant_found, 1),
        (date_found, 1),
        (total_found, 2),
        (tax_found, 1),
    ]
    total_weight = sum(w for _, w in weights)
    achieved = sum(w for found, w in weights if found)
    return round(achieved / total_weight, 2)


class MockOcrProvider:
    """Category suggestion is deliberately NOT computed here - see
    app.ocr.category_suggestion, called by app.services.receipt_service
    with the caller's real category list, since a provider has no
    business knowing which categories exist for a given user."""

    async def extract(self, *, file_bytes: bytes, content_type: str) -> OcrExtractionResult:
        if content_type != "application/pdf":
            # Honest "nothing extracted" - no real OCR engine is wired up
            # for images in this environment; see the module docstring.
            return OcrExtractionResult(provider=_PROVIDER_NAME, confidence=0.0)

        try:
            text = _extract_pdf_text(file_bytes)
        except Exception as exc:  # noqa: BLE001 - any parse failure is a clean "failed", not a crash
            return OcrExtractionResult(provider=_PROVIDER_NAME, error=f"Could not read PDF: {exc}")

        lines = [line for line in text.splitlines() if line.strip()]

        merchant = extract_merchant(lines)
        occurred_on = extract_date(text)
        total_minor = extract_total_minor(lines)
        tax_minor = extract_tax_minor(lines)
        items = extract_items(lines)

        return OcrExtractionResult(
            provider=_PROVIDER_NAME,
            merchant=merchant,
            occurred_on=occurred_on,
            total_minor=total_minor,
            tax_minor=tax_minor,
            items=items,
            confidence=_confidence(
                merchant_found=merchant is not None,
                date_found=occurred_on is not None,
                total_found=total_minor is not None,
                tax_found=tax_minor is not None,
            ),
        )
