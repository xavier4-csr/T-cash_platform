import os
from celery import Celery
from celery.schedules import crontab

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

app = Celery('tcash')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()

# ---------------------------------------------------------------------------
# Periodic task schedule (Celery Beat)
# ---------------------------------------------------------------------------
app.conf.beat_schedule = {
    # 08:00 EAT (UTC+3) = 05:00 UTC
    'contribution-reminders-daily': {
        'task': 'notifications.tasks.send_contribution_reminders',
        'schedule': crontab(hour=5, minute=0),
    },
    # 09:00 EAT = 06:00 UTC
    'overdue-alerts-daily': {
        'task': 'notifications.tasks.send_overdue_alerts',
        'schedule': crontab(hour=6, minute=0),
    },
    # 10:00 EAT = 07:00 UTC — close stale cycles
    'mark-missed-daily': {
        'task': 'notifications.tasks.mark_missed_contributions',
        'schedule': crontab(hour=7, minute=0),
    },
    # Monday 09:00 EAT = 06:00 UTC
    'reengagement-nudges-weekly': {
        'task': 'notifications.tasks.send_reengagement_nudges',
        'schedule': crontab(day_of_week=1, hour=6, minute=0),
    },
}

app.conf.timezone = 'UTC'