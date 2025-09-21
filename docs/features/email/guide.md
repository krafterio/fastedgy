# Email - Usage guide

This guide provides practical examples for sending emails in your FastEdgy application.

## Configuration

First, configure your SMTP settings in your environment file (`.env`):

```env
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your-email@gmail.com
SMTP_PASSWORD=your-app-password
SMTP_DEFAULT_FROM=no-reply@yourapp.com
SMTP_USE_TLS=true
```

## Basic email sending

### Using the Mail service

```python
from fastedgy.dependencies import Inject
from fastedgy.mail import Mail
from email.message import EmailMessage

async def send_simple_email(mail: Mail = Inject(Mail)):

    # Create email message
    email = EmailMessage()
    email["To"] = "user@example.com"
    email["Subject"] = "Hello from FastEdgy"
    email.set_content("This is a plain text email.")

    # Send it
    await mail.send(email)
```

### Using in API endpoints

```python
from fastedgy.app import FastEdgy
from fastedgy.dependencies import Inject
from fastedgy.mail import Mail
from fastapi import BackgroundTasks

app = FastEdgy()

async def send_email_background(
    recipient: str,
    subject: str,
    message: str,
    mail: Mail = Inject(Mail)
):
    """Background task to send email."""
    from email.message import EmailMessage

    email_msg = EmailMessage()
    email_msg["To"] = recipient
    email_msg["Subject"] = subject
    email_msg.set_content(message)

    await mail.send(email_msg)

@app.post("/send-notification")
async def send_notification(
    email: str,
    message: str,
    background_tasks: BackgroundTasks
):
    # Add email sending to background tasks
    background_tasks.add_task(
        send_email_background,
        email,
        "Notification",
        message
    )

    # Return immediately without waiting for email
    return {"status": "queued", "message": "Notification will be sent shortly"}
```

## Template-based emails

### Create your template

Create a template file in `templates/en/welcome.html`:

```html
{% block subject %}Welcome to {{ app_name }}, {{ user_name }}!{% endblock %}

{% block body_html %}
<div style="font-family: Arial, sans-serif;">
    <h1>Welcome {{ user_name }}!</h1>
    <p>Thank you for joining <strong>{{ app_name }}</strong>.</p>
    <p>Your account is now active and ready to use.</p>
    <a href="{{ login_url }}" style="background-color: #007cba; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px;">
        Login Now
    </a>
</div>
{% endblock %}

{% block body_text %}
Welcome {{ user_name }}!

Thank you for joining {{ app_name }}.
Your account is now active and ready to use.

Login: {{ login_url }}
{% endblock %}
```

### Send templated email

```python
async def send_welcome_email(
    user_email: str,
    user_name: str,
    mail: Mail = Inject(Mail)
):
    await mail.send_template(
        template_name="welcome",
        tpl_vals={
            "user_name": user_name,
            "app_name": "My Awesome App",
            "login_url": "https://myapp.com/login"
        },
        email_parts={"To": user_email}
    )
```

### Background templated emails

Perfect for user registration workflows:

```python
from fastapi import BackgroundTasks
from pydantic import BaseModel

class UserRegistration(BaseModel):
    email: str
    username: str
    full_name: str

async def send_welcome_email_background(
    user_email: str,
    user_name: str,
    mail: Mail = Inject(Mail)
):
    """Send welcome email in background."""
    await mail.send_template(
        template_name="auth/welcome",
        tpl_vals={
            "user_name": user_name,
            "app_name": "My Awesome App",
            "login_url": "https://myapp.com/login"
        },
        email_parts={"To": user_email}
    )

@app.post("/register")
async def register_user(
    user_data: UserRegistration,
    background_tasks: BackgroundTasks
):
    # 1. Create user in database (fast)
    # user = await create_user(user_data)

    # 2. Send welcome email in background (slow)
    background_tasks.add_task(
        send_welcome_email_background,
        user_data.email,
        user_data.full_name
    )

    # 3. Return immediately
    return {
        "message": "User registered successfully",
        "status": "welcome_email_queued"
    }
```

[Back to Overview](overview.md){ .md-button }
