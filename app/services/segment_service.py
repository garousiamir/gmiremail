"""Segmentation: turns JSON filter rules into SQL over the subscribers table.

Rule format::

    {
      "logic": "AND",            # or "OR"
      "rules": [
        {"field": "status", "operator": "equals", "value": "active"},
        {"field": "custom_fields.plan", "operator": "in", "value": ["pro", "team"]},
        {"logic": "OR", "rules": [...]}          # nested groups are allowed
      ]
    }

Fields:
  * subscriber columns (email, first_name, status, engagement_score, ...)
  * ``tags`` (operators: contains / not_contains / is_set / is_not_set)
  * custom fields: ``custom_fields.<key>``; any unknown field name is treated
    as a custom field too (so ``custom_field_1`` works as in the spec)
  * campaign history: ``campaign_received`` / ``campaign_opened`` /
    ``campaign_clicked`` with ``equals`` / ``not_equals`` a campaign id
"""
from datetime import timedelta

from sqlalchemy import String, and_, cast, exists, false, func, not_, or_, true

from app import db
from app.models import EmailLog, Segment, Subscriber
from app.utils.constants import (SEGMENT_LOGIC, SEGMENT_OPERATORS, SUBSCRIBER_COLUMN_FIELDS,
                                 SUBSCRIBER_DATE_FIELDS)
from app.utils.helpers import NotFoundError, ServiceError, parse_datetime, utcnow

CAMPAIGN_HISTORY_FIELDS = {'campaign_received', 'campaign_opened', 'campaign_clicked'}
NUMERIC_OPERATORS = {'greater_than', 'less_than', 'greater_or_equal', 'less_or_equal'}
DATE_OPERATORS = {'before', 'after', 'within_last_days', 'not_within_last_days'}
MAX_RULE_DEPTH = 5


# ---------------------------------------------------------------- validation

def validate_filter_rules(filter_rules, depth=0):
    if not isinstance(filter_rules, dict):
        raise ServiceError('filter_rules must be an object with "rules" and "logic"')
    if depth > MAX_RULE_DEPTH:
        raise ServiceError('filter_rules are nested too deeply')
    logic = str(filter_rules.get('logic', 'AND')).upper()
    if logic not in SEGMENT_LOGIC:
        raise ServiceError('filter_rules.logic must be "AND" or "OR"')
    rules = filter_rules.get('rules', [])
    if not isinstance(rules, list):
        raise ServiceError('filter_rules.rules must be a list')
    for rule in rules:
        if not isinstance(rule, dict):
            raise ServiceError('Each rule must be an object')
        if 'rules' in rule:
            validate_filter_rules(rule, depth + 1)
            continue
        field = rule.get('field')
        operator = rule.get('operator')
        if not field or not isinstance(field, str):
            raise ServiceError('Each rule needs a "field"')
        if operator not in SEGMENT_OPERATORS:
            raise ServiceError(f'Unsupported operator: {operator}', details={'allowed': sorted(SEGMENT_OPERATORS)})
        if operator not in ('is_set', 'is_not_set') and 'value' not in rule:
            raise ServiceError(f'Rule on "{field}" needs a "value"')
        if operator in ('in', 'not_in') and not isinstance(rule.get('value'), list):
            raise ServiceError(f'Operator "{operator}" needs a list value')
        if operator == 'between':
            value = rule.get('value')
            if not isinstance(value, list) or len(value) != 2 or all(v in (None, '') for v in value):
                raise ServiceError(f'"between" on "{field}" needs [from, to] (either may be empty)')
        if operator in ('within_last_days', 'not_within_last_days'):
            _to_number(rule.get('value'), field)
        if field in CAMPAIGN_HISTORY_FIELDS and operator not in ('equals', 'not_equals'):
            raise ServiceError(f'"{field}" only supports equals / not_equals')
    return {'logic': logic, 'rules': rules}


# ------------------------------------------------------------- SQL building

def build_condition(filter_rules):
    """Return a SQLAlchemy boolean expression for the given filter rules."""
    filter_rules = validate_filter_rules(filter_rules)
    conditions = []
    for rule in filter_rules['rules']:
        if 'rules' in rule:
            conditions.append(build_condition(rule))
        else:
            conditions.append(_rule_condition(rule))
    if not conditions:
        return true()
    return and_(*conditions) if filter_rules['logic'] == 'AND' else or_(*conditions)


def _to_number(value, field):
    try:
        return float(value)
    except (TypeError, ValueError):
        raise ServiceError(f'Rule on "{field}" needs a numeric value')


def _like_escape(value):
    return str(value).replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')


def _rule_condition(rule):
    field = rule['field']
    operator = rule['operator']
    value = rule.get('value')

    if field in CAMPAIGN_HISTORY_FIELDS:
        return _campaign_history_condition(field, operator, value)
    if field == 'tags':
        return _tags_condition(operator, value)
    if field in SUBSCRIBER_COLUMN_FIELDS:
        column = getattr(Subscriber, field)
        is_date = field in SUBSCRIBER_DATE_FIELDS
        is_numeric = field in ('total_opens', 'total_clicks', 'engagement_score', 'bounce_count')
        return _compare(column, operator, value, field, is_date=is_date, is_numeric=is_numeric)

    key = field.split('.', 1)[1] if field.startswith(('custom_fields.', 'custom.')) else field
    element = Subscriber.custom_fields[key]
    if operator in ('is_set', 'is_not_set'):
        condition = and_(element.as_string().isnot(None), element.as_string() != '')
        return condition if operator == 'is_set' else not_(condition)
    if operator == 'between':
        low, high = rule.get('value') or [None, None]
        probe = low if low not in (None, '') else high
        try:
            float(probe)
            return _compare(element.as_float(), operator, value, field, is_numeric=True)
        except (TypeError, ValueError):
            return _compare(element.as_string(), operator, value, field, is_date=True, date_as_string=True)
    if operator in NUMERIC_OPERATORS or (operator in ('equals', 'not_equals') and
                                         isinstance(value, (int, float)) and not isinstance(value, bool)):
        return _compare(element.as_float(), operator, value, field, is_numeric=True)
    if isinstance(value, bool):
        column = element.as_boolean()
        return column.is_(value) if operator == 'equals' else or_(column.is_(None), column.isnot(value))
    if operator in DATE_OPERATORS:
        return _compare(element.as_string(), operator, value, field, is_date=True, date_as_string=True)
    return _compare(element.as_string(), operator, value, field)


def _compare(column, operator, value, field, is_date=False, is_numeric=False, date_as_string=False):
    if operator == 'is_set':
        return column.isnot(None)
    if operator == 'is_not_set':
        return column.is_(None)

    if operator == 'between':
        low, high = value
        parts = []
        if is_date:
            if low not in (None, ''):
                start = parse_datetime(low)
                parts.append(column >= (start.isoformat() if date_as_string else start))
            if high not in (None, ''):
                end = parse_datetime(high)
                if isinstance(high, str) and len(high.strip()) == 10:
                    end += timedelta(days=1)  # a plain date includes that whole day
                    parts.append(column < (end.isoformat() if date_as_string else end))
                else:
                    parts.append(column <= (end.isoformat() if date_as_string else end))
        else:
            if low not in (None, ''):
                parts.append(column >= (_to_number(low, field) if is_numeric else low))
            if high not in (None, ''):
                parts.append(column <= (_to_number(high, field) if is_numeric else high))
        return and_(*parts) if parts else true()

    if is_date:
        if operator in ('within_last_days', 'not_within_last_days'):
            threshold = utcnow() - timedelta(days=_to_number(value, field))
            threshold_value = threshold.isoformat() if date_as_string else threshold
            if operator == 'within_last_days':
                return column >= threshold_value
            return column < threshold_value
        parsed = parse_datetime(value) if operator in ('before', 'after', 'equals', 'not_equals',
                                                        *NUMERIC_OPERATORS) else None
        if parsed is not None:
            value = parsed.isoformat() if date_as_string else parsed
    elif operator in DATE_OPERATORS:
        raise ServiceError(f'Operator "{operator}" only applies to date fields')

    if is_numeric and operator not in ('in', 'not_in'):
        value = _to_number(value, field)

    if operator == 'equals':
        return column == value
    if operator == 'not_equals':
        return or_(column.is_(None), column != value)
    if operator in ('greater_than', 'after'):
        return column > value
    if operator in ('less_than', 'before'):
        return column < value
    if operator == 'greater_or_equal':
        return column >= value
    if operator == 'less_or_equal':
        return column <= value
    if operator == 'in':
        return column.in_(value) if value else false()
    if operator == 'not_in':
        return or_(column.is_(None), column.notin_(value)) if value else true()

    text = func.lower(cast(column, String))
    needle = _like_escape(str(value).lower())
    if operator == 'contains':
        return text.like(f'%{needle}%', escape='\\')
    if operator == 'not_contains':
        return or_(column.is_(None), not_(text.like(f'%{needle}%', escape='\\')))
    if operator == 'starts_with':
        return text.like(f'{needle}%', escape='\\')
    if operator == 'ends_with':
        return text.like(f'%{needle}', escape='\\')
    raise ServiceError(f'Unsupported operator "{operator}" for field "{field}"')


def _tags_condition(operator, value):
    # Tags are stored as a JSON array of strings; match the quoted element in
    # its serialized form, which works on both PostgreSQL and SQLite.
    serialized = cast(Subscriber.tags, String)
    if operator in ('is_set', 'is_not_set'):
        condition = and_(Subscriber.tags.isnot(None), serialized.notin_(['[]', 'null']))
        return condition if operator == 'is_set' else not_(condition)
    if operator in ('contains', 'equals', 'not_contains', 'not_equals', 'in', 'not_in'):
        values = value if isinstance(value, list) else [value]
        matches = [serialized.like(f'%"{_like_escape(v)}"%', escape='\\') for v in values]
        condition = or_(*matches) if matches else false()
        return not_(condition) if operator in ('not_contains', 'not_equals', 'not_in') else condition
    raise ServiceError(f'Operator "{operator}" is not supported for tags')


def _campaign_history_condition(field, operator, campaign_id):
    clauses = [EmailLog.subscriber_id == Subscriber.id, EmailLog.campaign_id == str(campaign_id)]
    if field == 'campaign_received':
        clauses.append(EmailLog.sent_at.isnot(None))
    elif field == 'campaign_opened':
        clauses.append(EmailLog.opened_at.isnot(None))
    else:
        clauses.append(EmailLog.clicked_at.isnot(None))
    condition = exists().where(and_(*clauses))
    return condition if operator == 'equals' else not_(condition)


# -------------------------------------------------------------- queries/CRUD

def subscribers_query(business_id, filter_rules=None, only_active=False):
    query = Subscriber.query.filter(Subscriber.business_id == business_id)
    if filter_rules:
        query = query.filter(build_condition(filter_rules))
    if only_active:
        query = query.filter(Subscriber.status == 'active')
    return query


def subscriber_matches(subscriber, filter_rules):
    """True if a single subscriber matches the rules (used by automations)."""
    return db.session.query(
        subscribers_query(subscriber.business_id, filter_rules)
        .filter(Subscriber.id == subscriber.id).exists()
    ).scalar()


def get_segment(business_id, segment_id):
    segment = Segment.query.filter_by(id=segment_id, business_id=business_id).first()
    if segment is None:
        raise NotFoundError('Segment')
    return segment


def list_segments(business_id):
    return Segment.query.filter_by(business_id=business_id).order_by(Segment.created_at.desc())


def create_segment(business_id, name, filter_rules, description=None):
    if not name:
        raise ServiceError('Segment name is required')
    filter_rules = validate_filter_rules(filter_rules)
    if Segment.query.filter_by(business_id=business_id, name=name).first():
        raise ServiceError('A segment with this name already exists', 409)
    segment = Segment(business_id=business_id, name=name, description=description, filter_rules=filter_rules)
    db.session.add(segment)
    db.session.flush()
    _refresh_count(segment)
    db.session.commit()
    return segment


def update_segment(business_id, segment_id, data):
    segment = get_segment(business_id, segment_id)
    if 'name' in data and data['name'] != segment.name:
        if not data['name']:
            raise ServiceError('Segment name is required')
        if Segment.query.filter_by(business_id=business_id, name=data['name']).first():
            raise ServiceError('A segment with this name already exists', 409)
        segment.name = data['name']
    if 'description' in data:
        segment.description = data['description']
    if 'filter_rules' in data:
        segment.filter_rules = validate_filter_rules(data['filter_rules'])
    _refresh_count(segment)
    db.session.commit()
    return segment


def delete_segment(business_id, segment_id):
    from app.models import Campaign
    segment = get_segment(business_id, segment_id)
    in_use = Campaign.query.filter(Campaign.segment_id == segment.id,
                                   Campaign.status.in_(['scheduled', 'sending', 'paused'])).count()
    if in_use:
        raise ServiceError('Segment is used by scheduled or in-progress campaigns', 409)
    db.session.delete(segment)
    db.session.commit()


def get_segment_subscribers(business_id, segment_id, only_active=False):
    segment = get_segment(business_id, segment_id)
    return subscribers_query(business_id, segment.filter_rules, only_active=only_active)


def count_segment(business_id, segment_id):
    segment = get_segment(business_id, segment_id)
    count = _refresh_count(segment)
    active = subscribers_query(business_id, segment.filter_rules, only_active=True).count()
    db.session.commit()
    return {'segment_id': segment.id, 'subscriber_count': count, 'active_subscriber_count': active}


def evaluate_segment(business_id, segment_id):
    """Alias kept for the implementation guide's naming."""
    return count_segment(business_id, segment_id)


def preview_rules(business_id, filter_rules, limit=10):
    query = subscribers_query(business_id, filter_rules)
    return {
        'subscriber_count': query.count(),
        'sample': [s.to_dict() for s in query.order_by(Subscriber.created_at.desc()).limit(limit)],
    }


def refresh_all_counts():
    for segment in Segment.query.all():
        _refresh_count(segment)
    db.session.commit()


def _refresh_count(segment):
    segment.subscriber_count = subscribers_query(segment.business_id, segment.filter_rules).count()
    segment.count_updated_at = utcnow()
    return segment.subscriber_count
