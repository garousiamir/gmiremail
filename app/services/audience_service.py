"""Campaign audiences: who receives a campaign.

An audience combines several groups. A subscriber is included when they match
ANY include group, and dropped when they match ANY exclude group::

    {
      "segment_ids": ["..."],              # people in these segments
      "tags": ["vip", "beta"],             # people with any of these tags
      "subscriber_ids": ["..."],           # hand-picked people
      "rules": {"logic": "AND", "rules": [...]},   # an ad-hoc filter (segment format)
      "exclude_segment_ids": ["..."],
      "exclude_tags": ["do-not-mail"]
    }

No include group at all means "all active subscribers". Only active subscribers
are ever mailed, whatever the groups say.
"""
from sqlalchemy import and_, false, func, not_, or_

from app.models import Subscriber
from app.services import segment_service
from app.utils.helpers import ServiceError

LIST_KEYS = ('segment_ids', 'tags', 'subscriber_ids', 'exclude_segment_ids', 'exclude_tags')
MAX_PICKED = 50000


def _clean_list(value, key):
    if value in (None, ''):
        return []
    if not isinstance(value, list) or not all(isinstance(v, str) and v.strip() for v in value):
        raise ServiceError(f'audience.{key} must be a list of strings')
    cleaned = list(dict.fromkeys(v.strip() for v in value))  # dedupe, keep order
    if len(cleaned) > MAX_PICKED:
        raise ServiceError(f'audience.{key} can have at most {MAX_PICKED} entries')
    return cleaned


def validate_audience(business_id, audience):
    """Normalize an audience dict; returns None for "all active subscribers"."""
    if audience in (None, {}, ''):
        return None
    if not isinstance(audience, dict):
        raise ServiceError('audience must be an object')
    unknown = set(audience) - set(LIST_KEYS) - {'rules'}
    if unknown:
        raise ServiceError('Unknown audience fields', details={'fields': sorted(unknown)})
    clean = {key: _clean_list(audience.get(key), key) for key in LIST_KEYS}
    for key in ('segment_ids', 'exclude_segment_ids'):
        for segment_id in clean[key]:
            segment_service.get_segment(business_id, segment_id)  # 404 for other tenants' ids
    rules = audience.get('rules')
    if rules and (rules.get('rules') if isinstance(rules, dict) else True):
        clean['rules'] = segment_service.validate_filter_rules(rules)
    else:
        clean['rules'] = None
    if not any(clean[k] for k in LIST_KEYS) and not clean['rules']:
        return None
    return clean


def has_includes(audience):
    return bool(audience and (audience.get('segment_ids') or audience.get('tags')
                              or audience.get('subscriber_ids') or audience.get('rules')))


def _tags_condition(tags):
    return segment_service.build_condition({'logic': 'OR', 'rules': [
        {'field': 'tags', 'operator': 'contains', 'value': tag} for tag in tags]})


def _segment_condition(business_id, segment_id):
    return segment_service.build_condition(segment_service.get_segment(business_id, segment_id).filter_rules)


def audience_condition(business_id, audience):
    """SQL condition for an audience (None = everyone)."""
    if not audience:
        return None
    includes = [_segment_condition(business_id, sid) for sid in audience.get('segment_ids') or []]
    if audience.get('tags'):
        includes.append(_tags_condition(audience['tags']))
    if audience.get('subscriber_ids'):
        includes.append(Subscriber.id.in_(audience['subscriber_ids']))
    if audience.get('rules'):
        includes.append(segment_service.build_condition(audience['rules']))

    excludes = [_segment_condition(business_id, sid) for sid in audience.get('exclude_segment_ids') or []]
    if audience.get('exclude_tags'):
        excludes.append(_tags_condition(audience['exclude_tags']))

    parts = []
    if includes:
        parts.append(or_(*includes))
    elif has_includes(audience):
        parts.append(false())
    if excludes:
        # NULL-safe: a missing field makes "in segment" NULL, which must count as "not in it"
        parts.append(not_(func.coalesce(or_(*excludes), false())))
    return and_(*parts) if parts else None


def audience_query(business_id, audience, only_active=True):
    query = Subscriber.query.filter(Subscriber.business_id == business_id)
    condition = audience_condition(business_id, audience)
    if condition is not None:
        query = query.filter(condition)
    if only_active:
        query = query.filter(Subscriber.status == 'active')
    return query


def preview(business_id, audience, sample=8):
    audience = validate_audience(business_id, audience)
    query = audience_query(business_id, audience)
    return {
        'recipients': query.count(),
        'sample': [{'id': s.id, 'email': s.email, 'first_name': s.first_name}
                   for s in query.order_by(Subscriber.created_at.desc()).limit(sample)],
        'audience': audience,
    }


def describe(audience, segment_names=None):
    """Short human summary, e.g. '2 segments, tag vip, 5 people (excluding 1 segment)'."""
    if not audience:
        return 'All active subscribers'
    segment_names = segment_names or {}
    parts = []
    segs = audience.get('segment_ids') or []
    if segs:
        names = [segment_names.get(s) for s in segs]
        parts.append(', '.join(n for n in names if n) if all(names) and len(segs) <= 2
                     else f'{len(segs)} segments')
    tags = audience.get('tags') or []
    if tags:
        parts.append(('tag ' if len(tags) == 1 else 'tags ') + ', '.join(tags[:3]) + ('…' if len(tags) > 3 else ''))
    people = audience.get('subscriber_ids') or []
    if people:
        parts.append(f"{len(people)} {'person' if len(people) == 1 else 'people'}")
    if audience.get('rules'):
        parts.append('custom filter')
    text = ' + '.join(parts) if parts else 'All active subscribers'
    excl = len(audience.get('exclude_segment_ids') or []) + len(audience.get('exclude_tags') or [])
    if excl:
        text += f' (excluding {excl} group{"s" if excl > 1 else ""})'
    return text
