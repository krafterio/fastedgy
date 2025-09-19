# Queued Tasks

A production-ready task queue system for FastAPI applications that makes background job processing simple and reliable.

## FastAPI BackgroundTasks vs Queued tasks

FastAPI includes an excellent `BackgroundTasks` system that's perfect for simple, non-critical background operations:

### FastAPI BackgroundTasks - great for simple cases

```python
# FastAPI native approach - excellent for simple tasks
from fastapi import BackgroundTasks

@router.post("/register")
async def register_user(user_data: dict, background_tasks: BackgroundTasks):
    user = create_user(user_data)

    # Perfect for simple operations like logging, notifications
    background_tasks.add_task(send_welcome_email, user.email)

    return {"user_id": user.id}
```

**FastAPI's BackgroundTasks excels when you need:**

- Simple fire-and-forget tasks (emails, logging, cache warming)
- Tasks that don't require resilience or retry logic
- Single-server applications with acceptable task loss on restarts
- Rapid development without additional infrastructure

### When you need production-grade task processing

For more demanding applications, you'll eventually need additional capabilities:

- **Persistence**: Tasks must survive server restarts and crashes
- **Reliability**: Failed tasks need automatic retries and error handling
- **Monitoring**: Track task progress, logs, and performance metrics
- **Scalability**: Distribute tasks across multiple workers/servers
- **Complex Workflows**: Task dependencies, scheduling, and chaining
- **Production Monitoring**: Database logs, CLI tools, health checks

## The solution: extending FastAPI with production-grade tasks

FastEdgy's Queued Tasks builds on FastAPI's foundation to provide enterprise-grade task processing capabilities:

```python
# FastEdgy Queued Tasks - production ready
from fastedgy.dependencies import Inject
from fastedgy.queued_tasks import QueuedTasks

@router.post("/register")
async def register_user(
    user_data: dict,
    tasks: QueuedTasks = Inject(QueuedTasks)
):
    user = create_user(user_data)

    # Tasks are persisted in PostgreSQL and executed by dedicated workers
    task_ref = tasks.add_task(send_welcome_email, user.email)

    # Optional: Get task ID for tracking
    return {
        "user_id": user.id,
        "email_task_id": await task_ref.get_task_id()
    }
```

**Additional capabilities for production applications:**

- **Persistent Storage**: Tasks survive server restarts and crashes
- **Multi-Server**: Distribute workers across multiple servers
- **Task Dependencies**: Create complex workflows with parent-child relationships
- **Progress Tracking**: Monitor task progress with context and logging
- **Automatic Retries**: Failed tasks are automatically retried
- **Production Monitoring**: Database logs, CLI tools, health checks
- **Scalability**: Add more workers as needed without code changes

## Key features

- **Simple API**: Just `add_task(function, *args)` to queue any async function
- **Task Dependencies**: Parent-child relationships with automatic cascade handling
- **Worker Management**: Intelligent scaling and multi-server coordination
- **Context Tracking**: Nested context and enhanced logging
- **Production Ready**: PostgreSQL notifications, graceful shutdown, monitoring

## Quick demo

```python
# 1. Define your async function
async def process_user_data(user_id: int):
    # Heavy processing here...
    return {"processed": True}

# 2. Queue it in any endpoint
@router.post("/users/{user_id}/process")
async def trigger_processing(
    user_id: int,
    tasks: QueuedTasks = Inject(QueuedTasks)
):
    task_ref = tasks.add_task(process_user_data, user_id)
    return {"task_queued": True, "task_id": await task_ref.get_task_id()}

# 3. Background workers automatically pick up and execute the task
```

## Quick Start

New to background tasks? Start here:

[Getting Started →](getting-started.md){ .md-button .md-button--primary }

## Documentation Structure

<div class="grid cards" markdown>

-   :material-rocket-launch: **Getting Started**

    ---

    5-minute setup guide with your first background task

    [:material-arrow-right: Start here](getting-started.md)

-   :material-book-open-variant: **User Guide**

    ---

    Complete guide for everyday task queue patterns

    [:material-arrow-right: Learn more](guide.md)

-   :material-cog: **Advanced Usage**

    ---

    Dependencies, context, hooks, and complex scenarios

    [:material-arrow-right: Advanced topics](advanced.md)

-   :material-database: **Technical Details**

    ---

    Architecture, CLI commands, monitoring, and troubleshooting

    [:material-arrow-right: Technical info](technical.md)

</div>

## When to Use Queued Tasks

**Perfect for:**
- Email sending and notifications
- Image/file processing
- Report generation
- Data imports/exports
- Third-party API calls
- Heavy computations

**FastAPI's BackgroundTasks is sufficient for:**
- Simple database queries and logging
- Fast operations (< 1 second)
- Fire-and-forget notifications
- Cache warming and simple cleanup tasks

## Core Concepts

### Tasks
Any async function can be queued as a background task.

### Workers
Background processes that execute queued tasks. Can run on same server or distributed across multiple servers.

### Task Dependencies
Tasks can wait for other tasks to complete, creating processing chains.

### Context
Track progress and metadata throughout task execution.

Ready to get started? **[→ Getting Started Guide](getting-started.md)**
