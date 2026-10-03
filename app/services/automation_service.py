"""Automation workflow engine.

Workflow format::

    {"steps": [
        {"id": 1, "type": "send_email", "template_id": "...", "delay_days": 0},
        {"id": 2, "type": "wait", "days": 2},
        {"id": 3, "type": "condition", "condition": "email_opened", "if_true": 4, "if_false": 5},
        {"id": 4, "type": "send_email", "template_id": "..."},
        {"id": 5, "type": "add_tag", "tag": "engaged"}
    ]}

Step types: send_email, wait, condition, add_tag, remove_tag, update_field,
unsubscribe. After a step the engine moves to ``next`` (a step id) if given,
otherwise to the following step in the list. ``if_true`` / ``if_false`` on a
condition jump to a step id; ``null`` means "continue with the next step" and
``"end"`` (or an id that does not exist) ends the workflow.

Conditions: email_opened / email_not_opened / email_clicked /
email_not_clicked (about the last email this workflow sent) and
segment_rules (``"rules": {...}`` in the segment filter format).

Triggers: new_subscriber, email_opened / email_clicked (trigger_value may
hold a campaign id), custom_event (trigger_value = event name) and
time_based (trigger_value = "days_after_subscribe:N").
"""
import logging
from datetime import timedelta

from app import db
from app.models import Automation, AutomationInstance, EmailLog, Subscriber
from app.services import email_service, segment_service, template_service
from app.utils.constants import (AUTOMATION_CONDITIONS, AUTOMATION_STATUSES, AUTOMATION_STEP_TYPES,
                                 AUTOMATION_TRIGGERS)
from app.utils.helpers import NotFoundError, ServiceError, isoformat, utcnow

logger = logging.getLogger(__name__)

MAX_STEPS_PER_RUN = 50
MAX_HISTORY = 100
MAX_WORKFLOW_STEPS = 100
END = 'end'


# --------------------------------------------------------------- validation

def _delay(step, prefix=''):
    try:
        days = float(step.get(f'{prefix}days', 0) or 0)
        hours = float(step.get(f'{prefix}hours', 0) or 0)
        minutes = float(step.get(f'{prefix}minutes', 0) or 0)
    except (TypeError, ValueError):
        raise ServiceError(f'Step {step.get("id")}: delays must be numbers')
    if min(days, hours, minutes) < 0:
        raise ServiceError(f'Step {step.get("id")}: delays cannot be negative')
    return timedelta(days=days, hours=hours, minutes=minutes)


def parse_time_trigger(value):
    try:
        kind, days = str(value).split(':', 1)
        days = float(days)
    except (ValueError, AttributeError):
        kind, days = None, None
    if kind != 'days_after_subscribe' or days is None or days < 0:
        raise ServiceError('time_based trigger_value must look like "days_after_subscribe:3"')
    return days


def validate_workflow(business_id, workflow):
    if not isinstance(workflow, dict) or not isinstance(workflow.get('steps'), list):
        raise ServiceError('workflow must be an object with a "steps" list')
    steps = workflow['steps']
    if not steps:
        raise ServiceError('workflow needs at least one step')
    if len(steps) > MAX_WORKFLOW_STEPS:
        raise ServiceError(f'workflow can have at most {MAX_WORKFLOW_STEPS} steps')

    clean, seen_ids = [], set()
    for index, raw in enumerate(steps):
        if not isinstance(raw, dict):
            raise ServiceError(f'Step {index + 1} must be an object')
        step = dict(raw)
        step.setdefault('id', index + 1)
        if step['id'] in seen_ids:
            raise ServiceError(f'Duplicate step id: {step["id"]}')
        seen_ids.add(step['id'])
        step_type = step.get('type')
        if step_type not in AUTOMATION_STEP_TYPES:
            raise ServiceError(f'Step {step["id"]}: unknown type "{step_type}"',
                               details={'allowed': sorted(AUTOMATION_STEP_TYPES)})
        if step_type == 'send_email':
            if not step.get('template_id'):
                raise ServiceError(f'Step {step["id"]}: send_email needs a template_id')
            template_service.get_template(business_id, step['template_id'])
            _delay(step, 'delay_')
        elif step_type == 'wait':
            if _delay(step) <= timedelta(0):
                raise ServiceError(f'Step {step["id"]}: wait needs days, hours or minutes')
        elif step_type == 'condition':
            if step.get('condition') not in AUTOMATION_CONDITIONS:
                raise ServiceError(f'Step {step["id"]}: unknown condition "{step.get("condition")}"',
                                   details={'allowed': sorted(AUTOMATION_CONDITIONS)})
            if step['condition'] == 'segment_rules':
                segment_service.validate_filter_rules(step.get('rules'))
        elif step_type in ('add_tag', 'remove_tag'):
            if not isinstance(step.get('tag'), str) or not step['tag'].strip():
                raise ServiceError(f'Step {step["id"]}: {step_type} needs a "tag"')
        elif step_type == 'update_field':
            if not isinstance(step.get('field'), str) or not step['field']:
                raise ServiceError(f'Step {step["id"]}: update_field needs a "field"')
            if step['field'] in ('email', 'status'):
                raise ServiceError(f'Step {step["id"]}: update_field cannot change "{step["field"]}"')
        clean.append(step)
    return {'steps': clean}


def _validate_trigger(trigger_type, trigger_value):
    if trigger_type not in AUTOMATION_TRIGGERS:
        raise ServiceError(f'Invalid trigger_type: {trigger_type}', details={'allowed': sorted(AUTOMATION_TRIGGERS)})
    if trigger_type == 'custom_event' and not trigger_value:
        raise ServiceError('custom_event automations need trigger_value (the event name)')
    if trigger_type == 'time_based':
        parse_time_trigger(trigger_value)


# --------------------------------------------------------------------- CRUD

def get_automation(business_id, automation_id):
    automation = Automation.query.filter_by(id=automation_id, business_id=business_id).first()
    if automation is None:
        raise NotFoundError('Automation')
    return automation


def list_automations(business_id, status=None, trigger_type=None):
    query = Automation.query.filter_by(business_id=business_id)
    if status:
        query = query.filter_by(status=status)
    if trigger_type:
        query = query.filter_by(trigger_type=trigger_type)
    return query.order_by(Automation.created_at.desc())


def create_automation(business_id, name, trigger_type, workflow, trigger_value=None, status='active'):
    if not name:
        raise ServiceError('Automation name is required')
    _validate_trigger(trigger_type, trigger_value)
    if status not in AUTOMATION_STATUSES:
        raise ServiceError(f'Invalid status: {status}')
    automation = Automation(
        business_id=business_id, name=name, trigger_type=trigger_type,
        trigger_value=str(trigger_value) if trigger_value is not None else None,
        workflow=validate_workflow(business_id, workflow), status=status,
    )
    db.session.add(automation)
    db.session.commit()
    return automation


def update_automation(business_id, automation_id, data):
    automation = get_automation(business_id, automation_id)
    if 'name' in data:
        if not data['name']:
            raise ServiceError('Automation name is required')
        automation.name = data['name']
    trigger_type = data.get('trigger_type', automation.trigger_type)
    trigger_value = data.get('trigger_value', automation.trigger_value)
    if 'trigger_type' in data or 'trigger_value' in data:
        _validate_trigger(trigger_type, trigger_value)
        automation.trigger_type = trigger_type
        automation.trigger_value = str(trigger_value) if trigger_value is not None else None
    if 'workflow' in data:
        automation.workflow = validate_workflow(business_id, data['workflow'])
    if 'status' in data:
        if data['status'] not in AUTOMATION_STATUSES:
            raise ServiceError(f'Invalid status: {data["status"]}')
        automation.status = data['status']
    db.session.commit()
    return automation


def delete_automation(business_id, automation_id):
    automation = get_automation(business_id, automation_id)
    EmailLog.query.filter_by(automation_id=automation.id).update({'automation_id': None},
                                                                 synchronize_session=False)
    db.session.delete(automation)
    db.session.commit()


def set_status(business_id, automation_id, status):
    automation = get_automation(business_id, automation_id)
    automation.status = status
    db.session.commit()
    return automation


def list_instances(business_id, automation_id, status=None):
    automation = get_automation(business_id, automation_id)
    query = automation.instances
    if status:
        query = query.filter_by(status=status)
    return query.order_by(AutomationInstance.created_at.desc())


# ------------------------------------------------------------------ triggers

def evaluate_trigger(automation, trigger_type, subscriber, email_log=None, event=None):
    """Does this event start the given automation for this subscriber?"""
    if automation.status != 'active' or automation.trigger_type != trigger_type:
        return False
    if subscriber.status != 'active':
        return False
    if trigger_type in ('email_opened', 'email_clicked'):
        if email_log is None:
            return False
        if email_log.automation_id == automation.id:
            return False  # never re-trigger on our own emails (loops)
        if automation.trigger_value and automation.trigger_value != email_log.campaign_id:
            return False
    if trigger_type == 'custom_event' and automation.trigger_value != event:
        return False

    instances = AutomationInstance.query.filter_by(automation_id=automation.id, subscriber_id=subscriber.id)
    if trigger_type in ('new_subscriber', 'time_based'):
        return instances.count() == 0  # once per subscriber, ever
    return instances.filter_by(status='active').count() == 0


def handle_event(business_id, trigger_type, subscriber, email_log=None, event=None, url=None):
    """Start every matching automation for this subscriber. Never raises."""
    started = []
    try:
        automations = Automation.query.filter_by(business_id=business_id, trigger_type=trigger_type,
                                                 status='active').all()
        for automation in automations:
            if evaluate_trigger(automation, trigger_type, subscriber, email_log=email_log, event=event):
                started.append(execute_automation(automation, subscriber, context={
                    'trigger': trigger_type, 'event': event, 'url': url,
                    'email_log_id': email_log.id if email_log else None,
                }))
    except Exception:  # noqa: BLE001 - automations must not break the caller
        db.session.rollback()
        logger.exception('Automation trigger %s failed for subscriber %s', trigger_type, subscriber.id)
    return started


def fire_custom_event(business_id, event, subscriber_id=None, email=None):
    from app.services import subscriber_service
    if not event:
        raise ServiceError('event is required')
    if subscriber_id:
        subscriber = subscriber_service.get_subscriber(business_id, subscriber_id)
    elif email:
        subscriber = subscriber_service.get_subscriber_by_email(business_id, email)
        if subscriber is None:
            raise NotFoundError('Subscriber')
    else:
        raise ServiceError('subscriber_id or email is required')
    started = handle_event(business_id, 'custom_event', subscriber, event=event)
    return {'event': event, 'subscriber_id': subscriber.id, 'automations_started': len(started),
            'instance_ids': [i.id for i in started]}


def execute_automation(automation, subscriber, context=None):
    """Create an instance and run it until it waits or finishes."""
    if isinstance(automation, str):
        automation = db.session.get(Automation, automation)
    if isinstance(subscriber, str):
        subscriber = db.session.get(Subscriber, subscriber)
    instance = AutomationInstance(
        automation_id=automation.id, subscriber_id=subscriber.id, business_id=automation.business_id,
        current_step=0, status='active', next_run_at=utcnow(),
        history=[{'event': 'started', 'at': isoformat(utcnow()), **{k: v for k, v in (context or {}).items() if v}}],
    )
    db.session.add(instance)
    db.session.commit()
    process_instance(instance)
    return instance


def evaluate_time_based_triggers():
    """Start time_based automations whose delay has elapsed."""
    started = 0
    for automation in Automation.query.filter_by(trigger_type='time_based', status='active').all():
        try:
            days = parse_time_trigger(automation.trigger_value)
        except ServiceError:
            continue
        now = utcnow()
        delay = timedelta(days=days)
        already = db.select(AutomationInstance.subscriber_id).where(
            AutomationInstance.automation_id == automation.id)
        candidates = Subscriber.query.filter(
            Subscriber.business_id == automation.business_id,
            Subscriber.status == 'active',
            Subscriber.subscribed_at <= now - delay,
            # Only anniversaries after the automation existed (no mass back-fill)
            Subscriber.subscribed_at >= automation.created_at - delay,
            Subscriber.id.notin_(already),
        ).limit(500).all()
        for subscriber in candidates:
            execute_automation(automation, subscriber, context={'trigger': 'time_based'})
            started += 1
    return started


# ----------------------------------------------------------------- execution

def _resolve_target(steps, target, fallback_index):
    if target is None:
        return fallback_index
    if target == END:
        return len(steps)
    for index, step in enumerate(steps):
        if step.get('id') == target or str(step.get('id')) == str(target):
            return index
    return len(steps)  # unknown id ends the workflow


def _record(instance, entry):
    history = list(instance.history or [])
    history.append({'at': isoformat(utcnow()), **entry})
    instance.history = history[-MAX_HISTORY:]


def _complete(instance, status='completed', error=None):
    instance.status = status
    instance.completed_at = utcnow()
    instance.next_run_at = None
    instance.waiting_step = None
    if error:
        instance.error_message = error
    _record(instance, {'event': status, **({'error': error} if error else {})})


def _check_condition(instance, step, subscriber):
    condition = step['condition']
    if condition == 'segment_rules':
        return bool(segment_service.subscriber_matches(subscriber, step.get('rules')))
    last_log = db.session.get(EmailLog, instance.last_email_log_id) if instance.last_email_log_id else None
    opened = bool(last_log and last_log.opened_at)
    clicked = bool(last_log and last_log.clicked_at)
    return {
        'email_opened': opened, 'email_not_opened': not opened,
        'email_clicked': clicked, 'email_not_clicked': not clicked,
    }[condition]


def handle_automation_action(instance, step, subscriber):
    """Execute a non-flow step. Returns a short result for the history."""
    step_type = step['type']
    if step_type == 'send_email':
        template = template_service.get_template(instance.business_id, step['template_id'])
        log = email_service.queue_email(instance.business_id, subscriber, template,
                                        automation_id=instance.automation_id, subject=step.get('subject'))
        db.session.flush()
        instance.last_email_log_id = log.id
        return {'email_log_id': log.id}
    if step_type == 'add_tag':
        subscriber.tags = sorted(set(subscriber.tags or []) | {step['tag'].strip()})
        return {'tag': step['tag']}
    if step_type == 'remove_tag':
        subscriber.tags = sorted(set(subscriber.tags or []) - {step['tag'].strip()})
        return {'tag': step['tag']}
    if step_type == 'update_field':
        field = step['field']
        if field in ('first_name', 'last_name'):
            setattr(subscriber, field, step.get('value'))
        else:
            key = field.split('.', 1)[1] if field.startswith('custom_fields.') else field
            fields = dict(subscriber.custom_fields or {})
            if step.get('value') is None:
                fields.pop(key, None)
            else:
                fields[key] = step.get('value')
            subscriber.custom_fields = fields
        return {'field': field}
    if step_type == 'unsubscribe':
        from app.services.subscriber_service import _apply_status
        _apply_status(subscriber, 'unsubscribed')
        return {}
    raise ServiceError(f'Unknown step type {step_type}')


def process_automation_step(instance, current_step=None):
    """Alias kept for the implementation guide's naming."""
    if current_step is not None:
        instance.current_step = current_step
    return process_instance(instance)


def process_instance(instance):
    """Run steps until the instance has to wait or finishes."""
    automation = instance.automation
    subscriber = instance.subscriber
    if automation is None or subscriber is None:
        _complete(instance, 'failed', 'Automation or subscriber no longer exists')
        db.session.commit()
        return instance
    if automation.status != 'active':
        return instance

    steps = (automation.workflow or {}).get('steps', [])
    try:
        for _ in range(MAX_STEPS_PER_RUN):
            if instance.status != 'active':
                break
            if subscriber.status != 'active':
                _complete(instance, 'completed', f'Subscriber is {subscriber.status}')
                break
            if instance.current_step >= len(steps):
                _complete(instance)
                break

            step = steps[instance.current_step]
            delay = _delay(step) if step['type'] == 'wait' else (
                _delay(step, 'delay_') if step['type'] == 'send_email' else timedelta(0))
            if delay > timedelta(0) and instance.waiting_step != instance.current_step:
                instance.waiting_step = instance.current_step
                instance.next_run_at = utcnow() + delay
                _record(instance, {'step': step['id'], 'type': step['type'], 'event': 'waiting',
                                   'until': isoformat(instance.next_run_at)})
                break
            instance.waiting_step = None

            next_index = instance.current_step + 1
            if step['type'] == 'condition':
                result = _check_condition(instance, step, subscriber)
                _record(instance, {'step': step['id'], 'type': 'condition', 'result': result})
                next_index = _resolve_target(steps, step.get('if_true' if result else 'if_false'), next_index)
            elif step['type'] != 'wait':
                result = handle_automation_action(instance, step, subscriber)
                _record(instance, {'step': step['id'], 'type': step['type'], **result})
            else:
                _record(instance, {'step': step['id'], 'type': 'wait', 'event': 'done'})

            if step['type'] != 'condition' and 'next' in step:
                next_index = _resolve_target(steps, step['next'], next_index)
            instance.current_step = next_index
            instance.next_run_at = utcnow()
        else:
            # Hit the per-run step cap (probably a loop): continue next tick
            instance.next_run_at = utcnow() + timedelta(minutes=1)
        db.session.commit()
    except ServiceError as exc:
        db.session.rollback()
        _complete(instance, 'failed', exc.message)
        db.session.commit()
    except Exception as exc:  # noqa: BLE001
        db.session.rollback()
        logger.exception('Automation instance %s failed', instance.id)
        _complete(instance, 'failed', str(exc))
        db.session.commit()
    return instance


def execute_pending_automations(limit=500):
    """Background job: advance instances whose wait is over."""
    started = evaluate_time_based_triggers()
    due = (AutomationInstance.query.join(Automation)
           .filter(AutomationInstance.status == 'active', AutomationInstance.next_run_at <= utcnow(),
                   Automation.status == 'active')
           .order_by(AutomationInstance.next_run_at).limit(limit).all())
    for instance in due:
        process_instance(instance)
    return {'started': started, 'processed': len(due)}
