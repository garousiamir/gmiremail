"""Standalone background worker: runs all scheduled jobs in one process.

    ENABLE_SCHEDULER=False gunicorn -w 4 wsgi:app   # web
    python worker.py                                # jobs (run exactly one)
"""
import logging

from apscheduler.schedulers.blocking import BlockingScheduler

from app import create_app
from app.tasks.scheduled_tasks import build_scheduler

if __name__ == '__main__':
    app = create_app(start_scheduler=False)
    scheduler = build_scheduler(app, BlockingScheduler)
    logging.getLogger(__name__).info('Worker started with jobs: %s', [j.id for j in scheduler.get_jobs()])
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        pass
