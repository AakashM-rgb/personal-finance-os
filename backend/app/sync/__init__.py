"""Automatic transaction sync abstraction. Every provider (mock or a real
Account Aggregator/bank integration) speaks only the plain, read-only data
model in app.sync.provider.base - never a database session, never a payment
or funds-movement capability of any kind. See app.models.linked_account and
app.models.sync_run for the persisted records this seam eventually feeds;
no ingestion/orchestration logic exists yet (that belongs to a later
phase's service layer)."""
