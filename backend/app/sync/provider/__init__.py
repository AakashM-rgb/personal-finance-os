"""Bank/Account-Aggregator sync-provider abstraction. Every provider - mock
or a real Account Aggregator client - speaks only the plain, read-only data
model in app.sync.provider.base: it can discover linked institution
accounts and pull transaction history, and nothing else. See that module's
docstring for the read-only boundary this package must never cross."""
