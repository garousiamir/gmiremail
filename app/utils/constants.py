SUBSCRIBER_STATUSES = {'active', 'inactive', 'bounced', 'unsubscribed'}

CAMPAIGN_STATUSES = {'draft', 'scheduled', 'sending', 'sent', 'paused'}
CAMPAIGN_EDITABLE_STATUSES = {'draft', 'scheduled', 'paused'}

# 'sending' = claimed by a queue worker; 'failed' = gave up without a bounce
EMAIL_LOG_STATUSES = {'pending', 'sending', 'sent', 'delivered', 'bounced', 'opened', 'clicked', 'failed'}
# Engagement order: a log never moves "backwards" (e.g. clicked -> opened)
EMAIL_LOG_PROGRESSION = {'pending': 0, 'sent': 1, 'delivered': 2, 'opened': 3, 'clicked': 4}

AUTOMATION_TRIGGERS = {'new_subscriber', 'email_opened', 'email_clicked', 'custom_event', 'time_based'}
AUTOMATION_STATUSES = {'active', 'paused', 'inactive'}
AUTOMATION_INSTANCE_STATUSES = {'active', 'completed', 'paused', 'failed'}
AUTOMATION_STEP_TYPES = {
    'send_email', 'wait', 'condition', 'add_tag', 'remove_tag',
    'update_field', 'unsubscribe',
}
AUTOMATION_CONDITIONS = {'email_opened', 'email_not_opened', 'email_clicked', 'email_not_clicked', 'segment_rules'}

SEGMENT_OPERATORS = {
    'equals', 'not_equals', 'contains', 'not_contains', 'starts_with', 'ends_with',
    'greater_than', 'less_than', 'greater_or_equal', 'less_or_equal',
    'in', 'not_in', 'is_set', 'is_not_set', 'before', 'after', 'within_last_days',
}
SEGMENT_LOGIC = {'AND', 'OR'}

# Fields stored as real columns on the subscribers table
SUBSCRIBER_COLUMN_FIELDS = {
    'email', 'first_name', 'last_name', 'status', 'subscribed_at', 'created_at',
    'updated_at', 'unsubscribed_at', 'total_opens', 'total_clicks', 'last_opened_at',
    'last_clicked_at', 'engagement_score', 'bounce_count',
}
SUBSCRIBER_DATE_FIELDS = {
    'subscribed_at', 'created_at', 'updated_at', 'unsubscribed_at',
    'last_opened_at', 'last_clicked_at',
}

# Updatable business settings (smtp_password is write-only)
BUSINESS_UPDATABLE_FIELDS = {
    'name', 'email_from', 'email_from_name', 'sender_domain', 'physical_address',
    'smtp_host', 'smtp_port', 'smtp_username', 'smtp_password', 'smtp_tls',
    'daily_email_limit',
}
