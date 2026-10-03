# Multi-Tenant Email Marketing Infrastructure - Complete Specification

## Project Overview
A production-ready, self-hosted email marketing platform for managing multiple businesses/brands with complete automation, analytics, and campaign management capabilities.

---

## 1. SYSTEM ARCHITECTURE

### Technology Stack
- **Backend:** Python Flask
- **Database:** PostgreSQL
- **Task Scheduler:** APScheduler
- **Email Sending:** SMTP (native Python smtplib)
- **Authentication:** JWT tokens
- **API:** RESTful endpoints

### Core Modules
```
email_marketing_platform/
├── app.py                    # Flask application entry point
├── config.py                 # Configuration management
├── requirements.txt          # Python dependencies
├── .env.example              # Environment variables template
│
├── models/
│   ├── __init__.py
│   ├── business.py           # Business/Tenant model
│   ├── subscriber.py         # Subscriber/Contact model
│   ├── campaign.py           # Campaign model
│   ├── email_template.py     # Email template model
│   ├── automation.py         # Automation workflow model
│   ├── email_log.py          # Email sending log/analytics
│   └── segment.py            # Subscriber segment model
│
├── services/
│   ├── __init__.py
│   ├── email_service.py      # Core email sending service
│   ├── smtp_service.py       # SMTP connection manager
│   ├── campaign_service.py   # Campaign management logic
│   ├── automation_service.py # Automation workflow engine
│   ├── analytics_service.py  # Metrics & reporting
│   ├── subscriber_service.py # Subscriber management
│   └── template_service.py   # Template rendering
│
├── routes/
│   ├── __init__.py
│   ├── auth.py               # Authentication endpoints
│   ├── businesses.py         # Business management
│   ├── subscribers.py        # Subscriber CRUD
│   ├── campaigns.py          # Campaign management
│   ├── templates.py          # Email template management
│   ├── automations.py        # Automation setup
│   ├── segments.py           # Segmentation
│   └── analytics.py          # Analytics & metrics
│
├── tasks/
│   ├── __init__.py
│   └── scheduled_tasks.py    # Background job definitions
│
├── utils/
│   ├── __init__.py
│   ├── decorators.py         # JWT auth decorators
│   ├── validators.py         # Email/data validation
│   ├── helpers.py            # Utility functions
│   └── constants.py          # App constants
│
├── migrations/               # Database migration files
└── tests/                    # Unit & integration tests
```

---

## 2. DATABASE SCHEMA

### Table: businesses
```sql
CREATE TABLE businesses (
    id UUID PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    email_from VARCHAR(255) NOT NULL,
    email_from_name VARCHAR(255),
    sender_domain VARCHAR(255) NOT NULL,
    api_key VARCHAR(255) UNIQUE NOT NULL,
    smtp_host VARCHAR(255) NOT NULL,
    smtp_port INTEGER NOT NULL,
    smtp_username VARCHAR(255) NOT NULL,
    smtp_password VARCHAR(255) NOT NULL,
    smtp_tls BOOLEAN DEFAULT TRUE,
    daily_email_limit INTEGER DEFAULT 10000,
    emails_sent_today INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### Table: subscribers
```sql
CREATE TABLE subscribers (
    id UUID PRIMARY KEY,
    business_id UUID NOT NULL REFERENCES businesses(id),
    email VARCHAR(255) NOT NULL,
    first_name VARCHAR(255),
    last_name VARCHAR(255),
    status ENUM('active', 'inactive', 'bounced', 'unsubscribed') DEFAULT 'active',
    custom_fields JSONB DEFAULT '{}',
    subscribed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(business_id, email),
    INDEX idx_business_status (business_id, status),
    INDEX idx_email (email)
);
```

### Table: email_templates
```sql
CREATE TABLE email_templates (
    id UUID PRIMARY KEY,
    business_id UUID NOT NULL REFERENCES businesses(id),
    name VARCHAR(255) NOT NULL,
    subject_line VARCHAR(500) NOT NULL,
    preview_text VARCHAR(255),
    html_content TEXT NOT NULL,
    text_content TEXT,
    template_variables JSONB DEFAULT '[]',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(business_id, name)
);
```

### Table: campaigns
```sql
CREATE TABLE campaigns (
    id UUID PRIMARY KEY,
    business_id UUID NOT NULL REFERENCES businesses(id),
    template_id UUID NOT NULL REFERENCES email_templates(id),
    name VARCHAR(255) NOT NULL,
    status ENUM('draft', 'scheduled', 'sending', 'sent', 'paused') DEFAULT 'draft',
    segment_id UUID REFERENCES segments(id),
    scheduled_time TIMESTAMP,
    send_time TIMESTAMP,
    total_recipients INTEGER DEFAULT 0,
    total_sent INTEGER DEFAULT 0,
    total_opens INTEGER DEFAULT 0,
    total_clicks INTEGER DEFAULT 0,
    total_bounces INTEGER DEFAULT 0,
    total_unsubscribes INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_business_status (business_id, status)
);
```

### Table: automations
```sql
CREATE TABLE automations (
    id UUID PRIMARY KEY,
    business_id UUID NOT NULL REFERENCES businesses(id),
    name VARCHAR(255) NOT NULL,
    trigger_type ENUM('new_subscriber', 'email_opened', 'email_clicked', 'custom_event', 'time_based') NOT NULL,
    trigger_value VARCHAR(255),
    status ENUM('active', 'paused', 'inactive') DEFAULT 'active',
    workflow JSONB NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### Table: automation_instances
```sql
CREATE TABLE automation_instances (
    id UUID PRIMARY KEY,
    automation_id UUID NOT NULL REFERENCES automations(id),
    subscriber_id UUID NOT NULL REFERENCES subscribers(id),
    current_step INTEGER DEFAULT 0,
    status ENUM('active', 'completed', 'paused') DEFAULT 'active',
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### Table: email_logs
```sql
CREATE TABLE email_logs (
    id UUID PRIMARY KEY,
    business_id UUID NOT NULL REFERENCES businesses(id),
    campaign_id UUID REFERENCES campaigns(id),
    subscriber_id UUID NOT NULL REFERENCES subscribers(id),
    recipient_email VARCHAR(255) NOT NULL,
    subject_line VARCHAR(500),
    status ENUM('pending', 'sent', 'delivered', 'bounced', 'opened', 'clicked') DEFAULT 'pending',
    sent_at TIMESTAMP,
    opened_at TIMESTAMP,
    clicked_at TIMESTAMP,
    bounced_at TIMESTAMP,
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_business_campaign (business_id, campaign_id),
    INDEX idx_subscriber_status (subscriber_id, status),
    INDEX idx_sent_at (sent_at)
);
```

### Table: segments
```sql
CREATE TABLE segments (
    id UUID PRIMARY KEY,
    business_id UUID NOT NULL REFERENCES businesses(id),
    name VARCHAR(255) NOT NULL,
    description TEXT,
    filter_rules JSONB NOT NULL,
    subscriber_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(business_id, name)
);
```

---

## 3. API ENDPOINTS

### Authentication
- `POST /api/auth/register` - Register new business
- `POST /api/auth/login` - Login and get JWT token
- `POST /api/auth/refresh` - Refresh JWT token

### Business Management
- `GET /api/businesses/me` - Get current business details
- `PUT /api/businesses/me` - Update business settings
- `GET /api/businesses/stats` - Get business overview stats

### Subscribers
- `POST /api/subscribers` - Add single subscriber
- `POST /api/subscribers/bulk` - Bulk import subscribers (CSV/JSON)
- `GET /api/subscribers` - List subscribers (paginated, filtered)
- `GET /api/subscribers/:id` - Get subscriber details
- `PUT /api/subscribers/:id` - Update subscriber
- `DELETE /api/subscribers/:id` - Delete subscriber
- `POST /api/subscribers/export` - Export subscribers to CSV
- `PUT /api/subscribers/:id/status` - Change subscriber status

### Email Templates
- `POST /api/templates` - Create template
- `GET /api/templates` - List templates
- `GET /api/templates/:id` - Get template details
- `PUT /api/templates/:id` - Update template
- `DELETE /api/templates/:id` - Delete template
- `POST /api/templates/:id/preview` - Preview template with sample data

### Campaigns
- `POST /api/campaigns` - Create campaign
- `GET /api/campaigns` - List campaigns
- `GET /api/campaigns/:id` - Get campaign details
- `PUT /api/campaigns/:id` - Update campaign
- `DELETE /api/campaigns/:id` - Delete campaign
- `POST /api/campaigns/:id/send` - Send campaign immediately
- `POST /api/campaigns/:id/schedule` - Schedule campaign for later
- `POST /api/campaigns/:id/pause` - Pause sending
- `POST /api/campaigns/:id/resume` - Resume sending
- `GET /api/campaigns/:id/analytics` - Get campaign analytics

### Automations
- `POST /api/automations` - Create automation workflow
- `GET /api/automations` - List automations
- `GET /api/automations/:id` - Get automation details
- `PUT /api/automations/:id` - Update automation
- `DELETE /api/automations/:id` - Delete automation
- `POST /api/automations/:id/activate` - Activate automation
- `POST /api/automations/:id/deactivate` - Deactivate automation

### Segments
- `POST /api/segments` - Create segment
- `GET /api/segments` - List segments
- `GET /api/segments/:id` - Get segment details
- `PUT /api/segments/:id` - Update segment
- `DELETE /api/segments/:id` - Delete segment
- `GET /api/segments/:id/count` - Get subscriber count in segment

### Analytics
- `GET /api/analytics/overview` - Dashboard overview metrics
- `GET /api/analytics/engagement` - Engagement metrics
- `GET /api/analytics/subscribers` - Subscriber growth chart
- `GET /api/analytics/campaigns` - Campaign performance comparison
- `GET /api/analytics/email-logs` - Raw email sending logs

---

## 4. CORE FEATURES

### A. Email Sending Engine
- Direct SMTP connection (no 3rd party dependency)
- Support for multiple SMTP providers per business
- Connection pooling and retry logic
- Email validation before sending
- Unsubscribe link injection
- List-Unsubscribe header
- Bounce handling
- Rate limiting (respect daily limits)
- Error logging and recovery

### B. Campaign Management
- **Drafting:** Create campaigns with templates
- **Scheduling:** Schedule sends for specific date/time
- **Segmentation:** Send to specific subscriber segments
- **A/B Testing:** Support subject line variations
- **Personalization:** Variable substitution ({{first_name}}, etc.)
- **Pause/Resume:** Pause ongoing campaigns and resume
- **Real-time tracking:** Monitor sends, opens, clicks

### C. Automation Workflows
**Triggers:**
- New subscriber joins
- Email opened
- Email clicked
- Time-based (X days after event)
- Custom event

**Actions:**
- Send email (immediate or delayed)
- Add/remove from segment
- Update custom field
- Tag subscriber
- Unsubscribe

**Example Workflow:**
```
Trigger: New Subscriber
├─ Action 1: Send welcome email (immediate)
├─ Action 2: Wait 2 days
├─ Condition: If email not opened
│  └─ Action: Send follow-up reminder
├─ Action 3: Wait 5 days
└─ Action 4: Send second email
```

### D. Subscriber Management
- Manual add/import
- Bulk CSV/JSON import with validation
- Custom fields (name, email, phone, custom data)
- Status management (active, inactive, bounced, unsubscribed)
- Segment creation based on filters
- Automatic unsubscribe handling
- Duplicate detection
- Export to CSV

### E. Analytics & Metrics
**Real-time Dashboards:**
- Total subscribers
- Campaigns sent
- Open rate
- Click rate
- Bounce rate
- Unsubscribe rate

**Campaign-level Analytics:**
- Unique opens
- Click-through rate
- Best performing links
- Timing of opens/clicks
- Subscriber engagement score

**Subscriber-level Analytics:**
- Last email opened date
- Total opens
- Total clicks
- Engagement score
- Lifetime value indicators

### F. Template Management
- WYSIWYG-friendly HTML templates
- Variable support ({{variable_name}})
- Template preview with sample data
- Template library with defaults
- Mobile responsive templates
- Dark mode considerations

### G. Segmentation
- Create segments based on:
  - Subscriber status
  - Custom fields
  - Engagement level
  - Campaign history
  - Time-based filters
- Dynamic segment updates
- Segment preview (see how many subscribers match)

---

## 5. KEY BUSINESS LOGIC

### Multi-Tenancy
- Each business is completely isolated (business_id on all tables)
- No cross-business data leakage
- Each business has own SMTP configuration
- API key-based authentication

### Email Sending Flow
1. Campaign creation/scheduling
2. Validate template and recipients
3. Check daily limit
4. Queue emails for sending
5. Background task processes queue
6. Log each send attempt
7. Track open/click via tracking pixels/links
8. Update metrics

### Bounce Handling
- Hard bounces (invalid email) → mark unsubscribed
- Soft bounces (temporary issue) → retry with backoff
- Track bounce reasons
- Auto-remove after X bounces

### Unsubscribe Flow
- Include "List-Unsubscribe" header with email address
- Support mailto: unsubscribe link
- Support web-based unsubscribe link (redirects to endpoint)
- Mark subscriber as unsubscribed
- Log unsubscribe timestamp

### Rate Limiting
- Per-business daily email limit
- Per-minute sending limit to avoid ISP throttling
- Exponential backoff on failures
- Queue prioritization

---

## 6. IMPLEMENTATION STEPS

### Phase 1: Core Infrastructure
1. Set up Flask app with configuration
2. PostgreSQL database setup
3. SQLAlchemy models
4. Database migrations

### Phase 2: Authentication & Business Management
1. JWT authentication system
2. Business registration/login
3. API key generation
4. Business settings management

### Phase 3: Subscriber Management
1. Subscriber CRUD endpoints
2. Bulk import functionality
3. Email validation
4. Custom fields support
5. Segmentation logic

### Phase 4: Email Templates
1. Template CRUD
2. Variable substitution
3. Template preview
4. Template library

### Phase 5: Campaign Management
1. Campaign CRUD
2. Email sending service
3. SMTP connection management
4. Scheduling system
5. Send queue management

### Phase 6: Email Tracking
1. Open tracking (pixel + log)
2. Click tracking (link rewrite + log)
3. Bounce handling
4. Analytics aggregation

### Phase 7: Automations
1. Automation workflow engine
2. Trigger evaluation
3. Task scheduling
4. Step execution

### Phase 8: Analytics & Reporting
1. Metrics calculation
2. Dashboard endpoints
3. Export functionality

### Phase 9: Background Tasks
1. APScheduler setup
2. Email queue processor
3. Automation executor
4. Analytics calculator
5. Cleanup jobs

### Phase 10: Testing & Deployment
1. Unit tests
2. Integration tests
3. Deployment guide
4. Environment configuration

---

## 7. ENVIRONMENT VARIABLES

```
# Flask
FLASK_ENV=production
FLASK_DEBUG=False
SECRET_KEY=your-secret-key-here

# Database
DATABASE_URL=postgresql://user:password@localhost:5432/email_marketing

# JWT
JWT_SECRET_KEY=your-jwt-secret-key

# Email System
DEFAULT_SMTP_HOST=smtp.gmail.com
DEFAULT_SMTP_PORT=587
DEFAULT_SMTP_TLS=True

# App Settings
MAX_EMAIL_BATCH_SIZE=100
QUEUE_PROCESSING_INTERVAL=10
MAX_RETRY_ATTEMPTS=3

# Analytics
ENABLE_TRACKING=True
TRACKING_DOMAIN=your-domain.com
```

---

## 8. IMPORTANT CONSIDERATIONS

### Deliverability Best Practices
- Implement SPF/DKIM/DMARC verification at setup
- Warm-up emails gradually for new IPs
- Monitor bounce rates
- Clean lists regularly
- Respect List-Unsubscribe standards
- Include physical address in emails (CAN-SPAM)

### Security
- JWT token expiration (15 min access, 7 days refresh)
- Rate limiting on API endpoints
- Input validation on all endpoints
- SQL injection prevention (use ORM)
- HTTPS enforcement
- API key rotation capability

### Performance
- Connection pooling for database
- Email queue processing (async)
- Caching for frequent queries
- Pagination for list endpoints
- Index on frequently queried columns

### Monitoring
- Log all email sends with status
- Monitor queue size
- Alert on errors
- Track API response times
- Disk space monitoring

---

## 9. DEPLOYMENT

### VPS Setup
```bash
1. Install Python 3.9+
2. Install PostgreSQL 13+
3. Clone repository
4. Create virtual environment
5. pip install -r requirements.txt
6. Configure .env file
7. Run migrations
8. Start with gunicorn
9. Set up nginx as reverse proxy
10. Configure SSL certificate
```

### Systemd Service (for continuous running)
```ini
[Unit]
Description=Email Marketing Platform
After=network.target

[Service]
User=emailapp
WorkingDirectory=/path/to/app
ExecStart=/path/to/venv/bin/gunicorn -w 4 -b 127.0.0.1:5000 app:app
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### Nginx Configuration
```nginx
server {
    listen 443 ssl http2;
    server_name yourdomain.com;

    ssl_certificate /path/to/cert;
    ssl_certificate_key /path/to/key;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

---

## 10. TESTING CHECKLIST

- [ ] Create business account
- [ ] Add subscribers manually
- [ ] Bulk import subscribers
- [ ] Create email template
- [ ] Create campaign
- [ ] Send campaign to test subscriber
- [ ] Verify email received
- [ ] Verify open tracking
- [ ] Verify click tracking
- [ ] Create automation workflow
- [ ] Verify automation trigger
- [ ] Test segmentation
- [ ] Check analytics accuracy
- [ ] Test unsubscribe flow
- [ ] Load test email queue
- [ ] Test error handling

---

This specification provides everything Claude Code needs to build your multi-tenant email marketing platform.
