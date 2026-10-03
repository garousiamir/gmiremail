# Email Marketing Platform - Quick Reference for Claude Code

## Files to Create (In Order)

### Configuration & Setup (Phase 1)
1. ✅ `requirements.txt` - Dependencies
2. ✅ `.env.example` - Environment template
3. ✅ `app/config.py` - Configuration classes
4. ✅ `app/__init__.py` - Application factory

### Database Models (Phase 2)
5. ✅ `app/models/__init__.py` - Model exports
6. ✅ `app/models/business.py` - Business/tenant model
7. ✅ `app/models/subscriber.py` - Subscriber model
8. ✅ `app/models/email_template.py` - Template model
9. ✅ `app/models/campaign.py` - Campaign model
10. ✅ `app/models/email_log.py` - Email log model
11. ✅ `app/models/automation.py` - Automation model
12. ✅ `app/models/automation_instance.py` - Automation instance model
13. ✅ `app/models/segment.py` - Segment model

### Services (Phases 3-10)
14. ✅ `app/utils/decorators.py` - JWT decorator
15. ✅ `app/utils/validators.py` - Email validators
16. ✅ `app/utils/helpers.py` - Utility functions
17. ✅ `app/services/email_service.py` - Email sending
18. ✅ `app/services/smtp_service.py` - SMTP connection
19. ✅ `app/services/campaign_service.py` - Campaign logic
20. ✅ `app/services/automation_service.py` - Automation logic
21. ✅ `app/services/subscriber_service.py` - Subscriber logic
22. ✅ `app/services/template_service.py` - Template rendering
23. ✅ `app/services/segment_service.py` - Segmentation logic
24. ✅ `app/services/analytics_service.py` - Analytics logic

### API Routes (Phases 3-10)
25. ✅ `app/routes/__init__.py` - Routes init
26. ✅ `app/routes/auth.py` - Auth endpoints
27. ✅ `app/routes/businesses.py` - Business endpoints
28. ✅ `app/routes/subscribers.py` - Subscriber endpoints
29. ✅ `app/routes/campaigns.py` - Campaign endpoints (includes tracking)
30. ✅ `app/routes/templates.py` - Template endpoints
31. ✅ `app/routes/automations.py` - Automation endpoints
32. ✅ `app/routes/segments.py` - Segment endpoints
33. ✅ `app/routes/analytics.py` - Analytics endpoints

### Background Tasks (Phase 11)
34. ✅ `app/tasks/__init__.py` - Tasks init
35. ✅ `app/tasks/scheduled_tasks.py` - Background job definitions

### Entry Point (Phase 12)
36. ✅ `app.py` - Main application file
37. ✅ `.gitignore` - Git ignore patterns

---

## API Endpoint Summary

### Authentication
```
POST /api/auth/register
POST /api/auth/login
POST /api/auth/refresh
```

### Businesses
```
GET /api/businesses/me
PUT /api/businesses/me
GET /api/businesses/stats
```

### Subscribers
```
POST /api/subscribers
POST /api/subscribers/bulk
GET /api/subscribers
GET /api/subscribers/:id
PUT /api/subscribers/:id
DELETE /api/subscribers/:id
PUT /api/subscribers/:id/status
POST /api/subscribers/export
```

### Templates
```
POST /api/templates
GET /api/templates
GET /api/templates/:id
PUT /api/templates/:id
DELETE /api/templates/:id
POST /api/templates/:id/preview
```

### Campaigns
```
POST /api/campaigns
GET /api/campaigns
GET /api/campaigns/:id
PUT /api/campaigns/:id
DELETE /api/campaigns/:id
POST /api/campaigns/:id/send
POST /api/campaigns/:id/schedule
POST /api/campaigns/:id/pause
POST /api/campaigns/:id/resume
GET /api/campaigns/:id/analytics
```

### Automations
```
POST /api/automations
GET /api/automations
GET /api/automations/:id
PUT /api/automations/:id
DELETE /api/automations/:id
POST /api/automations/:id/activate
POST /api/automations/:id/deactivate
```

### Segments
```
POST /api/segments
GET /api/segments
GET /api/segments/:id
PUT /api/segments/:id
DELETE /api/segments/:id
GET /api/segments/:id/count
```

### Analytics
```
GET /api/analytics/overview
GET /api/analytics/engagement
GET /api/analytics/subscribers
GET /api/analytics/campaigns
GET /api/analytics/email-logs
```

### Tracking
```
GET /t/pixel?email_log_id=xxx
GET /t/click?email_log_id=xxx&url=xxx
```

---

## Database Tables at a Glance

| Table | Purpose | Key Columns |
|-------|---------|------------|
| businesses | Tenant/business info | id, name, smtp_host, api_key |
| subscribers | Contact list | id, business_id, email, status |
| email_templates | Email designs | id, business_id, name, html_content |
| campaigns | Email campaigns | id, business_id, template_id, status |
| email_logs | Send tracking | id, campaign_id, subscriber_id, status |
| automations | Workflow definitions | id, business_id, trigger_type, workflow |
| automation_instances | Active workflows | id, automation_id, subscriber_id, status |
| segments | Subscriber groups | id, business_id, name, filter_rules |

---

## Critical Implementation Details

### Multi-Tenancy Security
```python
# ALWAYS include in queries:
query = Model.query.filter_by(business_id=request.business_id)

# ALWAYS validate ownership before modifying:
if resource.business_id != request.business_id:
    return error_response, 403
```

### Email Sending Flow
```
1. Campaign.send() created in DB
2. Email logs queued (status: pending)
3. Background task: process_email_queue()
   - Get pending logs
   - Connect to SMTP
   - Send email
   - Update status: sent
4. Subscriber receives email
5. Open/click tracked via pixels/redirects
6. Analytics updated every 5 minutes
```

### Automation Workflow Format
```json
{
  "steps": [
    {
      "id": 1,
      "type": "send_email",
      "template_id": "xxx",
      "delay_days": 0
    },
    {
      "id": 2,
      "type": "wait",
      "days": 2
    },
    {
      "id": 3,
      "type": "condition",
      "condition": "email_opened",
      "if_true": 4,
      "if_false": 5
    },
    {
      "id": 4,
      "type": "send_email",
      "template_id": "yyy"
    }
  ]
}
```

### Segmentation Filter Format
```json
{
  "rules": [
    {
      "field": "status",
      "operator": "equals",
      "value": "active"
    },
    {
      "field": "custom_field_1",
      "operator": "contains",
      "value": "example"
    }
  ],
  "logic": "AND"
}
```

### JWT Token Format
```python
{
  "business_id": "uuid-here",
  "email": "user@business.com",
  "iat": 1234567890,
  "exp": 1234568790  # 15 minutes
}
```

---

## Background Tasks Schedule

| Task | Frequency | Purpose |
|------|-----------|---------|
| process_email_queue | Every 10 seconds | Send queued emails |
| execute_pending_automations | Every 30 seconds | Run workflow steps |
| calculate_analytics | Every 5 minutes | Update campaign metrics |
| process_bounces | Every hour | Handle failed emails |
| cleanup_old_data | Daily @ 2 AM | Archive/delete old logs |
| reset_daily_limits | Daily @ 12 AM | Reset send counters |

---

## Key Service Methods (Template)

### EmailService
```python
send_email(business_id, recipient, subject, html, text)
queue_email(campaign_id, subscriber_id, email_log_id)
process_email_queue() # Background task
get_smtp_connection(business) # With pooling
```

### CampaignService
```python
create_campaign(business_id, template_id, segment_id, name)
send_campaign_now(business_id, campaign_id)
schedule_campaign(business_id, campaign_id, scheduled_time)
get_campaign_analytics(campaign_id)
create_email_logs_from_segment(campaign_id, segment_id)
```

### AutomationService
```python
create_automation(business_id, name, trigger_type, workflow)
evaluate_trigger(trigger_type, trigger_value, subscriber_id)
execute_automation(automation_id, subscriber_id)
process_automation_step(automation_instance, step_num)
```

### AnalyticsService
```python
get_business_overview(business_id) # Dashboard
calculate_campaign_metrics(campaign_id)
get_engagement_metrics(business_id)
calculate_engagement_score(subscriber_id)
```

---

## Testing Scenarios

1. **Register Business**
   - Create account with email/password
   - Verify API key generated
   - Login and get JWT token

2. **Add Subscribers**
   - Add single subscriber
   - Bulk import CSV (100 records)
   - Verify duplicates handled
   - Update subscriber custom fields

3. **Create Campaign**
   - Create email template with variables
   - Create segment with filters
   - Create campaign targeting segment
   - Send campaign now
   - Verify emails queued

4. **Track Email**
   - Open tracking pixel loaded
   - Click tracking link redirected
   - Analytics updated
   - Campaign shows open rate

5. **Automation**
   - Create new-subscriber automation
   - New subscriber added
   - Welcome email sent automatically
   - Automation instance created and tracked

6. **Analytics**
   - Dashboard shows correct totals
   - Campaign metrics accurate
   - Engagement scores calculated
   - Export to CSV works

---

## Common Errors & Solutions

| Error | Cause | Solution |
|-------|-------|----------|
| 401 Unauthorized | Missing/invalid JWT | Check token in Authorization header |
| 403 Forbidden | Business ID mismatch | Verify resource belongs to business_id in token |
| 404 Not Found | Resource doesn't exist | Check ID is correct UUID |
| 500 SMTP Error | Bad SMTP credentials | Verify smtp_host, smtp_port, username, password |
| Email not sent | No pending queue entries | Check email_logs table has entries with status='pending' |
| Analytics incorrect | Calculation not run | Check background task is running |

---

## Performance Optimization Tips

1. **Database Indexing:**
   - Add index on (business_id, status) for frequent filters
   - Add index on sent_at for analytics

2. **Email Queue:**
   - Process in batches of MAX_EMAIL_BATCH_SIZE
   - Use connection pooling for SMTP

3. **API Response:**
   - Paginate list endpoints (20-50 per page)
   - Cache business settings for 5 minutes

4. **Analytics:**
   - Run heavy calculations in background task
   - Store aggregated results, not raw calculations

---

## Deployment Checklist

- [ ] Set SECRET_KEY to strong random value
- [ ] Set JWT_SECRET_KEY to strong random value
- [ ] Configure DATABASE_URL with production database
- [ ] Configure SMTP credentials for production
- [ ] Set FLASK_ENV=production
- [ ] Disable FLASK_DEBUG
- [ ] Configure SSL certificate
- [ ] Set up nginx reverse proxy
- [ ] Create systemd service
- [ ] Enable automatic startup
- [ ] Set up database backups
- [ ] Monitor error logs
- [ ] Test email sending with real account
- [ ] Verify SSL certificate works
- [ ] Load test with concurrent users

---

## File Structure After Completion

```
email-marketing-platform/
├── app.py
├── .env.example
├── requirements.txt
├── .gitignore
├── app/
│   ├── __init__.py
│   ├── config.py
│   ├── models/
│   │   ├── __init__.py
│   │   ├── business.py
│   │   ├── subscriber.py
│   │   ├── email_template.py
│   │   ├── campaign.py
│   │   ├── email_log.py
│   │   ├── automation.py
│   │   ├── automation_instance.py
│   │   └── segment.py
│   ├── services/
│   │   ├── __init__.py
│   │   ├── email_service.py
│   │   ├── smtp_service.py
│   │   ├── campaign_service.py
│   │   ├── automation_service.py
│   │   ├── subscriber_service.py
│   │   ├── template_service.py
│   │   ├── segment_service.py
│   │   └── analytics_service.py
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── auth.py
│   │   ├── businesses.py
│   │   ├── subscribers.py
│   │   ├── campaigns.py
│   │   ├── templates.py
│   │   ├── automations.py
│   │   ├── segments.py
│   │   └── analytics.py
│   ├── tasks/
│   │   ├── __init__.py
│   │   └── scheduled_tasks.py
│   └── utils/
│       ├── __init__.py
│       ├── decorators.py
│       ├── validators.py
│       └── helpers.py
├── migrations/
├── tests/
└── docs/
    ├── EMAIL_MARKETING_INFRASTRUCTURE_SPEC.md
    ├── ARCHITECTURE_DIAGRAM.md
    ├── IMPLEMENTATION_GUIDE.md
    └── QUICK_REFERENCE.md
```

---

This is everything Claude Code needs to build your complete email marketing platform!
