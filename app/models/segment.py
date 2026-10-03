from app import db
from app.utils.helpers import isoformat, new_id, utcnow


class Segment(db.Model):
    __tablename__ = 'segments'
    __table_args__ = (
        db.UniqueConstraint('business_id', 'name', name='uq_segment_business_name'),
    )

    id = db.Column(db.String(36), primary_key=True, default=new_id)
    business_id = db.Column(db.String(36), db.ForeignKey('businesses.id', ondelete='CASCADE'),
                            nullable=False, index=True)
    name = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text)
    filter_rules = db.Column(db.JSON, nullable=False)
    subscriber_count = db.Column(db.Integer, default=0)
    count_updated_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=utcnow)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'business_id': self.business_id,
            'name': self.name,
            'description': self.description,
            'filter_rules': self.filter_rules,
            'subscriber_count': self.subscriber_count,
            'count_updated_at': isoformat(self.count_updated_at),
            'created_at': isoformat(self.created_at),
            'updated_at': isoformat(self.updated_at),
        }
