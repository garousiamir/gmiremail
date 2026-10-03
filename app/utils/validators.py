from email_validator import EmailNotValidError, validate_email

from app.utils.constants import SUBSCRIBER_STATUSES
from app.utils.helpers import ServiceError


def normalize_email(email, check_deliverability=False):
    """Validate an email address and return its normalized form.

    Raises ServiceError when the address is invalid.
    """
    if not email or not isinstance(email, str):
        raise ServiceError('Email address is required')
    try:
        result = validate_email(email.strip(), check_deliverability=check_deliverability)
    except EmailNotValidError as exc:
        raise ServiceError(f'Invalid email address: {email}', details=str(exc))
    return result.normalized.lower()


def is_valid_email(email):
    try:
        normalize_email(email)
        return True
    except ServiceError:
        return False


def require_fields(data, *fields):
    missing = [f for f in fields if data.get(f) in (None, '')]
    if missing:
        raise ServiceError('Missing required fields', details={'missing': missing})


def validate_choice(value, choices, field):
    if value not in choices:
        raise ServiceError(f'Invalid {field}: {value}', details={'allowed': sorted(choices)})
    return value


def validate_subscriber_status(status):
    return validate_choice(status, SUBSCRIBER_STATUSES, 'status')


def validate_password(password):
    if not isinstance(password, str) or len(password) < 8:
        raise ServiceError('Password must be at least 8 characters')
    return password


def validate_port(port):
    try:
        port = int(port)
    except (TypeError, ValueError):
        raise ServiceError('smtp_port must be an integer')
    if not 1 <= port <= 65535:
        raise ServiceError('smtp_port must be between 1 and 65535')
    return port


def validate_dict(value, field):
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ServiceError(f'{field} must be an object')
    return value
