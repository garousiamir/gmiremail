# Email Marketing Platform - Implementation Guide for Claude Code

## Quick Start for Claude Code

This document guides Claude Code through building the entire email marketing platform step-by-step.

---

## PHASE 1: Project Setup & Database

### Step 1.1: Create Project Structure
```
Create directories:
  - email_marketing_platform/
  - email_marketing_platform/app/
  - email_marketing_platform/app/models/
  - email_marketing_platform/app/services/
  - email_marketing_platform/app/routes/
  - email_marketing_platform/app/tasks/
  - email_marketing_platform/app/utils/
  - email_marketing_platform/migrations/
  - email_marketing_platform/tests/
```

### Step 1.2: Create requirements.txt
```
Flask==2.3.3
Flask-SQLAlchemy==3.0.5
Flask-CORS==4.0.0
psycopg2-binary==2.9.7
python-dotenv==1.0.0
APScheduler==3.10.4
Jinja2==3.1.2
requests==2.31.0
PyJWT==2.8.0
email-validator==2.0.0
uuid6==1.0.3
gunicorn==21.2.0
python-dateutil==2.8.2
sqlalchemy==2.0.20
```

### Step 1.3: Create .env.example
```
# Flask Configuration
FLASK_ENV=development
FLASK_DEBUG=True
SECRET_KEY=your-dev-secret-key-change-in-production

# Database
DATABASE_URL=postgresql://postgres:password@localhost:5432/email_marketing_dev

# JWT
JWT_SECRET_KEY=your-jwt-secret-key-change-in-production
JWT_EXPIRATION=900

# Email Settings
DEFAULT_SMTP_HOST=smtp.gmail.com
DEFAULT_SMTP_PORT=587
DEFAULT_SMTP_TLS=True

# Application Settings
MAX_EMAIL_BATCH_SIZE=100
QUEUE_PROCESSING_INTERVAL=10
MAX_RETRY_ATTEMPTS=3
DAILY_EMAIL_LIMIT=10000
```

### Step 1.4: Create app/config.py
```python
import os
from datetime import timedelta

class Config:
    """Base configuration"""
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key')
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL', 'postgresql://localhost/email_marketing_dev')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # JWT
    JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY', 'jwt-secret')
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(minutes=15)
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=7)
    
    # Email Settings
    SMTP_HOST = os.getenv('DEFAULT_SMTP_HOST', 'smtp.gmail.com')
    SMTP_PORT = int(os.getenv('DEFAULT_SMTP_PORT', 587))
    SMTP_TLS = os.getenv('DEFAULT_SMTP_TLS', 'True') == 'True'
    
    # Application
    MAX_EMAIL_BATCH_SIZE = int(os.getenv('MAX_EMAIL_BATCH_SIZE', 100))
    QUEUE_PROCESSING_INTERVAL = int(os.getenv('QUEUE_PROCESSING_INTERVAL', 10))
    MAX_RETRY_ATTEMPTS = int(os.getenv('MAX_RETRY_ATTEMPTS', 3))
    DAILY_EMAIL_LIMIT = int(os.getenv('DAILY_EMAIL_LIMIT', 10000))

class DevelopmentConfig(Config):
    """Development configuration"""
    DEBUG = True
    TESTING = False

class ProductionConfig(Config):
    """Production configuration"""
    DEBUG = False
    TESTING = False

class TestingConfig(Config):
    """Testing configuration"""
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'

config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}
```

### Step 1.5: Create app/__init__.py
```python
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()

# Initialize extensions
db = SQLAlchemy()

def create_app(config_name=None):
    """Application factory"""
    if config_name is None:
        config_name = os.getenv('FLASK_ENV', 'development')
    
    from app.config import config
    
    app = Flask(__name__)
    app.config.from_object(config[config_name])
    
    # Initialize extensions
    db.init_app(app)
    CORS(app)
    
    # Register blueprints
    from app.routes import auth, businesses, subscribers, campaigns, templates, automations, segments, analytics
    
    app.register_blueprint(auth.bp)
    app.register_blueprint(businesses.bp)
    app.register_blueprint(subscribers.bp)
    app.register_blueprint(campaigns.bp)
    app.register_blueprint(templates.bp)
    app.register_blueprint(automations.bp)
    app.register_blueprint(segments.bp)
    app.register_blueprint(analytics.bp)
    
    # Create database tables
    with app.app_context():
        db.create_all()
    
    # Initialize background tasks
    from app.tasks.scheduled_tasks import init_scheduler
    init_scheduler(app)
    
    return app
```

---

## PHASE 2: Database Models

### Step 2.1: Create app/models/__init__.py
```python
from app import db
from .business import Business
from .subscriber import Subscriber
from .email_template import EmailTemplate
from .campaign import Campaign
from .email_log import EmailLog
from .automation import Automation
from .automation_instance import AutomationInstance
from .segment import Segment

__all__ = [
    'Business', 'Subscriber', 'EmailTemplate', 'Campaign',
    'EmailLog', 'Automation', 'AutomationInstance', 'Segment'
]
```

### Step 2.2: Create app/models/business.py
```python
from app import db
from uuid6 import uuid6
from datetime import datetime

class Business(db.Model):
    __tablename__ = 'businesses'
    
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid6()))
    name = db.Column(db.String(255), nullable=False)
    email_from = db.Column(db.String(255), nullable=False)
    email_from_name = db.Column(db.String(255))
    sender_domain = db.Column(db.String(255), nullable=False)
    api_key = db.Column(db.String(255), unique=True, nullable=False, default=lambda: str(uuid6()))
    
    # SMTP Configuration
    smtp_host = db.Column(db.String(255), nullable=False)
    smtp_port = db.Column(db.Integer, nullable=False)
    smtp_username = db.Column(db.String(255), nullable=False)
    smtp_password = db.Column(db.String(255), nullable=False)
    smtp_tls = db.Column(db.Boolean, default=True)
    
    # Rate limiting
    daily_email_limit = db.Column(db.Integer, default=10000)
    emails_sent_today = db.Column(db.Integer, default=0)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    subscribers = db.relationship('Subscriber', backref='business', lazy=True, cascade='all, delete-orphan')
    campaigns = db.relationship('Campaign', backref='business', lazy=True, cascade='all, delete-orphan')
    templates = db.relationship('EmailTemplate', backref='business', lazy=True, cascade='all, delete-orphan')
    automations = db.relationship('Automation', backref='business', lazy=True, cascade='all, delete-orphan')
    segments = db.relationship('Segment', backref='business', lazy=True, cascade='all, delete-orphan')
    email_logs = db.relationship('EmailLog', backref='business', lazy=True, cascade='all, delete-orphan')
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'email_from': self.email_from,
            'email_from_name': self.email_from_name,
            'sender_domain': self.sender_domain,
            'api_key': self.api_key,
            'daily_email_limit': self.daily_email_limit,
            'emails_sent_today': self.emails_sent_today,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat()
        }
```

### Step 2.3-2.9: Create Other Models
**app/models/subscriber.py** - Subscriber model with status, custom fields
**app/models/email_template.py** - Email template with variables support
**app/models/campaign.py** - Campaign with status, metrics tracking
**app/models/email_log.py** - Email log with open/click tracking
**app/models/automation.py** - Automation workflow definition
**app/models/automation_instance.py** - Automation instance per subscriber
**app/models/segment.py** - Subscriber segmentation with filter rules

*(See DATABASE_SCHEMA section in main spec for exact SQL structure)*

---

## PHASE 3: Authentication & Business Management

### Step 3.1: Create app/utils/decorators.py
```python
from functools import wraps
from flask import request, jsonify
import jwt
import os

def require_auth(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth_header = request.headers.get('Authorization')
        
        if not auth_header:
            return jsonify({'error': 'Missing authorization header'}), 401
        
        try:
            token = auth_header.split(' ')[1]
            payload = jwt.decode(token, os.getenv('JWT_SECRET_KEY'), algorithms=['HS256'])
            request.business_id = payload['business_id']
            request.user_email = payload['email']
        except (IndexError, jwt.ExpiredSignatureError, jwt.InvalidTokenError) as e:
            return jsonify({'error': 'Invalid or expired token'}), 401
        
        return f(*args, **kwargs)
    return decorated_function
```

### Step 3.2: Create app/routes/auth.py
Implement endpoints:
- `POST /api/auth/register` - Create new business
- `POST /api/auth/login` - Login and get JWT
- `POST /api/auth/refresh` - Refresh token

### Step 3.3: Create app/routes/businesses.py
Implement endpoints:
- `GET /api/businesses/me` - Get current business
- `PUT /api/businesses/me` - Update business settings
- `GET /api/businesses/stats` - Overview statistics

---

## PHASE 4: Subscriber Management

### Step 4.1: Create app/services/subscriber_service.py
Implement:
- `add_subscriber(business_id, email, name, custom_fields)`
- `bulk_import(business_id, subscribers_data, source='csv')`
- `get_subscribers(business_id, page, per_page, filters)`
- `update_subscriber(business_id, subscriber_id, data)`
- `delete_subscriber(business_id, subscriber_id)`
- `export_subscribers(business_id, format='csv')`
- `get_subscriber_by_email(business_id, email)`

### Step 4.2: Create app/routes/subscribers.py
Implement endpoints:
- `POST /api/subscribers` - Add subscriber
- `POST /api/subscribers/bulk` - Bulk import
- `GET /api/subscribers` - List (paginated)
- `GET /api/subscribers/:id` - Get details
- `PUT /api/subscribers/:id` - Update
- `DELETE /api/subscribers/:id` - Delete
- `PUT /api/subscribers/:id/status` - Change status
- `POST /api/subscribers/export` - Export CSV

---

## PHASE 5: Email Templates

### Step 5.1: Create app/services/template_service.py
Implement:
- `create_template(business_id, name, subject, html, variables)`
- `get_template(business_id, template_id)`
- `update_template(business_id, template_id, data)`
- `delete_template(business_id, template_id)`
- `render_template(template, variables={})` - Jinja2 rendering
- `preview_template(business_id, template_id, sample_data)`

### Step 5.2: Create app/routes/templates.py
Implement endpoints:
- `POST /api/templates` - Create
- `GET /api/templates` - List
- `GET /api/templates/:id` - Get
- `PUT /api/templates/:id` - Update
- `DELETE /api/templates/:id` - Delete
- `POST /api/templates/:id/preview` - Preview

---

## PHASE 6: Campaign Management

### Step 6.1: Create app/services/email_service.py
Implement:
- `send_email(business_id, recipient_email, subject, html, text, from_email, from_name)`
- `queue_email(campaign_id, subscriber_id, email_log_id)`
- `process_email_queue()` - Background task
- `handle_bounce(email_log_id, reason)`
- `get_smtp_connection(business)` - Connection pooling

### Step 6.2: Create app/services/campaign_service.py
Implement:
- `create_campaign(business_id, template_id, segment_id, name)`
- `send_campaign_now(business_id, campaign_id)`
- `schedule_campaign(business_id, campaign_id, scheduled_time)`
- `pause_campaign(business_id, campaign_id)`
- `resume_campaign(business_id, campaign_id)`
- `get_campaign_analytics(business_id, campaign_id)`
- `create_email_logs_from_segment(campaign_id, segment_id)`

### Step 6.3: Create app/routes/campaigns.py
Implement endpoints:
- `POST /api/campaigns` - Create
- `GET /api/campaigns` - List
- `GET /api/campaigns/:id` - Get details
- `PUT /api/campaigns/:id` - Update
- `DELETE /api/campaigns/:id` - Delete
- `POST /api/campaigns/:id/send` - Send immediately
- `POST /api/campaigns/:id/schedule` - Schedule
- `POST /api/campaigns/:id/pause` - Pause
- `POST /api/campaigns/:id/resume` - Resume
- `GET /api/campaigns/:id/analytics` - Get analytics

---

## PHASE 7: Email Tracking

### Step 7.1: Create Tracking Endpoints
Implement in campaigns route:
- `GET /t/pixel?email_log_id=xxx` - Open tracking pixel
- `GET /t/click?email_log_id=xxx&url=xxx` - Click tracking redirect

### Step 7.2: Implement Tracking Logic
```python
def track_email_open(email_log_id):
    # Log open timestamp
    # Update email_log status to 'opened'
    # Return 1x1 pixel

def track_email_click(email_log_id, url):
    # Log click timestamp
    # Update email_log status to 'clicked'
    # Redirect to original URL
```

---

## PHASE 8: Automations

### Step 8.1: Create app/services/automation_service.py
Implement:
- `create_automation(business_id, name, trigger_type, workflow)`
- `evaluate_trigger(trigger_type, trigger_value, subscriber_id)`
- `execute_automation(automation_id, subscriber_id)`
- `process_automation_step(automation_instance, current_step)`
- `handle_automation_action(action_type, action_data, subscriber_id)`

### Step 8.2: Create app/routes/automations.py
Implement endpoints:
- `POST /api/automations` - Create
- `GET /api/automations` - List
- `GET /api/automations/:id` - Get
- `PUT /api/automations/:id` - Update
- `DELETE /api/automations/:id` - Delete
- `POST /api/automations/:id/activate` - Activate
- `POST /api/automations/:id/deactivate` - Deactivate

---

## PHASE 9: Segmentation

### Step 9.1: Create app/services/segment_service.py
Implement:
- `create_segment(business_id, name, filter_rules)`
- `get_segment_subscribers(business_id, segment_id)`
- `evaluate_segment(business_id, segment_id)`
- `count_segment(business_id, segment_id)`
- `update_segment(business_id, segment_id, filter_rules)`

### Step 9.2: Create app/routes/segments.py
Implement endpoints:
- `POST /api/segments` - Create
- `GET /api/segments` - List
- `GET /api/segments/:id` - Get
- `PUT /api/segments/:id` - Update
- `DELETE /api/segments/:id` - Delete
- `GET /api/segments/:id/count` - Get subscriber count

---

## PHASE 10: Analytics

### Step 10.1: Create app/services/analytics_service.py
Implement:
- `get_business_overview(business_id)` - Dashboard stats
- `calculate_campaign_metrics(campaign_id)` - Campaign analytics
- `get_engagement_metrics(business_id)` - Open/click rates
- `get_subscriber_growth(business_id)` - Trend data
- `calculate_engagement_score(subscriber_id)` - Individual score

### Step 10.2: Create app/routes/analytics.py
Implement endpoints:
- `GET /api/analytics/overview` - Dashboard
- `GET /api/analytics/engagement` - Engagement stats
- `GET /api/analytics/subscribers` - Growth chart
- `GET /api/analytics/campaigns` - Campaign comparison
- `GET /api/analytics/email-logs` - Raw logs

---

## PHASE 11: Background Tasks

### Step 11.1: Create app/tasks/scheduled_tasks.py
Implement:
```python
from apscheduler.schedulers.background import BackgroundScheduler

def init_scheduler(app):
    scheduler = BackgroundScheduler()
    
    # Email Queue Processor - Every 10 seconds
    scheduler.add_job(
        process_email_queue,
        'interval',
        seconds=10,
        id='email_queue_processor'
    )
    
    # Automation Executor - Every 30 seconds
    scheduler.add_job(
        execute_pending_automations,
        'interval',
        seconds=30,
        id='automation_executor'
    )
    
    # Analytics Calculator - Every 5 minutes
    scheduler.add_job(
        calculate_analytics,
        'interval',
        minutes=5,
        id='analytics_calculator'
    )
    
    # Bounce Processor - Every hour
    scheduler.add_job(
        process_bounces,
        'interval',
        hours=1,
        id='bounce_processor'
    )
    
    # Daily Cleanup - 2 AM
    scheduler.add_job(
        cleanup_old_data,
        'cron',
        hour=2,
        minute=0,
        id='daily_cleanup'
    )
    
    # Reset Daily Limits - 12 AM
    scheduler.add_job(
        reset_daily_limits,
        'cron',
        hour=0,
        minute=0,
        id='reset_daily_limits'
    )
    
    scheduler.start()
```

---

## PHASE 12: Main Application Entry Point

### Step 12.1: Create app.py (root level)
```python
import os
from app import create_app

if __name__ == '__main__':
    app = create_app()
    app.run(
        host='0.0.0.0',
        port=int(os.getenv('PORT', 5000)),
        debug=os.getenv('FLASK_ENV') == 'development'
    )
```

---

## PHASE 13: Testing & Validation

### Checklist Before Deployment
- [ ] All models created and migrations tested
- [ ] Authentication system working (register/login)
- [ ] Subscriber CRUD operations functional
- [ ] Email template creation and rendering working
- [ ] Campaign creation and scheduling working
- [ ] Email sending via SMTP (with test credentials)
- [ ] Open/click tracking working
- [ ] Automation workflows triggering correctly
- [ ] Segmentation filtering accurate
- [ ] Analytics calculations correct
- [ ] Background tasks running without errors
- [ ] All API endpoints returning proper responses
- [ ] Error handling and validation on all endpoints
- [ ] Database indexes created for performance
- [ ] JWT authentication on protected routes
- [ ] CORS properly configured
- [ ] Rate limiting implemented
- [ ] Logging setup for debugging

---

## PHASE 14: Deployment to VPS

### Commands for Claude Code to Execute:
```bash
# 1. On VPS: Install dependencies
sudo apt-get update
sudo apt-get install python3.9 python3-pip postgresql postgresql-contrib nginx

# 2. Clone/upload project
git clone <your-repo> /home/emailapp/email-marketing
cd /home/emailapp/email-marketing

# 3. Create virtual environment
python3 -m venv venv
source venv/bin/activate

# 4. Install Python dependencies
pip install -r requirements.txt

# 5. Set up environment
cp .env.example .env
# Edit .env with production values

# 6. Set up PostgreSQL database
sudo -u postgres createdb email_marketing
sudo -u postgres psql -c "CREATE USER emailapp WITH PASSWORD 'secure_password';"
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE email_marketing TO emailapp;"

# 7. Run migrations (create tables)
python -c "from app import create_app; app = create_app('production'); app.app_context().push()"

# 8. Test the application
gunicorn -w 4 -b 127.0.0.1:5000 app:app

# 9. Create systemd service (optional)
sudo nano /etc/systemd/system/email-marketing.service
# Copy service configuration from ARCHITECTURE_DIAGRAM.md

# 10. Configure nginx
sudo nano /etc/nginx/sites-available/email-marketing
# Copy nginx config from spec

# 11. Enable and start services
sudo systemctl enable email-marketing
sudo systemctl start email-marketing
sudo systemctl enable nginx
sudo systemctl restart nginx
```

---

## Key Implementation Notes

1. **Multi-Tenancy:** Always filter by `business_id` in queries
2. **Security:** Validate JWT on all protected routes
3. **Email Headers:** Include List-Unsubscribe header for compliance
4. **Tracking:** Use unique token for each email to track opens/clicks
5. **Error Handling:** Log all errors to database for debugging
6. **Performance:** Index frequently filtered columns
7. **Rate Limiting:** Check daily email limit before sending
8. **Validation:** Validate email format before sending
9. **SMTP:** Use connection pooling to avoid exhausting connections
10. **Background Tasks:** Ensure scheduler runs as separate process

This implementation guide provides everything needed for Claude Code to build a production-ready email marketing platform.
