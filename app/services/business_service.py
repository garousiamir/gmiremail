from app import db
from app.models import Business
from app.utils.constants import BUSINESS_UPDATABLE_FIELDS
from app.utils.helpers import ServiceError, generate_api_key
from app.utils.validators import normalize_email, require_fields, validate_password, validate_port


def register_business(data):
    require_fields(data, 'name', 'email', 'password')
    email = normalize_email(data['email'])
    validate_password(data['password'])
    if Business.query.filter_by(account_email=email).first():
        raise ServiceError('An account with this email already exists', 409)

    from flask import current_app
    email_from = normalize_email(data.get('email_from') or email)
    business = Business(
        name=data['name'].strip(),
        account_email=email,
        email_from=email_from,
        email_from_name=data.get('email_from_name') or data['name'].strip(),
        sender_domain=(data.get('sender_domain') or email_from.split('@', 1)[1]).lower(),
        physical_address=data.get('physical_address'),
        smtp_host=data.get('smtp_host') or current_app.config['SMTP_HOST'],
        smtp_port=validate_port(data.get('smtp_port') or current_app.config['SMTP_PORT']),
        smtp_username=data['smtp_username'] if 'smtp_username' in data else email_from,  # '' = no AUTH
        smtp_password=data.get('smtp_password') or '',
        smtp_tls=bool(data.get('smtp_tls', current_app.config['SMTP_TLS'])),
        daily_email_limit=int(data.get('daily_email_limit') or current_app.config['DAILY_EMAIL_LIMIT']),
    )
    business.set_password(data['password'])
    db.session.add(business)
    db.session.commit()
    return business


def authenticate(email, password):
    if not email or not password:
        raise ServiceError('email and password are required')
    try:
        email = normalize_email(email)
    except ServiceError:
        raise ServiceError('Invalid email or password', 401)
    business = Business.query.filter_by(account_email=email).first()
    if business is None or not business.check_password(password):
        raise ServiceError('Invalid email or password', 401)
    return business


def update_business(business, data):
    unknown = set(data) - BUSINESS_UPDATABLE_FIELDS - {'password', 'current_password'}
    if unknown:
        raise ServiceError('Unknown or read-only fields', details={'fields': sorted(unknown)})
    for field in BUSINESS_UPDATABLE_FIELDS & set(data):
        value = data[field]
        if field in ('email_from',):
            value = normalize_email(value)
        elif field == 'smtp_port':
            value = validate_port(value)
        elif field == 'smtp_tls':
            value = bool(value)
        elif field == 'daily_email_limit':
            try:
                value = int(value)
            except (TypeError, ValueError):
                raise ServiceError('daily_email_limit must be an integer')
            if value < 0:
                raise ServiceError('daily_email_limit cannot be negative')
        elif field in ('name', 'sender_domain', 'smtp_host') and not value:
            raise ServiceError(f'{field} cannot be empty')
        if field == 'smtp_username':
            value = value or ''
        setattr(business, field, value)

    if 'password' in data:
        if not business.check_password(data.get('current_password') or ''):
            raise ServiceError('current_password is incorrect', 403)
        business.set_password(validate_password(data['password']))
        business.token_version = (business.token_version or 0) + 1  # revoke old tokens
    db.session.commit()
    return business


def rotate_api_key(business):
    business.api_key = generate_api_key()
    db.session.commit()
    return business.api_key


def revoke_tokens(business):
    business.token_version = (business.token_version or 0) + 1
    db.session.commit()


def get_stats(business):
    from app.services.analytics_service import get_business_overview
    return get_business_overview(business.id)
