from app import db
from app.utils.helpers import isoformat, new_id, utcnow


class EmailLog(db.Model):
    """One outgoing message (campaign or automation) and its delivery state."""
    __tablename__ = 'email_logs'
    __table_args__ = (
        db.Index('idx_email_log_business_campaign', 'business_id', 'campaign_id'),
        db.Index('idx_email_log_subscriber_status', 'subscriber_id', 'status'),
        db.Index('idx_email_log_status_next_attempt', 'status', 'next_attempt_at'),
    )

    id = db.Column(db.String(36), primary_key=True, default=new_id)
    business_id = db.Column(db.String(36), db.ForeignKey('businesses.id', ondelete='CASCADE'), nullable=False)
    campaign_id = db.Column(db.String(36), db.ForeignKey('campaigns.id', ondelete='CASCADE'))
    automation_id = db.Column(db.String(36), db.ForeignKey('automations.id', ondelete='SET NULL'))
    template_id = db.Column(db.String(36), db.ForeignKey('email_templates.id', ondelete='SET NULL'))
    subscriber_id = db.Column(db.String(36), db.ForeignKey('subscribers.id', ondelete='CASCADE'), nullable=False)
    recipient_email = db.Column(db.String(255), nullable=False)
    subject_line = db.Column(db.String(500))
    subject_variant = db.Column(db.Integer)  # index into campaign.subject_variants (A/B)
    status = db.Column(db.String(20), nullable=False, default='pending')

    # Delivery / retry
    attempts = db.Column(db.Integer, default=0, nullable=False)
    next_attempt_at = db.Column(db.DateTime, default=utcnow)
    message_id = db.Column(db.String(255))
    bounce_type = db.Column(db.String(10))  # 'hard' | 'soft'
    error_message = db.Column(db.Text)

    # Engagement
    open_count = db.Column(db.Integer, default=0, nullable=False)
    click_count = db.Column(db.Integer, default=0, nullable=False)

    sent_at = db.Column(db.DateTime, index=True)
    opened_at = db.Column(db.DateTime)
    clicked_at = db.Column(db.DateTime)
    bounced_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=utcnow)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow)

    events = db.relationship('EmailEvent', backref='email_log', lazy='dynamic', cascade='all, delete-orphan')

    def to_dict(self):
        return {
            'id': self.id,
            'business_id': self.business_id,
            'campaign_id': self.campaign_id,
            'automation_id': self.automation_id,
            'template_id': self.template_id,
            'subscriber_id': self.subscriber_id,
            'recipient_email': self.recipient_email,
            'subject_line': self.subject_line,
            'subject_variant': self.subject_variant,
            'status': self.status,
            'attempts': self.attempts,
            'bounce_type': self.bounce_type,
            'error_message': self.error_message,
            'open_count': self.open_count,
            'click_count': self.click_count,
            'sent_at': isoformat(self.sent_at),
            'opened_at': isoformat(self.opened_at),
            'clicked_at': isoformat(self.clicked_at),
            'bounced_at': isoformat(self.bounced_at),
            'created_at': isoformat(self.created_at),
        }


class EmailEvent(db.Model):
    """Raw open/click/unsubscribe events: powers link stats and open timing."""
    __tablename__ = 'email_events'
    __table_args__ = (
        db.Index('idx_email_event_business_type', 'business_id', 'event_type', 'created_at'),
    )

    id = db.Column(db.String(36), primary_key=True, default=new_id)
    business_id = db.Column(db.String(36), db.ForeignKey('businesses.id', ondelete='CASCADE'), nullable=False)
    email_log_id = db.Column(db.String(36), db.ForeignKey('email_logs.id', ondelete='CASCADE'),
                             nullable=False, index=True)
    campaign_id = db.Column(db.String(36), index=True)
    subscriber_id = db.Column(db.String(36), index=True)
    event_type = db.Column(db.String(20), nullable=False)  # open | click | unsubscribe
    url = db.Column(db.Text)
    user_agent = db.Column(db.String(500))
    ip_address = db.Column(db.String(64))
    created_at = db.Column(db.DateTime, default=utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'email_log_id': self.email_log_id,
            'campaign_id': self.campaign_id,
            'subscriber_id': self.subscriber_id,
            'event_type': self.event_type,
            'url': self.url,
            'created_at': isoformat(self.created_at),
        }
