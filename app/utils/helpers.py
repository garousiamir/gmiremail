import csv
import io
import secrets
import uuid
from datetime import datetime, timezone

from dateutil import parser as date_parser
from flask import current_app, request


class ServiceError(Exception):
    """Error raised by the service layer and rendered as a JSON response."""

    def __init__(self, message, status_code=400, details=None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.details = details


class NotFoundError(ServiceError):
    def __init__(self, resource='Resource'):
        super().__init__(f'{resource} not found', 404)


def utcnow():
    """Naive UTC timestamp (stored consistently across PostgreSQL and SQLite)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def new_id():
    return str(uuid.uuid4())


def generate_api_key():
    return 'emk_' + secrets.token_urlsafe(32)


def isoformat(value):
    return value.isoformat() if value else None


def parse_datetime(value):
    """Parse an ISO-8601 string into a naive UTC datetime."""
    if value is None or value == '':
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        try:
            dt = date_parser.isoparse(str(value))
        except (ValueError, TypeError):
            raise ServiceError(f'Invalid datetime: {value}')
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def get_json_body():
    data = request.get_json(silent=True)
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ServiceError('Request body must be a JSON object')
    return data


def get_pagination():
    try:
        page = max(int(request.args.get('page', 1)), 1)
        per_page = int(request.args.get('per_page', current_app.config['DEFAULT_PAGE_SIZE']))
    except ValueError:
        raise ServiceError('page and per_page must be integers')
    per_page = min(max(per_page, 1), current_app.config['MAX_PAGE_SIZE'])
    return page, per_page


def paginate(query, page, per_page, serializer=None):
    result = query.paginate(page=page, per_page=per_page, error_out=False)
    serializer = serializer or (lambda item: item.to_dict())
    return {
        'items': [serializer(item) for item in result.items],
        'page': result.page,
        'per_page': result.per_page,
        'total': result.total,
        'pages': result.pages,
    }


def percentage(part, whole):
    return round(part / whole * 100, 2) if whole else 0.0


def rows_to_csv(rows, fieldnames):
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, extrasaction='ignore')
    writer.writeheader()
    for row in rows:
        writer.writerow({key: _csv_safe(row.get(key)) for key in fieldnames})
    return buffer.getvalue()


def _csv_safe(value):
    """Prevent CSV/formula injection when exports are opened in spreadsheets."""
    if value is None:
        return ''
    text = str(value)
    if text and text[0] in ('=', '+', '-', '@', '\t', '\r'):
        return "'" + text
    return text


def client_ip():
    # Behind a reverse proxy, TRUSTED_PROXIES makes ProxyFix set remote_addr
    # from X-Forwarded-For; the raw header is never trusted (it is spoofable).
    return request.remote_addr or 'unknown'
