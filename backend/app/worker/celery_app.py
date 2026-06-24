"""Celery application configuration."""

from celery import Celery
from celery.schedules import crontab

from app.core.config import settings

celery_app = Celery(
    "pixel_dream_agent",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    result_expires=3600,
    worker_prefetch_multiplier=1,
    worker_concurrency=4,
    # Bound task execution so a hung LLM call can't tie up a worker slot forever
    # (only 4 slots). The longest legit run (hourly HAWK→SAGE→proposal chain, even
    # with backoff) finishes well under the soft limit; tasks catch
    # SoftTimeLimitExceeded to mark their run failed before the hard kill.
    task_soft_time_limit=540,  # 9 min — raises SoftTimeLimitExceeded inside the task
    task_time_limit=600,  # 10 min — hard kill backstop
)

celery_app.autodiscover_tasks(["app.worker.tasks"])

celery_app.conf.beat_schedule = {
    "run-skill-trainer-daily": {
        "task": "app.worker.tasks.run_skill_trainer",
        "schedule": crontab(hour=3, minute=0),  # 3am UTC daily
    },
    "expire-trade-proposals-every-5min": {
        "task": "app.worker.tasks.expire_trade_proposals",
        "schedule": 300,
    },
    # Phase W31A — read-only W29 Watch Cron Observer. Calls HawkConditionWatch.evaluate
    # and logs the advisory posture every 15 minutes. Observer-only: it never dispatches a
    # workflow or reaches any order/risk_ack/validation_only path (see
    # app.services.w29_watch_observer). Disable via W29_WATCH_OBSERVER_ENABLED=false.
    "w29-watch-observer-every-15min": {
        "task": "app.worker.tasks.w29_watch_observer",
        "schedule": crontab(minute="*/15"),
    },
    # Phase W31E — DEMO Guarded Auto-Approval evaluator. SHIPS DISABLED: the task
    # short-circuits unless AUTO_APPROVAL_ENABLED=true, and never places an order unless
    # AUTO_APPROVAL_PLACE_ORDERS=true AND the owner-reviewed placement wiring is completed
    # (W31F). It evaluates the guarded policy read-only and logs the decision; it never
    # weakens HAWK/SAGE/kill-switch/preflight, enables LIVE, creates a risk_ack, or flips
    # validation_only. Offset to :05/:20/:35/:50 so it never collides with the observer.
    "w29-auto-approval-evaluator-every-15min": {
        "task": "app.worker.tasks.w29_auto_approval_evaluator",
        "schedule": crontab(minute="5,20,35,50"),
    },
}
