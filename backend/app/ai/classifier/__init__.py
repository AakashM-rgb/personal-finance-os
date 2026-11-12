"""Narrow one-shot merchant-classification abstraction (Phase F).

Deliberately separate from app.ai.provider (the conversational Financial AI
Assistant abstraction - see app.ai's own docstring). A MerchantClassifier
answers exactly one question - "given this merchant and these category
names, which category (if any)?" - as a single request/response pair, never
a multi-turn conversation, never a tool call, never a database access.

See app.ai.classifier.base for the full architecture and the security
invariants every implementation (the mock here, a future real provider)
must uphold.
"""
