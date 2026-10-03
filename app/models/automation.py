from app import db
from app.utils.helpers import isoformat, new_id, utcnow


class Automation(db.Model):
    __tablename__ = 'automations'
    __table_args__ = (
        db.Index('idx_automation_business_trigger', 'business_id', 'trigger_type', 'status'),
    )

    id = db.Column(db.String(36), primary_key=True, default=new_id)
    business_id = db.Column(db.String(36), db.ForeignKey('businesses.id', ondelete='CASCADE'), nullable=False)
    name = db.Column(db.String(255), nullable=False)
    trigger_type = db.Column(db.String(30), nullable=False)
    trigger_value = db.Column(db.String(255))
    status = db.Column(db.String(20), nullable=False, default='active')
    workflow = db.Column(db.JSON, nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow)

    instances = db.relationship('AutomationInstance', backref='automation', lazy='dynamic',
                                cascade='all, delete-orphan')

    def to_dict(self, include_stats=False):
        data = {
            'id': self.id,
            'business_id': self.business_id,
            'name': self.name,
            'trigger_type': self.trigger_type,
            'trigger_value': self.trigger_value,
            'status': self.status,
            'workflow': self.workflow,
            'created_at': isoformat(self.created_at),
            'updated_at': isoformat(self.updated_at),
        }
        if include_stats:
            from app.models.automation_instance import AutomationInstance
            counts = dict(
                db.session.query(AutomationInstance.status, db.func.count(AutomationInstance.id))
                .filter(AutomationInstance.automation_id == self.id)
                .group_by(AutomationInstance.status).all()
            )
            data['instances'] = {
                'active': counts.get('active', 0),
                'completed': counts.get('completed', 0),
                'paused': counts.get('paused', 0),
                'failed': counts.get('failed', 0),
            }
        return data
