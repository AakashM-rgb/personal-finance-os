"""The deterministic default MerchantClassifier - used automatically
whenever no real classifier implementation is configured (today, that's
always, since Phase F1 only builds this abstraction - see
app.ai.classifier.factory). Requires no API key and never makes a network
call.

Backed by a small curated map of well-known canonical merchant names, in
the same spirit as (but deliberately NOT sharing code with)
app.services.keyword_categorization._CATEGORY_BY_KNOWN_MERCHANT - this
package must stay independent of app.services so a future real classifier
can be dropped into app.ai.classifier.factory without this module, or
anything else in app.ai.classifier, ever importing the deterministic sync
pipeline or the database.

Every returned category still passes through
app.ai.classifier.base.validate_classification, so a caller whose own
category list doesn't include "Food" gets no classification for a
recognized food-delivery merchant, never a category name that doesn't
exist for them - this mock never bypasses that check just because it
"knows" the answer.
"""

from app.ai.classifier.base import (
    MerchantClassificationRequest,
    MerchantClassificationResult,
    MerchantClassifier,
    validate_classification,
)

# Curated, small, and deliberately conservative - a deterministic stand-in
# for a real classifier's judgment, not an attempt to cover every merchant.
_KNOWN_MERCHANT_CATEGORY: dict[str, str] = {
    "Swiggy": "Food",
    "Zomato": "Food",
    "Amazon": "Shopping",
    "Flipkart": "Shopping",
    "Netflix": "Entertainment",
    "Spotify": "Entertainment",
    "Uber": "Transport",
    "Ola": "Transport",
}

# A fixed, non-random confidence for every recognized mapping above - this
# mock has no notion of "more or less sure", only "recognized" or not.
_KNOWN_MERCHANT_CONFIDENCE = 0.9


class MockMerchantClassifier:
    """A pure function of its input - holds no per-request state, so a
    single instance is safe to reuse concurrently across requests (same
    posture as app.ai.provider.mock.MockProvider). Never accesses a
    database, never calls an external API, and given the same input always
    returns the same output."""

    name = "mock"

    async def classify(
        self, request: MerchantClassificationRequest
    ) -> MerchantClassificationResult:
        category_name = _KNOWN_MERCHANT_CATEGORY.get(request.merchant)
        confidence = _KNOWN_MERCHANT_CONFIDENCE if category_name is not None else 0.0
        return validate_classification(
            category_name=category_name,
            confidence=confidence,
            category_names=request.category_names,
        )


assert isinstance(MockMerchantClassifier(), MerchantClassifier)
