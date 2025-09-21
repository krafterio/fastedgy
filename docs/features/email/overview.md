# Email

FastEdgy provides a built-in Email service for sending templated emails via SMTP. It handles both HTML and plain text formats with automatic conversion and Jinja2 template rendering.

## Key features

- **SMTP support**: Send emails via any SMTP server (Gmail, SendGrid, etc.)
- **Jinja2 templates**: Create dynamic email templates with variables
- **Multi-format**: Automatic HTML to plain text conversion
- **Async delivery**: Non-blocking email sending
- **Template structure**: Organized templates with subject, HTML, and text parts
- **Configuration-driven**: Environment-based SMTP settings

## How it works

The Email service loads templates from your `templates/` directory and renders them with provided variables. Each template can have three parts:

- **Subject**: `{% block subject %}Your subject here{% endblock %}`
- **HTML body**: `{% block body_html %}HTML content{% endblock %}`
- **Text body**: `{% block body_text %}Plain text content{% endblock %}`

If you only provide HTML, the text version is automatically generated.

## Basic example

```python
from fastedgy.dependencies import Inject
from fastedgy.mail import Mail

async def send_welcome_email(
    user_email: str,
    user_name: str,
    mail: Mail = Inject(Mail)
):
    await mail.send_template(
        template_name="welcome",
        tpl_vals={"name": user_name},
        email_parts={"To": user_email}
    )
```

## Template structure

```
templates/
└── en/
    └── welcome.html
```

```html
<!-- templates/en/welcome.html -->
{% block subject %}Welcome, {{ name }}!{% endblock %}

{% block body_html %}
<h1>Welcome {{ name }}!</h1>
<p>Thank you for joining our platform.</p>
{% endblock %}

{% block body_text %}
Welcome {{ name }}!
Thank you for joining our platform.
{% endblock %}
```

## Configuration

Set these environment variables:

- `SMTP_HOST`: Your SMTP server (e.g., smtp.gmail.com)
- `SMTP_PORT`: SMTP port (default: 587)
- `SMTP_USERNAME`: SMTP username
- `SMTP_PASSWORD`: SMTP password
- `SMTP_DEFAULT_FROM`: Default sender email
- `SMTP_USE_TLS`: Enable TLS (default: true)

## Use cases

- **User registration**: Welcome emails and account confirmations
- **Password reset**: Secure password reset links
- **Notifications**: Order confirmations, status updates
- **Marketing**: Newsletters and promotional emails

## Get started

Ready to send your first email? Learn how to set up and use the Email service:

[Usage Guide](guide.md){ .md-button .md-button--primary }
