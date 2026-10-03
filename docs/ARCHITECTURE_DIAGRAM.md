# Email Marketing Platform - Architecture Diagram

## System Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        CLIENT APPLICATIONS                      │
│  (Web Dashboard / Mobile App / Third-party Integrations)        │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           │ HTTPS/REST API
                           │
┌──────────────────────────▼──────────────────────────────────────┐
│                    NGINX (Reverse Proxy)                        │
│                  SSL/TLS Termination                            │
└──────────────────────────┬──────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────┐
│                    FLASK APPLICATION                            │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │ API Routes Layer                                        │  │
│  │ ├─ Auth (login, register)                              │  │
│  │ ├─ Businesses (CRUD, settings)                         │  │
│  │ ├─ Subscribers (CRUD, import, export)                  │  │
│  │ ├─ Templates (CRUD, preview)                           │  │
│  │ ├─ Campaigns (CRUD, send, schedule)                    │  │
│  │ ├─ Automations (CRUD, trigger management)              │  │
│  │ ├─ Segments (CRUD, filtering)                          │  │
│  │ └─ Analytics (metrics, reporting)                      │  │
│  └─────────────────────────────────────────────────────────┘  │
│                           │                                     │
│  ┌────────────────────────▼────────────────────────────────┐  │
│  │ Service Layer                                           │  │
│  │ ├─ EmailService (core email logic)                     │  │
│  │ ├─ SMTPService (SMTP connection pool)                  │  │
│  │ ├─ CampaignService (campaign management)               │  │
│  │ ├─ AutomationService (workflow engine)                 │  │
│  │ ├─ AnalyticsService (metrics calculation)              │  │
│  │ ├─ SubscriberService (subscriber management)           │  │
│  │ └─ TemplateService (template rendering)                │  │
│  └─────────────────────────────────────────────────────────┘  │
│                           │                                     │
│  ┌────────────────────────▼────────────────────────────────┐  │
│  │ Data Layer (SQLAlchemy ORM)                             │  │
│  │ ├─ Business model                                       │  │
│  │ ├─ Subscriber model                                     │  │
│  │ ├─ Campaign model                                       │  │
│  │ ├─ EmailTemplate model                                  │  │
│  │ ├─ Automation model                                     │  │
│  │ ├─ EmailLog model                                       │  │
│  │ └─ Segment model                                        │  │
│  └─────────────────────────────────────────────────────────┘  │
└──────────────────────────┬──────────────────────────────────────┘
                           │
        ┌──────────────────┼──────────────────┐
        │                  │                  │
        │                  │                  │
┌───────▼────────┐ ┌──────▼──────┐ ┌────────▼─────────┐
│  PostgreSQL    │ │ Redis Cache │ │  File Storage    │
│  Database      │ │ (Optional)  │ │  (Temp/Logs)     │
│                │ │             │ │                  │
│ - Businesses   │ │ - Queue     │ │ - Logs           │
│ - Subscribers  │ │ - Sessions  │ │ - Exports        │
│ - Campaigns    │ │ - Cache     │ │                  │
│ - Templates    │ │             │ │                  │
│ - Automations  │ │             │ │                  │
│ - Email Logs   │ │             │ │                  │
│ - Segments     │ │             │ │                  │
└────────────────┘ └─────────────┘ └──────────────────┘


┌──────────────────────────────────────────────────────────────────┐
│              BACKGROUND TASK PROCESSOR (APScheduler)             │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │ Scheduled Tasks                                            │ │
│  │ ├─ Email Queue Processor (every 10 seconds)               │ │
│  │ │  └─ Connects to SMTP & sends queued emails              │ │
│  │ ├─ Automation Executor (every 30 seconds)                 │ │
│  │ │  └─ Evaluates triggers & executes workflows             │ │
│  │ ├─ Analytics Calculator (every 5 minutes)                 │ │
│  │ │  └─ Aggregates metrics & updates campaign stats         │ │
│  │ ├─ Bounce Processor (every hour)                          │ │
│  │ │  └─ Marks unsubscribes & failed emails                  │ │
│  │ ├─ Cleanup Job (daily at 2 AM)                            │ │
│  │ │  └─ Archives old logs & deletes expired data            │ │
│  │ └─ Daily Limit Reset (daily at 12 AM)                     │ │
│  │    └─ Resets daily email send counters                    │ │
│  └────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────┘
                           │
        ┌──────────────────┼──────────────────┐
        │                  │                  │
        │                  │                  │
┌───────▼────────┐ ┌──────▼──────┐ ┌────────▼─────────┐
│  SMTP Servers  │ │ Webhooks    │ │ Tracking Pixels  │
│  (per business)│ │ (future)    │ │ & Click Links    │
│                │ │             │ │                  │
│ - Gmail        │ │ - Opens     │ │ - Open Tracking  │
│ - SendGrid     │ │ - Clicks    │ │ - Click Tracking │
│ - Custom SMTP  │ │ - Bounces   │ │ - Log to DB      │
│                │ │             │ │                  │
└────────────────┘ └─────────────┘ └──────────────────┘
```

---

## Data Flow Diagrams

### Campaign Send Flow
```
User Creates Campaign
        │
        ▼
Validate Template & Recipients
        │
        ▼
Create Campaign Record (status: draft)
        │
        ▼
User Clicks "Send Now" or "Schedule"
        │
        ├─── If "Send Now" ───┐
        │                    │
        │              Check Daily Limit
        │                    │
        └─────────────────────┤
                             │
                        ✓ Limit OK?
                             │
                             ▼
                  Get Recipient Segment
                             │
                             ▼
              Create Email Queue Entries
         (one per subscriber, status: pending)
                             │
                             ▼
            Update Campaign Status: "sending"
                             │
                             ▼
        Background Task: Email Queue Processor
                    (runs every 10 sec)
                             │
          ┌──────────────────┼──────────────────┐
          │                  │                  │
    Get Pending Emails   Rate Limit Check   SMTP Send
          │                  │                  │
          └──────────────────┼──────────────────┘
                             │
                             ▼
                    Log Email Send
              (email_logs table, status: sent)
                             │
                             ▼
              Email Reaches Subscriber
                             │
          ┌──────────────────┴──────────────────┐
          │                                     │
    Subscriber Opens Email          Subscriber Clicks Link
          │                                     │
          ▼                                     ▼
    Tracking Pixel Loaded              Click Redirect Hit
          │                                     │
          ▼                                     ▼
    Log Email Open                   Log Email Click
    (email_logs.opened_at)        (email_logs.clicked_at)
          │                                     │
          └──────────────────┬──────────────────┘
                             │
                    Update Campaign Analytics
                  (open_rate, click_rate, etc)
```

### Automation Workflow Execution Flow
```
Trigger Event Occurs
   (e.g., new subscriber)
        │
        ▼
Background Task: Automation Executor
   (runs every 30 seconds)
        │
        ▼
Query All Active Automations
        │
        ▼
For Each Matching Automation:
        │
    ├─ Create automation_instance
    ├─ Set current_step = 0
    └─ status = 'active'
        │
        ▼
Process First Action
        │
    ├─ If "Send Email":
    │   └─ Create email queue entry
    │
    ├─ If "Wait X days":
    │   └─ Set next_check_time = now + X days
    │
    ├─ If "Add to Segment":
    │   └─ Link subscriber to segment
    │
    └─ Move to next step
        │
        ▼
Check Conditions
        │
    ├─ If "Email opened":
    │   ├─ Check if opened
    │   ├─ If yes: Execute action
    │   └─ If no: Wait for next check
    │
    └─ If "Time passed":
        └─ Check elapsed time
        │   ├─ If done: Execute action
        │   └─ If not: Wait
        │
        ▼
Mark Complete
   (automation_instance.status = 'completed')
```

### Analytics Update Flow
```
Email Sent / Opened / Clicked
        │
        ▼
Log Event to email_logs
        │
        ▼
Background Task: Analytics Calculator
   (runs every 5 minutes)
        │
        ▼
Query Recent Email Log Changes
        │
        ▼
Group by campaign_id
        │
        ▼
Calculate Metrics:
   ├─ total_sent
   ├─ total_opens (unique opens)
   ├─ total_clicks (unique clicks)
   ├─ open_rate (opens / sent * 100)
   └─ click_rate (clicks / sent * 100)
        │
        ▼
Update Campaign Table
   (campaigns.total_opens, etc)
        │
        ▼
Calculate Subscriber Engagement Scores
        │
        ▼
Cache Results for API Calls
```

---

## Database Relationships

```
businesses (1) ─────── (many) subscribers
    │
    ├── (1) ─── (many) email_templates
    │
    ├── (1) ─── (many) campaigns
    │               │
    │               └── (1) ─── (many) email_logs
    │
    ├── (1) ─── (many) automations
    │               │
    │               └── (1) ─── (many) automation_instances
    │                               └── (many) subscribers
    │
    ├── (1) ─── (many) segments
    │
    └── (1) ─── (many) email_logs

email_templates ────── campaigns
    │
    └── (1) ─── (many) email_logs
```

---

## Request/Response Flow

### Example: Send Campaign API

```
Request:
POST /api/campaigns/abc123/send
Authorization: Bearer <jwt-token>
{
  "segment_id": "seg456"
}

↓ (Flask processes)

1. Extract JWT → Get business_id
2. Validate campaign exists & belongs to business
3. Get segment subscribers
4. Create email_logs entries (status: pending)
5. Update campaign (status: sending, total_recipients: count)
6. Return response

Response:
{
  "success": true,
  "campaign_id": "abc123",
  "recipients_queued": 150,
  "message": "Campaign queued for sending"
}

↓ (Background task processes)

1. Email Queue Processor runs every 10 seconds
2. Gets all pending email_logs entries
3. For each: fetch subscriber, template, business SMTP config
4. Send via SMTP
5. Update email_logs (status: sent, sent_at: timestamp)
6. Log any errors

↓ (Email arrives)

1. Subscriber opens email
2. Tracking pixel loaded from /t/pixel?email_log_id=xyz
3. Hit /api/tracking/open endpoint
4. Update email_logs (opened_at: timestamp)
5. Background task aggregates opens into campaign stats
6. Dashboard shows real-time open rate
```

---

## Multi-Tenancy Security

```
User Authentication
        │
        ▼
Login with email + password
        │
        ▼
Validate & Generate JWT
   {
     "business_id": "biz123",
     "email": "user@company.com",
     "exp": 1234567890
   }
        │
        ▼
Token Sent to Client
        │
        ▼
Each API Request Includes Token
        │
        ▼
Flask Decorator: @require_auth
        │
        ├─ Extract & validate JWT
        ├─ Get business_id from token
        ├─ Check resource ownership
        │  (WHERE business_id = token.business_id)
        └─ Allow/deny request
```

This architecture ensures:
✓ Complete isolation between businesses
✓ Scalable background task processing
✓ Real-time analytics updates
✓ Reliable email delivery queue
✓ Automated workflow execution
✓ Clean separation of concerns
