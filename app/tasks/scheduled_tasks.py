"""Background job definitions.

Run the scheduler in exactly one process. In development the web process can
host it (ENABLE_SCHEDULER=True). In production run gunicorn with
ENABLE_SCHEDULER=False and start ``python worker.py`` once, so multiple
gunicorn workers don't each run the jobs.
"""
import atexit
import logging
from datetime import timedelta

from apscheduler.schedulers.background import BackgroundScheduler

from app import db
from app.utils.helpers import utcnow

logger = logging.getLogger(__name__)

_scheduler = None


def _job(app, func):
    """Run a job inside an app context and never let it crash the scheduler."""
    def run():
        with app.app_context():
            try:
                return func()
            except Exception:  # noqa: BLE001
                db.session.rollback()
                logger.exception('Background job %s failed', func.__name__)
            finally:
                db.session.remove()
    run.__name__ = func.__name__
    return run


# ------------------------------------------------------------------- jobs

def process_email_queue():
    from app.services import campaign_service, email_service
    campaign_service.dispatch_due_campaigns()
    summary = email_service.process_email_queue()
    if summary['claimed']:
        logger.info('Email queue: %s', summary)
    return summary


def execute_pending_automations():
    from app.services import automation_service
    return automation_service.execute_pending_automations()


def calculate_analytics():
    from app.services import analytics_service
    return analytics_service.calculate_analytics()


def process_bounces():
    """Deactivate repeat soft-bouncers and close out messages that failed."""
    from flask import current_app

    from app.models import EmailLog, Subscriber
    from app.services.subscriber_service import _apply_status

    threshold = current_app.config['MAX_SOFT_BOUNCES']
    repeat_bouncers = Subscriber.query.filter(Subscriber.status == 'active',
                                              Subscriber.bounce_count >= threshold).all()
    for subscriber in repeat_bouncers:
        _apply_status(subscriber, 'bounced')
    # Pending mail to subscribers that are no longer active will never be sent
    inactive = db.select(Subscriber.id).where(Subscriber.status != 'active')
    dropped = EmailLog.query.filter(EmailLog.status == 'pending', EmailLog.subscriber_id.in_(inactive)).update(
        {'status': 'failed', 'error_message': 'Subscriber no longer active', 'next_attempt_at': None},
        synchronize_session=False)
    db.session.commit()
    return {'deactivated': len(repeat_bouncers), 'dropped': dropped}


def cleanup_old_data():
    """Delete old tracking events / logs past retention; full analytics refresh."""
    from flask import current_app

    from app.models import AutomationInstance, EmailEvent, EmailLog
    from app.services import analytics_service, segment_service

    cutoff = utcnow() - timedelta(days=current_app.config['EMAIL_LOG_RETENTION_DAYS'])
    events = EmailEvent.query.filter(EmailEvent.created_at < cutoff).delete(synchronize_session=False)
    old_logs = db.select(EmailLog.id).where(EmailLog.created_at < cutoff,
                                            EmailLog.status.notin_(['pending', 'sending']))
    EmailEvent.query.filter(EmailEvent.email_log_id.in_(old_logs)).delete(synchronize_session=False)
    logs = EmailLog.query.filter(EmailLog.id.in_(old_logs)).delete(synchronize_session=False)
    instances = AutomationInstance.query.filter(AutomationInstance.status.in_(['completed', 'failed']),
                                                AutomationInstance.completed_at < cutoff) \
        .delete(synchronize_session=False)
    db.session.commit()
    analytics_service.calculate_analytics(full=True)
    segment_service.refresh_all_counts()
    result = {'events': events, 'email_logs': logs, 'automation_instances': instances}
    logger.info('Cleanup: %s', result)
    return result


def reset_daily_limits():
    from app.models import Business
    count = Business.query.update({'emails_sent_today': 0}, synchronize_session=False)
    db.session.commit()
    return count


# -------------------------------------------------------------- scheduler

def build_scheduler(app, scheduler_class=BackgroundScheduler):
    scheduler = scheduler_class(timezone='UTC', job_defaults={'coalesce': True, 'max_instances': 1})
    scheduler.add_job(_job(app, process_email_queue), 'interval',
                      seconds=app.config['QUEUE_PROCESSING_INTERVAL'], id='email_queue_processor')
    scheduler.add_job(_job(app, execute_pending_automations), 'interval', seconds=30, id='automation_executor')
    scheduler.add_job(_job(app, calculate_analytics), 'interval', minutes=5, id='analytics_calculator')
    scheduler.add_job(_job(app, process_bounces), 'interval', hours=1, id='bounce_processor')
    scheduler.add_job(_job(app, cleanup_old_data), 'cron', hour=2, minute=0, id='daily_cleanup')
    scheduler.add_job(_job(app, reset_daily_limits), 'cron', hour=0, minute=0, id='reset_daily_limits')
    return scheduler


def init_scheduler(app):
    global _scheduler
    if _scheduler is not None:
        return _scheduler
    _scheduler = build_scheduler(app)
    _scheduler.start()
    atexit.register(lambda: _scheduler.shutdown(wait=False))
    logger.info('Background scheduler started')
    return _scheduler
