from app import db
from app.utils.helpers import isoformat, new_id, utcnow


class Subscriber(db.Model):
    __tablename__ = 'subscribers'
    __table_args__ = (
        db.UniqueConstraint('business_id', 'email', name='uq_subscriber_business_email'),
        db.Index('idx_subscriber_business_status', 'business_id', 'status'),
    )

    id = db.Column(db.String(36), primary_key=True, default=new_id)
    business_id = db.Column(db.String(36), db.ForeignKey('businesses.id', ondelete='CASCADE'), nullable=False)
    email = db.Column(db.String(255), nullable=False, index=True)
    first_name = db.Column(db.String(255))
    last_name = db.Column(db.String(255))
    status = db.Column(db.String(20), nullable=False, default='active')
    custom_fields = db.Column(db.JSON, nullable=False, default=dict)
    tags = db.Column(db.JSON, nullable=False, default=list)

    # Engagement (maintained by tracking + analytics jobs)
    total_opens = db.Column(db.Integer, default=0, nullable=False)
    total_clicks = db.Column(db.Integer, default=0, nullable=False)
    last_opened_at = db.Column(db.DateTime)
    last_clicked_at = db.Column(db.DateTime)
    engagement_score = db.Column(db.Float, default=0.0, nullable=False)
    bounce_count = db.Column(db.Integer, default=0, nullable=False)

    subscribed_at = db.Column(db.DateTime, default=utcnow)
    unsubscribed_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=utcnow)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow)

    email_logs = db.relationship('EmailLog', backref='subscriber', lazy='dynamic', cascade='all, delete-orphan')
    automation_instances = db.relationship('AutomationInstance', backref='subscriber', lazy='dynamic',
                                           cascade='all, delete-orphan')

    @property
    def full_name(self):
        return ' '.join(p for p in (self.first_name, self.last_name) if p)

    def to_dict(self):
        return {
            'id': self.id,
            'business_id': self.business_id,
            'email': self.email,
            'first_name': self.first_name,
            'last_name': self.last_name,
            'status': self.status,
            'custom_fields': self.custom_fields or {},
            'tags': self.tags or [],
            'total_opens': self.total_opens,
            'total_clicks': self.total_clicks,
            'last_opened_at': isoformat(self.last_opened_at),
            'last_clicked_at': isoformat(self.last_clicked_at),
            'engagement_score': self.engagement_score,
            'bounce_count': self.bounce_count,
            'subscribed_at': isoformat(self.subscribed_at),
            'unsubscribed_at': isoformat(self.unsubscribed_at),
            'created_at': isoformat(self.created_at),
            'updated_at': isoformat(self.updated_at),
        }

    def template_context(self):
        """Variables available to email templates for this subscriber."""
        context = dict(self.custom_fields or {})
        context.update({
            'email': self.email,
            'first_name': self.first_name or '',
            'last_name': self.last_name or '',
            'full_name': self.full_name,
        })
        return context
