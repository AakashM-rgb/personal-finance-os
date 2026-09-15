"""Background-work entry points (CLAUDE.md §8): the seam a real job
runner calls into, so business logic never lives inline in a request
handler. In dev, nothing schedules these automatically - there is no
Celery/RQ worker or APScheduler provisioned in this project yet, and
CLAUDE.md's "never hard-depend on infra that isn't actually provisioned"
means that wiring isn't added speculatively. Each job function here is
directly callable (by a test, or by a manual "generate now" API route)
and is exactly what a production scheduler would call on a timer.
"""
