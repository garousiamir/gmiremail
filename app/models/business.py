from werkzeug.security import check_password_hash, generate_password_hash

from app import db
from app.utils.helpers import generate_api_key, isoformat, new_id, utcnow


class Business(db.Model):
    __tablename__ = 'businesses'

    id = db.Column(db.String(36), primary_key=True, default=new_id)
    name = db.Column(db.String(255), nullable=False)

    # Account login (the spec's JWT carries this as "email")
    account_email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    token_version = db.Column(db.Integer, default=0, nullable=False)

    # Sender identity
    email_from = db.Column(db.String(255), nullable=False)
    email_from_name = db.Column(db.String(255))
    sender_domain = db.Column(db.String(255), nullable=False)
    physical_address = db.Column(db.String(500))  # CAN-SPAM footer
    api_key = db.Column(db.String(255), unique=True, nullable=False, default=generate_api_key)

    # SMTP Configuration
    smtp_host = db.Column(db.String(255), nullable=False)
    smtp_port = db.Column(db.Integer, nullable=False)
    smtp_username = db.Column(db.String(255), nullable=False)
    smtp_password = db.Column(db.String(255), nullable=False)
    smtp_tls = db.Column(db.Boolean, default=True)

    # Rate limiting
    daily_email_limit = db.Column(db.Integer, default=10000)
    emails_sent_today = db.Column(db.Integer, default=0)

    # Timestamps
    created_at = db.Column(db.DateTime, default=utcnow)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow)

    # Relationships
    subscribers = db.relationship('Subscriber', backref='business', lazy='dynamic', cascade='all, delete-orphan')
    campaigns = db.relationship('Campaign', backref='business', lazy='dynamic', cascade='all, delete-orphan')
    templates = db.relationship('EmailTemplate', backref='business', lazy='dynamic', cascade='all, delete-orphan')
    automations = db.relationship('Automation', backref='business', lazy='dynamic', cascade='all, delete-orphan')
    segments = db.relationship('Segment', backref='business', lazy='dynamic', cascade='all, delete-orphan')
    email_logs = db.relationship('EmailLog', backref='business', lazy='dynamic', cascade='all, delete-orphan')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def remaining_daily_quota(self):
        return max((self.daily_email_limit or 0) - (self.emails_sent_today or 0), 0)

    def to_dict(self, include_api_key=True):
        data = {
            'id': self.id,
            'name': self.name,
            'account_email': self.account_email,
            'email_from': self.email_from,
            'email_from_name': self.email_from_name,
            'sender_domain': self.sender_domain,
            'physical_address': self.physical_address,
            'smtp_host': self.smtp_host,
            'smtp_port': self.smtp_port,
            'smtp_username': self.smtp_username,
            'smtp_tls': self.smtp_tls,
            'daily_email_limit': self.daily_email_limit,
            'emails_sent_today': self.emails_sent_today,
            'created_at': isoformat(self.created_at),
            'updated_at': isoformat(self.updated_at),
        }
        if include_api_key:
            data['api_key'] = self.api_key
        return data
