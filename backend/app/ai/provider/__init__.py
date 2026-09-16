"""AI provider abstraction. Every provider (mock or a real vendor) speaks
only the plain conversational data model in app.ai.provider.base - never a
database session, never raw SQL, never anything about the user beyond the
conversation text and the tool results app.services.ai_assistant_service
already fetched through the validated tool layer (app.ai.tools)."""
