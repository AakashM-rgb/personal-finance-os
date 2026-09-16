"""Financial AI Assistant module.

Architecture (never bypassed - see app.services.ai_assistant_service):

    Authenticated user
        -> AI Assistant API (app.api.v1.ai)
        -> AI orchestration service (app.services.ai_assistant_service)
        -> Controlled allowlisted financial tools (app.ai.tools)
        -> Existing authorized repositories/services
        -> Database

The AI model (app.ai.provider) never receives a database session or ORM
access, and never sees a caller-supplied user_id - every tool executes with
the user_id from the authenticated request context only.
"""
