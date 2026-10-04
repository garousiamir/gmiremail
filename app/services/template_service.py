"""Email template CRUD and rendering.

Templates are written by tenants, so they are rendered in a Jinja2 *sandbox*
(no access to Python internals) with HTML autoescaping of variable values.
"""
import re

from jinja2 import TemplateError, meta
from jinja2.sandbox import SandboxedEnvironment

from app import db
from app.models import Campaign, EmailTemplate
from app.utils.helpers import NotFoundError, ServiceError

_html_env = SandboxedEnvironment(autoescape=True)
_text_env = SandboxedEnvironment(autoescape=False)

# Variables injected by the platform at send time
SYSTEM_VARIABLES = {'unsubscribe_url', 'business_name', 'physical_address', 'preview_text', 'tracking_pixel'}

DEFAULT_SAMPLE_DATA = {
    'first_name': 'Jane',
    'last_name': 'Doe',
    'full_name': 'Jane Doe',
    'email': 'jane.doe@example.com',
    'unsubscribe_url': '#unsubscribe',
    'business_name': 'Your Business',
    'physical_address': '123 Main Street, Springfield',
}


def _base_layout(body):
    return (
        '<!DOCTYPE html>\n<html lang="en">\n<head>\n'
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        '<meta name="color-scheme" content="light dark">\n'
        '<meta name="supported-color-schemes" content="light dark">\n'
        '<style>\n'
        '  body { margin:0; padding:0; background:#f4f4f5; font-family:Arial,Helvetica,sans-serif; color:#18181b; }\n'
        '  .container { max-width:600px; margin:0 auto; background:#ffffff; padding:32px 24px; }\n'
        '  .btn { display:inline-block; padding:12px 24px; background:#2563eb; color:#ffffff !important;'
        ' text-decoration:none; border-radius:6px; }\n'
        '  .footer { max-width:600px; margin:0 auto; padding:16px 24px; font-size:12px; color:#71717a; }\n'
        '  @media (max-width:620px) { .container { padding:24px 16px; } }\n'
        '  @media (prefers-color-scheme: dark) {\n'
        '    body { background:#18181b !important; color:#f4f4f5 !important; }\n'
        '    .container { background:#27272a !important; }\n'
        '  }\n'
        '</style>\n</head>\n<body>\n'
        '<span style="display:none;max-height:0;overflow:hidden;">{{ preview_text }}</span>\n'
        f'<div class="container">\n{body}\n</div>\n'
        '<div class="footer">{{ business_name }} &middot; {{ physical_address }}<br>'
        '<a href="{{ unsubscribe_url }}">Unsubscribe</a></div>\n'
        '</body>\n</html>'
    )


TEMPLATE_LIBRARY = {
    'welcome': {
        'name': 'Welcome Email',
        'subject_line': 'Welcome, {{ first_name or "friend" }}!',
        'preview_text': 'Thanks for joining us',
        'html_content': _base_layout(
            '<h1>Welcome{% if first_name %}, {{ first_name }}{% endif %}!</h1>\n'
            '<p>Thanks for subscribing. We are glad to have you with us.</p>\n'
            '<p><a class="btn" href="https://example.com">Get started</a></p>'
        ),
        'text_content': 'Welcome {{ first_name }}!\n\nThanks for subscribing.\n\n'
                        'Unsubscribe: {{ unsubscribe_url }}',
    },
    'newsletter': {
        'name': 'Newsletter',
        'subject_line': 'This week at {{ business_name }}',
        'preview_text': 'The latest news and updates',
        'html_content': _base_layout(
            '<h1>Hi {{ first_name or "there" }},</h1>\n'
            '<p>Here is what is new this week.</p>\n'
            '<h2>Headline story</h2>\n<p>Write your story here.</p>\n'
            '<p><a class="btn" href="https://example.com/blog">Read more</a></p>'
        ),
        'text_content': 'Hi {{ first_name }},\n\nHere is what is new this week.\n\n'
                        'Unsubscribe: {{ unsubscribe_url }}',
    },
    'promotion': {
        'name': 'Promotion',
        'subject_line': '{{ first_name }}, a special offer just for you',
        'preview_text': 'Limited time only',
        'html_content': _base_layout(
            '<h1>Save 20% today</h1>\n'
            '<p>Hi {{ first_name or "there" }}, use code <strong>SAVE20</strong> at checkout.</p>\n'
            '<p><a class="btn" href="https://example.com/shop">Shop now</a></p>'
        ),
        'text_content': 'Save 20% today with code SAVE20.\n\nUnsubscribe: {{ unsubscribe_url }}',
    },
}


# ------------------------------------------------------------------ helpers

def _parse_variables(*sources):
    variables = set()
    for source in sources:
        if not source:
            continue
        try:
            variables |= meta.find_undeclared_variables(_html_env.parse(source))
        except TemplateError as exc:
            raise ServiceError('Template syntax error', details=str(exc))
    return sorted(variables - SYSTEM_VARIABLES)


def extract_variables(subject, html, text=None):
    return _parse_variables(subject, html, text)


def render_string(source, variables, html=False):
    if not source:
        return ''
    env = _html_env if html else _text_env
    try:
        return env.from_string(source).render(**variables)
    except TemplateError as exc:
        raise ServiceError('Template rendering failed', details=str(exc))


def html_to_text(html):
    text = re.sub(r'(?is)<(script|style).*?</\1>', '', html or '')
    text = re.sub(r'(?i)<br\s*/?>|</p>|</h[1-6]>|</div>|</li>', '\n', text)
    text = re.sub(r'(?s)<[^>]+>', '', text)
    text = re.sub(r'&nbsp;', ' ', text)
    text = re.sub(r'[ \t]+', ' ', text)
    return re.sub(r'\n\s*\n+', '\n\n', text).strip()


def render_template(template, variables=None, subject_override=None):
    """Render a template; returns dict(subject, html, text, preview_text)."""
    variables = dict(variables or {})
    variables.setdefault('preview_text', template.preview_text or '')
    subject = render_string(subject_override or template.subject_line, variables).strip()
    html = render_string(template.html_content, variables, html=True)
    text = render_string(template.text_content, variables) if template.text_content else html_to_text(html)
    return {
        'subject': subject,
        'html': html,
        'text': text,
        'preview_text': render_string(template.preview_text or '', variables),
    }


# --------------------------------------------------------------------- CRUD

def get_template(business_id, template_id):
    template = EmailTemplate.query.filter_by(id=template_id, business_id=business_id).first()
    if template is None:
        raise NotFoundError('Template')
    return template


def list_templates(business_id, search=None):
    query = EmailTemplate.query.filter_by(business_id=business_id)
    if search:
        query = query.filter(EmailTemplate.name.ilike(f'%{search}%'))
    return query.order_by(EmailTemplate.created_at.desc())


def create_template(business_id, name, subject, html, text=None, preview_text=None, variables=None):
    if not name or not subject or not html:
        raise ServiceError('name, subject_line and html_content are required')
    if EmailTemplate.query.filter_by(business_id=business_id, name=name).first():
        raise ServiceError('A template with this name already exists', 409)
    detected = extract_variables(subject, html, text)
    template = EmailTemplate(
        business_id=business_id, name=name, subject_line=subject, html_content=html,
        text_content=text, preview_text=preview_text,
        template_variables=sorted(set(detected) | set(variables or [])),
    )
    db.session.add(template)
    db.session.commit()
    return template


def update_template(business_id, template_id, data):
    template = get_template(business_id, template_id)
    if 'name' in data and data['name'] != template.name:
        if not data['name']:
            raise ServiceError('Template name is required')
        if EmailTemplate.query.filter_by(business_id=business_id, name=data['name']).first():
            raise ServiceError('A template with this name already exists', 409)
        template.name = data['name']
    for field in ('subject_line', 'html_content'):
        if field in data:
            if not data[field]:
                raise ServiceError(f'{field} cannot be empty')
            setattr(template, field, data[field])
    for field in ('text_content', 'preview_text'):
        if field in data:
            setattr(template, field, data[field])
    detected = extract_variables(template.subject_line, template.html_content, template.text_content)
    template.template_variables = sorted(set(detected) | set(data.get('template_variables') or []))
    db.session.commit()
    return template


def delete_template(business_id, template_id):
    template = get_template(business_id, template_id)
    if Campaign.query.filter_by(template_id=template.id).count():
        raise ServiceError('Template is used by one or more campaigns', 409)
    db.session.delete(template)
    db.session.commit()


def preview_template(business_id, template_id, sample_data=None):
    from app.models import Business
    template = get_template(business_id, template_id)
    business = db.session.get(Business, business_id)
    variables = dict(DEFAULT_SAMPLE_DATA)
    variables['business_name'] = business.name
    variables['physical_address'] = business.physical_address or ''
    variables.update(sample_data or {})
    rendered = render_template(template, variables)
    rendered['template_variables'] = template.template_variables or []
    return rendered


def preview_content(business_id, data):
    """Render unsaved template content (live editor preview)."""
    from app.models import Business
    business = db.session.get(Business, business_id)
    template = EmailTemplate(
        subject_line=data.get('subject_line') or '', html_content=data.get('html_content') or '',
        text_content=data.get('text_content') or None, preview_text=data.get('preview_text') or '',
    )
    variables = dict(DEFAULT_SAMPLE_DATA)
    variables['business_name'] = business.name
    variables['physical_address'] = business.physical_address or ''
    variables.update(data.get('sample_data') or {})
    rendered = render_template(template, variables)
    rendered['template_variables'] = extract_variables(template.subject_line, template.html_content,
                                                       template.text_content)
    return rendered


def create_from_library(business_id, key, name=None):
    entry = TEMPLATE_LIBRARY.get(key)
    if entry is None:
        raise NotFoundError('Library template')
    return create_template(
        business_id, name or entry['name'], entry['subject_line'], entry['html_content'],
        text=entry['text_content'], preview_text=entry['preview_text'],
    )


def library():
    return [
        {'key': key, 'name': entry['name'], 'subject_line': entry['subject_line'],
         'preview_text': entry['preview_text'], 'html_content': entry['html_content'],
         'text_content': entry['text_content']}
        for key, entry in TEMPLATE_LIBRARY.items()
    ]
