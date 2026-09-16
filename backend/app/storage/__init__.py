"""Object-storage abstraction (CLAUDE.md §3/§8): every caller depends on
app.storage.base.StorageProvider, never on a specific backend. See
app.storage.factory for how the concrete implementation is selected.
"""
