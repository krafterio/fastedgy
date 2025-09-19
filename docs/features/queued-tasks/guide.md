# Queued Tasks User Guide

Complete guide to using background tasks effectively in your FastAPI applications.

## Task Creation Patterns

### Pattern 1: Simple Background Jobs

For operations that don't need to return results to the user:

```python
from fastedgy.dependencies import Inject
from fastedgy.queued_tasks import QueuedTasks

async def send_email(recipient: str, subject: str, body: str):
    # Email sending logic
    return {"sent": True, "recipient": recipient}

@router.post("/users/{user_id}/notify")
async def notify_user(
    user_id: int,
    message: str,
    tasks: QueuedTasks = Inject(QueuedTasks)
):
    user = get_user(user_id)

    # Fire and forget - user gets immediate response
    tasks.add_task(send_email, user.email, "Notification", message)

    return {"notification_queued": True}
```

### Pattern 2: Task Dependencies

When tasks must run in a specific order:

```python
async def process_order(order_id: int):
    return {"order_id": order_id, "status": "processed"}

async def send_confirmation(order_id: int):
    return {"confirmation_sent": True}

@router.post("/orders")
async def create_order(
    order_data: dict,
    tasks: QueuedTasks = Inject(QueuedTasks)
):
    # Main processing task
    process_task = tasks.add_task(process_order, order_data["id"])

    # This waits for process_task to complete
    tasks.add_task(
        send_confirmation,
        order_data["id"],
        parent=process_task  # Dependency
    )

    return {"order_queued": True}
```

### Pattern 3: Parallel Processing

Process multiple items simultaneously:

```python
@router.post("/users/{user_id}/process-gallery")
async def process_user_gallery(
    user_id: int,
    tasks: QueuedTasks = Inject(QueuedTasks)
):
    user_images = get_user_images(user_id)

    for image in user_images:
        # Process all images in parallel
        tasks.add_task(process_image, image.id, user_id)

    return {"images_queued": len(user_images)}
```

## Context and Progress Tracking

Track progress within your tasks:

```python
from fastedgy.queued_task import set_context, get_context

async def process_dataset(dataset_id: int):
    set_context("dataset.id", dataset_id)
    set_context("progress", 0)
    set_context("stage", "loading")

    # Load data
    data = load_dataset(dataset_id)
    set_context("progress", 25)

    # Process data
    set_context("stage", "processing")
    result = process_data(data)
    set_context("progress", 75)

    # Save results
    set_context("stage", "saving")
    save_results(result)
    set_context("progress", 100)

    return {"processed": True}
```

## Error Handling

Design robust tasks:

```python
from fastedgy.queued_task import getLogger

async def robust_task(data_id: int):
    logger = getLogger("tasks.processing")

    try:
        logger.info(f"Starting task for {data_id}")
        set_context("data.id", data_id)

        result = process_data(data_id)

        logger.info("Task completed successfully")
        return result

    except Exception as e:
        logger.error(f"Task failed: {str(e)}")
        set_context("error.message", str(e))
        raise
```

## Best Practices

### 1. Keep Tasks Focused
```python
# Good: Single responsibility
async def send_welcome_email(user_email: str):
    return send_email(user_email, "welcome_template")

# Avoid: Too many responsibilities
async def handle_new_user(user_data: dict):
    create_user(user_data)    # Database
    send_email(...)           # Email
    resize_image(...)         # Image processing
    # Too much!
```

### 2. Handle Errors Appropriately
```python
async def api_task(data: dict):
    try:
        return await third_party_api.send(data)
    except APIRateLimitError:
        # Will be retried automatically
        raise
    except APIAuthError:
        # Don't retry auth errors
        set_context("auth_failed", True)
        raise
```

## Configuration

Set environment variables:

```bash
QUEUE_MAX_WORKERS=4         # Number of workers
QUEUE_TASK_TIMEOUT=300      # Max time per task (seconds)
QUEUE_MAX_RETRIES=3         # Retry attempts
```

## Common Issues

**Tasks not processing?**
- Check workers are running: `fastedgy queue status`
- Start workers: `fastedgy queue start --workers=3`

**Tasks failing?**
- Check function imports in worker environment
- Verify task function signatures

## Next Steps

- **[Advanced Usage →](advanced.md)** - Complex patterns and hooks
- **[Technical Details →](technical.md)** - CLI commands and monitoring
- **[Getting Started ←](getting-started.md)** - Back to basics
