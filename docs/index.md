---
hide:
  - navigation
---

# FastEdgy

**The opinionated FastAPI foundation for production applications**

FastEdgy combines the power of [FastAPI](https://fastapi.tiangolo.com) with [Edgy ORM](https://edgy.dymmond.com) to create a cohesive, battle-tested foundation for modern web applications. Born from real-world projects at [Krafter](https://krafter.io), it provides the missing pieces that transform FastAPI from a great framework into a complete development platform.

## Why FastEdgy?

**FastAPI is excellent**, but production applications need more than just great APIs. FastEdgy fills the gaps with:

<div class="grid cards" markdown>

-   **:material-flash: Skip the Boilerplate**

    ---

    Auto-generated CRUD APIs, intelligent query builders, and metadata extraction. Build complex features in minutes, not hours.

    [See what's possible →](features/index.md)

-   **:material-cogs: No More Dependency Hell**

    ---

    True application-wide dependency injection that just works. Share services between APIs, CLI commands, and background tasks effortlessly.

    [Learn how →](features/container-service/overview.md)

-   **:material-rocket-launch: Background Tasks That Scale**

    ---

    Persistent task queues with retries, monitoring, and multi-worker support. Handle heavy workloads without breaking a sweat.

    [Discover more →](features/queued-tasks/overview.md)

-   **:material-auto-fix: Everything Included**

    ---

    Rich CLI, multi-tenancy, email templating, i18n, file storage—all integrated and ready to use. Stop hunting for libraries.

    [Get started →](getting-started.md)

</div>

**And that's just the beginning.** FastEdgy includes **16+ production-ready features** covering everything from automatic CRUD generation to advanced query builders, multi-tenancy, email templating, and comprehensive i18n support.

[Explore all features :material-arrow-right:](features/index.md){ .md-button .md-button--primary }

## Quick Example

Here's what a complete FastEdgy application looks like:

```python
from fastedgy import FastEdgy
from fastedgy.models import Model
from fastedgy.orm import fields
from fastedgy.dependencies import Inject, get_service
from fastedgy.queued_tasks import QueuedTasks

# Your model
class User(Model):
    name = fields.CharField(max_length=100)
    email = fields.EmailField()

# Your service
class EmailService:
    async def send_welcome(self, email: str):
        # Send welcome email
        pass

# Your app with dependency injection and background tasks
app = FastEdgy()

@app.post("/users/")
async def create_user(
    user_data: dict,
    email_service: EmailService = Inject(EmailService),
    tasks: QueuedTasks = Inject(QueuedTasks)
):
    user = User(**user_data)
    await user.save()

    # Queue background task
    await tasks.add_task(email_service.send_welcome, user.email)

    return user
```

## Our Philosophy

FastEdgy isn't trying to replace or compete with existing tools. Instead, it **complements the Python ecosystem** by providing a thoughtful integration of proven technologies. We believe in:

- **Convention over Configuration** - Sensible defaults that just work
- **Production First** - Built for real applications, not just demos
- **Developer Happiness** - Tools that make your daily work enjoyable
- **Ecosystem Respect** - Building on giants, not reinventing wheels

## Ready to Build?

[Get Started →](getting-started.md){ .md-button .md-button--primary }
