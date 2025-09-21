# Getting Started with Queued Tasks

Set up background task processing in your FastAPI application in 5 minutes.

## Prerequisites

- FastAPI application with FastEdgy
- PostgreSQL database (for task storage)
- Basic understanding of async/await

## Step 1: Database Migration

First, create the tables needed for task storage:

```bash
# Create migration for task tables
fastedgy db makemigrations -m "Add queued task system"

# Apply the migration
fastedgy db migrate
```

This creates tables to store tasks, workers, and logs.

## Step 2: Your First Background Task

Create a simple async function to run in the background:

```python
# tasks.py
async def send_welcome_email(user_email: str, username: str):
    """Send a welcome email to new users."""
    # Your email sending logic here
    print(f"Sending welcome email to {user_email} (user: {username})")

    # Simulate email processing time
    await asyncio.sleep(2)

    return {"email_sent": True, "recipient": user_email}
```

## Step 3: Queue Tasks in Your API

Use the task in your FastAPI endpoints:

```python
# main.py
from fastapi import APIRouter
from fastedgy.app import FastEdgy
from fastedgy.dependencies import Inject
from fastedgy.queued_tasks import QueuedTasks
from tasks import send_welcome_email

app = FastEdgy()
router = APIRouter()

@router.post("/users/register")
async def register_user(
    email: str,
    username: str,
    tasks: QueuedTasks = Inject(QueuedTasks)  # Inject the task queue
):
    # Create user in database (fast operation)
    user = {"id": 123, "email": email, "username": username}

    # Queue email sending (slow operation) - runs in background
    email_task = tasks.add_task(
        send_welcome_email,
        user["email"],
        user["username"]
    )

    # Return immediately - user doesn't wait for email
    return {
        "user": user,
        "email_task_queued": True
    }

app.include_router(router)
```

**That's it!** Your task is now queued and will be executed by background workers.

## Step 4: Start Workers

In a separate terminal, start background workers to process tasks:

```bash
# Start 2 background workers
fastedgy queue start --workers=2
```

You'll see output like:
```
Starting 2 workers...
Worker 1 ready
Worker 2 ready
Listening for tasks...
```

## Step 5: Test It!

Make a request to your endpoint:

```bash
curl -X POST "http://localhost:8000/users/register" \
  -H "Content-Type: application/json" \
  -d '{"email": "user@example.com", "username": "johndoe"}'
```

**Response (immediate):**
```json
{
  "user": {"id": 123, "email": "user@example.com", "username": "johndoe"},
  "email_task_queued": true
}
```

**Worker output (2 seconds later):**
```
Sending welcome email to user@example.com (user: johndoe)
Task completed: send_welcome_email
```

## What Just Happened?

1. **User registration** completed instantly (database operations)
2. **Email task** was queued in PostgreSQL
3. **Background worker** picked up the task
4. **Email sent** without blocking the user's request

## Task Dependencies

Tasks can wait for other tasks to complete:

```python
@router.post("/orders")
async def process_order(
    order_data: dict,
    tasks: QueuedTasks = Inject(QueuedTasks)
):
    # Process order first
    process_task = tasks.add_task(process_payment, order_data["payment_info"])

    # These tasks wait for payment processing to complete
    email_task = tasks.add_task(
        send_order_confirmation,
        order_data["user_email"],
        parent=process_task  # Waits for process_task
    )

    inventory_task = tasks.add_task(
        update_inventory,
        order_data["items"],
        parent=process_task  # Also waits for process_task
    )

    return {"order_queued": True}
```

## Checking Task Status

Get information about your tasks:

```python
@router.get("/tasks/{task_id}")
async def get_task_status(task_id: str):
    # You can check task status, but this requires storing task IDs
    # See the User Guide for complete examples
    pass
```

## Common Patterns

### Pattern 1: Fire and Forget
```python
# Just queue it - don't need the result
tasks.add_task(send_notification, user_id, "Welcome!")
```

### Pattern 2: Get Task Reference
```python
# Get task ID to track later
task_ref = tasks.add_task(generate_report, user_id)
task_id = await task_ref.get_task_id()
return {"task_id": task_id}
```

### Pattern 3: Multiple Related Tasks
```python
# Process multiple items in parallel
for item in items:
    tasks.add_task(process_item, item.id)
```

## Environment Variables (Optional)

Customize worker behavior:

```bash
# .env
QUEUE_MAX_WORKERS=4              # Default: CPU count
QUEUE_WORKER_IDLE_TIMEOUT=60     # Shutdown idle workers after 60s
QUEUE_TASK_TIMEOUT=300           # Max 5 minutes per task
```

## Basic CLI Commands

```bash
# Check queue status
fastedgy queue status

# Start workers
fastedgy queue start --workers=3

# Clear all pending tasks (development only)
fastedgy queue clear
```

## Next Steps

You now know the basics! For more advanced features:

- **[User Guide →](guide.md)** - Complete patterns and task management
- **[Advanced Usage →](advanced.md)** - Context tracking, hooks, and complex scenarios
- **[Technical Details →](technical.md)** - CLI commands, monitoring, and troubleshooting

## Troubleshooting

**Tasks not running?**
- Check workers are started: `fastedgy queue status`
- Check database connection in worker logs

**Tasks failing?**
- Check function imports are available to workers
- Verify async function syntax

**Performance issues?**
- Increase worker count: `fastedgy queue start --workers=6`
- Check database connection pool settings

## Quick Reference

```python
from fastedgy.dependencies import Inject
from fastedgy.queued_tasks import QueuedTasks

# Basic usage
tasks: QueuedTasks = Inject(QueuedTasks)

# Queue a task (fire and forget)
tasks.add_task(my_function, arg1, arg2)

# Queue with parent dependency
child_task = tasks.add_task(child_function, parent=parent_task)

# Get task ID for tracking
task_ref = tasks.add_task(my_function, arg)
task_id = await task_ref.get_task_id()
```

Ready for more advanced patterns? **[Continue to User Guide →](guide.md)**
