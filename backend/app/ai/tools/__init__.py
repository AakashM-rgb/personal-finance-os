"""The fixed, allowlisted financial tool catalog the AI may call.

See app.ai.tools.catalog for the exhaustive list of the eight tools and
app.ai.tools.registry for the single choke point every tool call is
validated and executed through - nothing here ever accepts a caller-supplied
user_id or builds a database query from AI-generated text.
"""
