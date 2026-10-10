import csv
import io
from datetime import timedelta

from sqlalchemy import or_

from app import db
from app.models import AutomationInstance, Subscriber
from app.utils.helpers import NotFoundError, ServiceError, parse_datetime, rows_to_csv, utcnow
from app.utils.validators import normalize_email, validate_dict, validate_subscriber_status

STANDARD_IMPORT_FIELDS = {'email', 'first_name', 'last_name', 'status', 'tags', 'custom_fields'}
EXPORT_FIELDS = ['id', 'email', 'first_name', 'last_name', 'status', 'tags', 'engagement_score',
                 'total_opens', 'total_clicks', 'subscribed_at', 'unsubscribed_at', 'created_at']
MAX_BULK_IMPORT = 10000


def _clean_tags(tags):
    if tags is None:
        return []
    if isinstance(tags, str):
        tags = [t for t in (part.strip() for part in tags.split(',')) if t]
    if not isinstance(tags, list) or not all(isinstance(t, str) for t in tags):
        raise ServiceError('tags must be a list of strings')
    return sorted({t.strip() for t in tags if t.strip()})


def get_subscriber(business_id, subscriber_id):
    subscriber = Subscriber.query.filter_by(id=subscriber_id, business_id=business_id).first()
    if subscriber is None:
        raise NotFoundError('Subscriber')
    return subscriber


def get_subscriber_by_email(business_id, email):
    return Subscriber.query.filter_by(business_id=business_id, email=normalize_email(email)).first()


def add_subscriber(business_id, email, first_name=None, last_name=None, custom_fields=None,
                   tags=None, status='active', trigger_automations=True):
    email = normalize_email(email)
    validate_subscriber_status(status)
    if Subscriber.query.filter_by(business_id=business_id, email=email).first():
        raise ServiceError('Subscriber with this email already exists', 409)
    subscriber = Subscriber(
        business_id=business_id, email=email, first_name=first_name, last_name=last_name,
        custom_fields=validate_dict(custom_fields, 'custom_fields'), tags=_clean_tags(tags), status=status,
    )
    db.session.add(subscriber)
    db.session.commit()
    if trigger_automations and subscriber.status == 'active':
        from app.services import automation_service
        automation_service.handle_event(business_id, 'new_subscriber', subscriber)
    return subscriber


def parse_import_payload(raw_csv=None, records=None):
    """Normalize CSV text or a JSON list into a list of dicts."""
    if raw_csv is not None:
        reader = csv.DictReader(io.StringIO(raw_csv.lstrip('﻿')))
        if not reader.fieldnames or 'email' not in [f.strip().lower() for f in reader.fieldnames]:
            raise ServiceError('CSV must have a header row with an "email" column')
        rows = []
        for row in reader:
            clean = {}
            for key, value in row.items():
                if key is None:
                    continue
                key = key.strip()
                clean[key.lower() if key.lower() in STANDARD_IMPORT_FIELDS else key] = \
                    value.strip() if isinstance(value, str) else value
            rows.append(clean)
        return rows
    if not isinstance(records, list):
        raise ServiceError('Provide "subscribers" as a list, or upload a CSV file')
    return records


def bulk_import(business_id, subscribers_data, update_existing=False, trigger_automations=False):
    """Import many subscribers; returns counts and per-row errors.

    Columns other than the standard ones become custom fields.
    """
    if len(subscribers_data) > MAX_BULK_IMPORT:
        raise ServiceError(f'At most {MAX_BULK_IMPORT} subscribers per import')

    existing = {}
    emails = []
    errors = []
    prepared = []
    for index, raw in enumerate(subscribers_data):
        if not isinstance(raw, dict):
            errors.append({'row': index + 1, 'error': 'Row must be an object'})
            continue
        try:
            email = normalize_email(raw.get('email'))
            status = raw.get('status') or 'active'
            validate_subscriber_status(status)
            custom = validate_dict(raw.get('custom_fields'), 'custom_fields').copy()
            for key, value in raw.items():
                if key not in STANDARD_IMPORT_FIELDS and value not in (None, ''):
                    custom[key] = value
            prepared.append({
                'email': email, 'first_name': raw.get('first_name') or None,
                'last_name': raw.get('last_name') or None, 'status': status,
                'tags': _clean_tags(raw.get('tags')), 'custom_fields': custom, 'row': index + 1,
            })
            emails.append(email)
        except ServiceError as exc:
            errors.append({'row': index + 1, 'email': raw.get('email'), 'error': exc.message})
    failed = len(errors)

    for chunk_start in range(0, len(emails), 500):
        chunk = emails[chunk_start:chunk_start + 500]
        for sub in Subscriber.query.filter(Subscriber.business_id == business_id, Subscriber.email.in_(chunk)):
            existing[sub.email] = sub

    created, updated, skipped = [], 0, 0
    seen = set()
    for item in prepared:
        email = item['email']
        if email in seen:
            skipped += 1
            errors.append({'row': item['row'], 'email': email, 'error': 'Duplicate email in import'})
            continue
        seen.add(email)
        subscriber = existing.get(email)
        if subscriber is not None:
            if not update_existing:
                skipped += 1
                continue
            for field in ('first_name', 'last_name'):
                if item[field]:
                    setattr(subscriber, field, item[field])
            if item['custom_fields']:
                subscriber.custom_fields = {**(subscriber.custom_fields or {}), **item['custom_fields']}
            if item['tags']:
                subscriber.tags = sorted(set(subscriber.tags or []) | set(item['tags']))
            updated += 1
            continue
        subscriber = Subscriber(
            business_id=business_id, email=email, first_name=item['first_name'],
            last_name=item['last_name'], status=item['status'], tags=item['tags'],
            custom_fields=item['custom_fields'],
        )
        db.session.add(subscriber)
        created.append(subscriber)
    db.session.commit()

    if trigger_automations:
        from app.services import automation_service
        for subscriber in created:
            if subscriber.status == 'active':
                automation_service.handle_event(business_id, 'new_subscriber', subscriber)

    return {
        'created': len(created),
        'updated': updated,
        'skipped': skipped,
        'failed': failed,
        'errors': errors[:100],
    }


def known_fields(business_id, sample=5000):
    """Custom field keys and tags in use (for building segment rules)."""
    custom, tags = set(), set()
    rows = (db.session.query(Subscriber.custom_fields, Subscriber.tags)
            .filter(Subscriber.business_id == business_id)
            .order_by(Subscriber.created_at.desc()).limit(sample))
    for fields, subscriber_tags in rows:
        custom.update((fields or {}).keys())
        tags.update(subscriber_tags or [])
    return {'custom_fields': sorted(custom), 'tags': sorted(tags)}


def get_subscribers(business_id, filters=None):
    filters = filters or {}
    query = Subscriber.query.filter(Subscriber.business_id == business_id)
    if filters.get('status'):
        validate_subscriber_status(filters['status'])
        query = query.filter(Subscriber.status == filters['status'])
    if filters.get('search'):
        term = f"%{filters['search'].lower()}%"
        query = query.filter(or_(
            Subscriber.email.ilike(term), Subscriber.first_name.ilike(term), Subscriber.last_name.ilike(term),
        ))
    if filters.get('tag'):
        from app.services.segment_service import build_condition
        query = query.filter(build_condition({'rules': [
            {'field': 'tags', 'operator': 'contains', 'value': filters['tag']}]}))
    if filters.get('segment_id'):
        from app.services.segment_service import get_segment, build_condition
        segment = get_segment(business_id, filters['segment_id'])
        query = query.filter(build_condition(segment.filter_rules))
    if filters.get('rules'):
        from app.services.segment_service import build_condition
        query = query.filter(build_condition(filters['rules']))
    for key, column in (('subscribed', Subscriber.subscribed_at), ('created', Subscriber.created_at)):
        if filters.get(f'{key}_from'):
            query = query.filter(column >= parse_datetime(filters[f'{key}_from']))
        if filters.get(f'{key}_to'):
            end = parse_datetime(filters[f'{key}_to'])
            if len(str(filters[f'{key}_to']).strip()) == 10:
                end += timedelta(days=1)  # plain date = include that whole day
            query = query.filter(column < end)
    for key, op in (('engagement_min', '__ge__'), ('engagement_max', '__le__')):
        if filters.get(key) not in (None, ''):
            try:
                query = query.filter(getattr(Subscriber.engagement_score, op)(float(filters[key])))
            except (TypeError, ValueError):
                raise ServiceError(f'{key} must be a number')
    sort = filters.get('sort', '-created_at')
    column = getattr(Subscriber, sort.lstrip('-'), None)
    if column is None or sort.lstrip('-') not in ('created_at', 'email', 'engagement_score', 'subscribed_at'):
        column = Subscriber.created_at
    return query.order_by(column.desc() if sort.startswith('-') else column.asc())


def update_subscriber(business_id, subscriber_id, data):
    subscriber = get_subscriber(business_id, subscriber_id)
    if 'email' in data:
        email = normalize_email(data['email'])
        if email != subscriber.email:
            if Subscriber.query.filter_by(business_id=business_id, email=email).first():
                raise ServiceError('Subscriber with this email already exists', 409)
            subscriber.email = email
    for field in ('first_name', 'last_name'):
        if field in data:
            setattr(subscriber, field, data[field])
    if 'custom_fields' in data:
        fields = validate_dict(data['custom_fields'], 'custom_fields')
        if data.get('replace_custom_fields'):
            subscriber.custom_fields = fields
        else:
            merged = {**(subscriber.custom_fields or {}), **fields}
            subscriber.custom_fields = {k: v for k, v in merged.items() if v is not None}
    if 'tags' in data:
        subscriber.tags = _clean_tags(data['tags'])
    if 'status' in data:
        _apply_status(subscriber, data['status'])
    db.session.commit()
    return subscriber


def change_status(business_id, subscriber_id, status):
    subscriber = get_subscriber(business_id, subscriber_id)
    _apply_status(subscriber, status)
    db.session.commit()
    return subscriber


def _apply_status(subscriber, status):
    validate_subscriber_status(status)
    if status == subscriber.status:
        return
    subscriber.status = status
    if status == 'unsubscribed':
        subscriber.unsubscribed_at = utcnow()
    elif status == 'active':
        subscriber.unsubscribed_at = None
        subscriber.bounce_count = 0
    if status != 'active':
        _stop_automations(subscriber)


def _stop_automations(subscriber):
    AutomationInstance.query.filter_by(subscriber_id=subscriber.id, status='active').update(
        {'status': 'completed', 'completed_at': utcnow(), 'error_message': f'Subscriber {subscriber.status}'},
        synchronize_session=False,
    )


def unsubscribe(subscriber, email_log=None):
    """Unsubscribe a subscriber (from a link / header); idempotent."""
    if subscriber.status == 'unsubscribed':
        return False
    _apply_status(subscriber, 'unsubscribed')
    if email_log is not None:
        from app.models import EmailEvent
        db.session.add(EmailEvent(
            business_id=subscriber.business_id, email_log_id=email_log.id, campaign_id=email_log.campaign_id,
            subscriber_id=subscriber.id, event_type='unsubscribe',
        ))
        if email_log.campaign is not None:
            email_log.campaign.total_unsubscribes = (email_log.campaign.total_unsubscribes or 0) + 1
    db.session.commit()
    return True


def delete_subscriber(business_id, subscriber_id):
    subscriber = get_subscriber(business_id, subscriber_id)
    db.session.delete(subscriber)
    db.session.commit()


BULK_ACTIONS = {'add_tag', 'remove_tag', 'set_status', 'delete'}
MAX_BULK_IDS = 50000


def resolve_selection(business_id, ids=None, filters=None):
    """Subscribers chosen in the UI: explicit ids, or everyone matching filters."""
    query = Subscriber.query.filter(Subscriber.business_id == business_id)
    if ids is not None:
        if not isinstance(ids, list) or len(ids) > MAX_BULK_IDS:
            raise ServiceError(f'ids must be a list of at most {MAX_BULK_IDS} subscriber ids')
        return query.filter(Subscriber.id.in_(ids))
    if filters is None:
        raise ServiceError('Provide "ids" or "filters"')
    return get_subscribers(business_id, filters).order_by(None)


def bulk_action(business_id, action, value=None, ids=None, filters=None):
    if action not in BULK_ACTIONS:
        raise ServiceError(f'Unknown action: {action}', details={'allowed': sorted(BULK_ACTIONS)})
    if action in ('add_tag', 'remove_tag'):
        tags = _clean_tags(value if isinstance(value, list) else [value] if value else [])
        if not tags:
            raise ServiceError('A tag is required')
    if action == 'set_status':
        validate_subscriber_status(value)

    affected = 0
    selection = resolve_selection(business_id, ids, filters)
    if action == 'delete':
        for subscriber in selection.all():
            db.session.delete(subscriber)
            affected += 1
        db.session.commit()
        return {'action': action, 'affected': affected}

    for subscriber in selection.all():
        current = set(subscriber.tags or [])
        if action == 'add_tag' and not set(tags) <= current:
            subscriber.tags = sorted(current | set(tags))
            affected += 1
        elif action == 'remove_tag' and current & set(tags):
            subscriber.tags = sorted(current - set(tags))
            affected += 1
        elif action == 'set_status' and subscriber.status != value:
            _apply_status(subscriber, value)
            affected += 1
    db.session.commit()
    return {'action': action, 'affected': affected}


def export_subscribers(business_id, filters=None, format='csv'):
    query = get_subscribers(business_id, filters)
    rows = []
    custom_keys = set()
    for subscriber in query.yield_per(1000):
        row = subscriber.to_dict()
        row['tags'] = ','.join(row['tags'])
        for key, value in (subscriber.custom_fields or {}).items():
            row[f'custom.{key}'] = value
            custom_keys.add(f'custom.{key}')
        rows.append(row)
    if format == 'json':
        return rows
    return rows_to_csv(rows, EXPORT_FIELDS + sorted(custom_keys))
