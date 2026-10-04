from app import db
from app.utils.helpers import isoformat, new_id, utcnow


class AutomationInstance(db.Model):
    """One subscriber's progress through an automation workflow."""
    __tablename__ = 'automation_instances'
    __table_args__ = (
        db.Index('idx_automation_instance_due', 'status', 'next_run_at'),
        db.Index('idx_automation_instance_sub', 'automation_id', 'subscriber_id'),
    )

    id = db.Column(db.String(36), primary_key=True, default=new_id)
    automation_id = db.Column(db.String(36), db.ForeignKey('automations.id', ondelete='CASCADE'), nullable=False)
    subscriber_id = db.Column(db.String(36), db.ForeignKey('subscribers.id', ondelete='CASCADE'), nullable=False)
    business_id = db.Column(db.String(36), db.ForeignKey('businesses.id', ondelete='CASCADE'), nullable=False)
    # Index into workflow["steps"] of the next step to execute
    current_step = db.Column(db.Integer, default=0, nullable=False)
    status = db.Column(db.String(20), nullable=False, default='active')
    next_run_at = db.Column(db.DateTime, default=utcnow)
    # Step index whose wait/delay is in progress (None when not waiting)
    waiting_step = db.Column(db.Integer)
    last_email_log_id = db.Column(db.String(36))
    history = db.Column(db.JSON, nullable=False, default=list)
    error_message = db.Column(db.Text)
    started_at = db.Column(db.DateTime, default=utcnow)
    completed_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'automation_id': self.automation_id,
            'subscriber_id': self.subscriber_id,
            'subscriber_email': self.subscriber.email if self.subscriber else None,
            'current_step': self.current_step,
            'status': self.status,
            'next_run_at': isoformat(self.next_run_at),
            'history': self.history or [],
            'error_message': self.error_message,
            'started_at': isoformat(self.started_at),
            'completed_at': isoformat(self.completed_at),
        }
