from app import db
from app.utils.helpers import isoformat, new_id, utcnow


class EmailTemplate(db.Model):
    __tablename__ = 'email_templates'
    __table_args__ = (
        db.UniqueConstraint('business_id', 'name', name='uq_template_business_name'),
    )

    id = db.Column(db.String(36), primary_key=True, default=new_id)
    business_id = db.Column(db.String(36), db.ForeignKey('businesses.id', ondelete='CASCADE'),
                            nullable=False, index=True)
    name = db.Column(db.String(255), nullable=False)
    subject_line = db.Column(db.String(500), nullable=False)
    preview_text = db.Column(db.String(255))
    html_content = db.Column(db.Text, nullable=False)
    text_content = db.Column(db.Text)
    template_variables = db.Column(db.JSON, nullable=False, default=list)
    created_at = db.Column(db.DateTime, default=utcnow)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow)

    def to_dict(self, include_content=True):
        data = {
            'id': self.id,
            'business_id': self.business_id,
            'name': self.name,
            'subject_line': self.subject_line,
            'preview_text': self.preview_text,
            'template_variables': self.template_variables or [],
            'created_at': isoformat(self.created_at),
            'updated_at': isoformat(self.updated_at),
        }
        if include_content:
            data['html_content'] = self.html_content
            data['text_content'] = self.text_content
        return data
