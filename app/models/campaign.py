from app import db
from app.utils.helpers import isoformat, new_id, percentage, utcnow


class Campaign(db.Model):
    __tablename__ = 'campaigns'
    __table_args__ = (
        db.Index('idx_campaign_business_status', 'business_id', 'status'),
    )

    id = db.Column(db.String(36), primary_key=True, default=new_id)
    business_id = db.Column(db.String(36), db.ForeignKey('businesses.id', ondelete='CASCADE'), nullable=False)
    template_id = db.Column(db.String(36), db.ForeignKey('email_templates.id'), nullable=False)
    segment_id = db.Column(db.String(36), db.ForeignKey('segments.id', ondelete='SET NULL'))
    name = db.Column(db.String(255), nullable=False)
    status = db.Column(db.String(20), nullable=False, default='draft')

    # Optional override of the template subject, and A/B subject variants
    subject_line = db.Column(db.String(500))
    subject_variants = db.Column(db.JSON, nullable=False, default=list)

    scheduled_time = db.Column(db.DateTime, index=True)
    send_time = db.Column(db.DateTime)
    completed_at = db.Column(db.DateTime)

    total_recipients = db.Column(db.Integer, default=0)
    total_sent = db.Column(db.Integer, default=0)
    total_opens = db.Column(db.Integer, default=0)
    total_clicks = db.Column(db.Integer, default=0)
    total_bounces = db.Column(db.Integer, default=0)
    total_unsubscribes = db.Column(db.Integer, default=0)

    created_at = db.Column(db.DateTime, default=utcnow)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow)

    template = db.relationship('EmailTemplate')
    segment = db.relationship('Segment')
    email_logs = db.relationship('EmailLog', backref='campaign', lazy='dynamic', passive_deletes=True)

    def to_dict(self):
        return {
            'id': self.id,
            'business_id': self.business_id,
            'template_id': self.template_id,
            'segment_id': self.segment_id,
            'template_name': self.template.name if self.template else None,
            'segment_name': self.segment.name if self.segment else None,
            'name': self.name,
            'status': self.status,
            'subject_line': self.subject_line,
            'subject_variants': self.subject_variants or [],
            'scheduled_time': isoformat(self.scheduled_time),
            'send_time': isoformat(self.send_time),
            'completed_at': isoformat(self.completed_at),
            'total_recipients': self.total_recipients,
            'total_sent': self.total_sent,
            'total_opens': self.total_opens,
            'total_clicks': self.total_clicks,
            'total_bounces': self.total_bounces,
            'total_unsubscribes': self.total_unsubscribes,
            'open_rate': percentage(self.total_opens or 0, self.total_sent or 0),
            'click_rate': percentage(self.total_clicks or 0, self.total_sent or 0),
            'bounce_rate': percentage(self.total_bounces or 0, self.total_sent or 0),
            'created_at': isoformat(self.created_at),
            'updated_at': isoformat(self.updated_at),
        }
