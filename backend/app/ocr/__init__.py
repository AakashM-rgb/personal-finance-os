"""OCR provider abstraction (CLAUDE.md §3/§8): every caller depends on
app.ocr.base.OcrProvider, never on a specific vendor. See app.ocr.factory
for how the concrete implementation is selected, and app.ocr.mock for the
always-available development/mock provider.
"""
