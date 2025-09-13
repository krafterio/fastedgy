# Queued Task System

A comprehensive, production-ready task queue system for FastAPI applications with advanced dependency management,
context tracking, and multi-server coordination.

## Features

- **Simple API**: Easy-to-use `add_task()` method with clean task references
- **Task Dependencies**: Parent-child relationships with automatic cascade handling
- **Context Management**: Nested context tracking with auto-commit to database
- **Enhanced Logging**: Dual logging (console + database) with seamless integration
- **Worker Pool**: Intelligent worker management with idle timeout and scaling
- **Multi-server Support**: Coordinate workers across multiple server instances
- **Local Functions**: Support for both module functions and local/lambda functions
- **PostgreSQL NOTIFY/LISTEN**: Real-time task notifications with polling fallback
- **Graceful Shutdown**: Proper cleanup and worker unregistration
- **Task Control**: Cancel, stop, wait for task completion with QueuedTaskRef

## Quick Start

### 1. Basic Task Creation

```python
from fastedgy.dependencies import Inject
from fastedgy.queued_tasks import QueuedTasks

# Simple async function
async def send_email(recipient: str, subject: str):
    # Your email logic here
    return {"sent": True, "recipient": recipient}


# In your FastAPI endpoint
async def create_user(user_data: dict, queued_tasks: QueuedTasks = Inject(QueuedTasks)):
    # Create user in database
    user = await create_user_in_db(user_data)

    # Send welcome email asynchronously
    email_task = queued_tasks.add_task(
        send_email,
        user.email,
        "Welcome to our platform!"
    )

    # Use get_task_id() only if task ID must be returned to the user
    return {"user_id": user.id, "email_task_id": await email_task.get_task_id()}
```

### 2. Task Dependencies

```python
from fastedgy.dependencies import Inject
from fastedgy.queued_tasks import QueuedTasks

async def process_order(order_id: int):
    # Process order logic
    return {"order_id": order_id, "status": "processed"}


async def send_confirmation(order_id: int):
    # Send confirmation email
    return {"confirmation_sent": True}


async def update_inventory(order_id: int):
    # Update inventory levels
    return {"inventory_updated": True}


# Create dependent tasks
async def handle_order(order_data: dict, queued_tasks: QueuedTasks = Inject(QueuedTasks)):
    # Main processing task
    process_task = queued_tasks.add_task(process_order, order_data['id'])

    # These will wait for process_task to complete
    confirmation_task = queued_tasks.add_task(
        send_confirmation,
        order_data['id'],
        parent=process_task
    )

    inventory_task = queued_tasks.add_task(
        update_inventory,
        order_data['id'],
        parent=process_task
    )

    return {
        "process_task_id": await process_task.get_task_id(),
        "confirmation_task_id": await confirmation_task.get_task_id(),
        "inventory_task_id": await inventory_task.get_task_id()
    }
```

### 3. Context Management

```python
from fastedgy.queued_task import set_context, get_context, getLogger


async def complex_data_processing(dataset_id: int):
    logger = getLogger('data.processing')

    # Set initial context
    set_context('dataset.id', dataset_id)
    set_context('progress', 0)
    set_context('step', 'validation')

    logger.info(f"Starting processing for dataset {dataset_id}")

    # Validation step
    set_context('validation.start_time', datetime.now().isoformat())
    await validate_dataset(dataset_id)
    set_context('validation.status', 'completed')
    set_context('progress', 25)

    # Processing step
    set_context('step', 'processing')
    results = await process_data(dataset_id)
    set_context('processing.records_processed', len(results))
    set_context('progress', 75)

    # Final step
    set_context('step', 'saving')
    await save_results(results)
    set_context('progress', 100)
    set_context('step', 'completed')

    # Access context from other parts
    total_records = get_context('processing.records_processed', 0)
    logger.info(f"Completed processing {total_records} records")

    return {"success": True, "records": total_records}
```

### 4. Local Functions (Advanced)

```python
from fastedgy.dependencies import Inject
from fastedgy.queued_tasks import QueuedTasks

async def create_dynamic_task(queued_tasks: QueuedTasks = Inject(QueuedTasks)):
    # Define task function locally (useful for dynamic behavior)
    async def dynamic_processing(config: dict):
        # This function is defined locally and will be serialized
        for item in config['items']:
            await process_item(item)
        return {"processed": len(config['items'])}

    # This works! Local functions are automatically serialized with dill
    task_ref = queued_tasks.add_task(dynamic_processing, {"items": [1, 2, 3]})

    # Use get_task_id() only if task ID must be returned to the user
    return {"task_id": await task_ref.get_task_id()}
```

### 6. Task Lifecycle Hooks (Extension System)

```python
from fastedgy import context
from fastedgy.queued_task import on_pre_create, on_pre_run, on_post_run
from fastedgy.http import Request

# Simple decorators auto-register hooks
@on_pre_create
async def capture_workspace_context(task) -> None:
    """Capture current workspace context when creating a task (before save)"""
    current_workspace = context.get_workspace()
    task.context.update({'workspace_id': current_workspace.id if current_workspace else None})

@on_pre_run
async def restore_workspace_context(task) -> None:
    """Restore workspace context before executing a task"""
    workspace_id = task.context.get('workspace_id')
    if workspace_id:
        workspace = await Workspace.query.get(id=workspace_id)
        # Create fake request and inject context
        fake_request = Request({"type": "http", "method": "POST", "path": "/task"})
        fake_request.state = State()
        context.set_request(fake_request)
        context.set_workspace(workspace)

@on_post_run
async def cleanup_context(task, result=None, error=None) -> None:
    """Clean up context after task execution"""
    context.set_request(None)

# Available hook decorators:
# - @on_pre_create    # Before task.save() - modify task object
# - @on_post_create   # After task.save() - task exists in DB
# - @on_pre_run       # Before task execution - setup context
# - @on_post_run      # After execution (success or failure) - cleanup

# No configuration needed - hooks are auto-registered when imported!
```

### 6. Task Control

```python
from fastedgy.dependencies import Inject
from fastedgy.queued_tasks import QueuedTasks

async def manage_tasks(queued_tasks: QueuedTasks = Inject(QueuedTasks)):
    # Create a long-running task
    task_ref = queued_tasks.add_task(long_running_process, data)

    # Wait for creation
    task_id = await task_ref.get_task_id()

    # Check status
    current_state = await task_ref.get_state()

    # Cancel if needed
    if some_condition:
        task_ref.cancel()

    # Or wait for completion
    try:
        result = await task_ref.wait()
        return {"success": True, "result": result}
    except asyncio.CancelledError:
        return {"success": False, "reason": "Task was cancelled"}
```

## Setup and Configuration

### 1. Install Dependencies

```bash
# Required packages (add to requirements.txt)
dill~=0.4  # For local function serialization
```

### 2. Database Migration

```bash
# Create migration for queue tables
fastedgy db makemigrations -m "Add queued task system"

# Apply migration
fastedgy db migrate
```

### 3. Environment Configuration

```bash
# Optional environment variables
QUEUE_MAX_WORKERS=4                    # Default: CPU count
QUEUE_WORKER_IDLE_TIMEOUT=60          # Seconds before idle worker shutdown
QUEUE_POLLING_INTERVAL=2              # Seconds between queue polls
QUEUE_FALLBACK_POLLING_INTERVAL=30    # Fallback polling when NOTIFY fails
QUEUE_TASK_TIMEOUT=300                # Max seconds per task
QUEUE_MAX_RETRIES=3                   # Max retry attempts
QUEUE_USE_POSTGRESQL_NOTIFY=true      # Enable PostgreSQL NOTIFY/LISTEN
QUEUE_NOTIFY_CHANNEL=queue_new_task   # PostgreSQL notification channel
```

## CLI Commands

### Queue Management

```bash
# Check queue status
fastedgy queue status

# Start workers (in separate terminal from server)
fastedgy queue start --workers=3

# Start specific number of workers
fastedgy queue start --workers=1

# Clear pending tasks
fastedgy queue clear

# Retry failed tasks
fastedgy queue retry

# View detailed statistics
fastedgy queue stats

# List active servers
fastedgy queue servers
```

### Server Management

```bash
# Start HTTP server only
kt serve

# Start server with specific workers (advanced)
kt serve --workers=3

# Start only workers (no HTTP)
kt serve --workers=3 --no-http
```

## Monitoring and Debugging

### Database Queries

```sql
-- View all tasks
SELECT id, name, state, date_enqueued, date_started, date_done, parent_task
FROM queued_tasks
ORDER BY date_enqueued DESC;

-- View task logs
SELECT qt.name, qtl.type, qtl.message, qtl.date_created
FROM queued_task_logs qtl
JOIN queued_tasks qt ON qtl.queued_task_id = qt.id
ORDER BY qtl.date_created DESC;

-- View active workers
SELECT server_name, max_workers, active_workers, idle_workers, is_running, last_heartbeat
FROM queued_task_workers
WHERE is_running = true;

-- Task hierarchy view
WITH RECURSIVE task_hierarchy AS (SELECT id, name, parent_task, 1 as level, ARRAY[id] as path
                                  FROM queued_tasks
                                  WHERE parent_task IS NULL

                                  UNION ALL

                                  SELECT qt.id, qt.name, qt.parent_task, th.level + 1, th.path || qt.id
                                  FROM queued_tasks qt
                                  JOIN task_hierarchy th ON qt.parent_task = th.id)
SELECT level, REPEAT('  ', level - 1) || name as indented_name, id, path
FROM task_hierarchy
ORDER BY path;
```

### Log Analysis

```python
from fastedgy.queued_task import getLogger

# Enhanced logging automatically goes to both console and database
logger = getLogger('my.module')
logger.info("Processing started")
logger.warning("Potential issue detected")
logger.error("Task failed", extra={"context": {"step": "validation"}})
```

## Advanced Configuration

### Custom Worker Pool Settings

```python
from fastedgy.dependencies import get_service
from fastedgy.queued_task import QueuedTaskConfig

# Modify settings at runtime
config = get_service(QueuedTaskConfig)
config.max_workers = 8
config.worker_idle_timeout = 120
config.task_timeout = 600
```

### Custom Task Serialization

```python
# For complex object serialization, use custom serializer
import pickle


async def custom_serialization_task(complex_object: MyCustomClass):
    # Handle custom objects that dill might struggle with
    serialized = pickle.dumps(complex_object)
    # Process the object
    return {"processed": True}
```

## Best Practices

### 1. Error Handling

```python
async def robust_task(data: dict):
    try:
        set_context('step', 'validation')
        validate_data(data)

        set_context('step', 'processing')
        result = await process_data(data)

        set_context('step', 'completed')
        return result

    except ValidationError as e:
        set_context('error.type', 'validation')
        set_context('error.details', str(e))
        raise
    except Exception as e:
        set_context('error.type', 'unexpected')
        set_context('error.details', str(e))
        raise
```

### 2. Resource Management

```python
async def database_intensive_task(query_params: dict):
    # Use context to track resource usage
    set_context('resources.database_connections', 0)

    async with get_db_connection() as conn:
        set_context('resources.database_connections', 1)

        # Process with connection
        result = await conn.execute(query_params)

        set_context('resources.processed_rows', len(result))
        return result
```

### 3. Progress Tracking

```python
async def batch_processing_task(items: list):
    total_items = len(items)
    set_context('progress.total', total_items)
    set_context('progress.completed', 0)

    for i, item in enumerate(items):
        await process_item(item)

        # Update progress
        completed = i + 1
        set_context('progress.completed', completed)
        set_context('progress.percentage', (completed / total_items) * 100)

        # Log every 10%
        if completed % (total_items // 10) == 0:
            logger.info(f"Progress: {completed}/{total_items} ({(completed / total_items) * 100:.1f}%)")
```

## Troubleshooting

### Common Issues

1. **Tasks stuck in "enqueued" state**
    - Check if workers are running: `kt queue status`
    - Start workers: `kt queue start --workers=3`

2. **Task dependencies not working**
    - Verify parent task completed successfully
    - Check for circular dependencies
    - Use hierarchy testing endpoint to debug

3. **High memory usage**
    - Reduce `QUEUE_MAX_WORKERS`
    - Increase `QUEUE_WORKER_IDLE_TIMEOUT`
    - Monitor task completion rates

4. **Database connection issues**
    - Verify PostgreSQL NOTIFY/LISTEN support
    - Set `QUEUE_USE_POSTGRESQL_NOTIFY=false` to disable
    - Check database connection pool settings

### Debug Mode

```python
# Enable debug logging
import logging

logging.getLogger('queued_task').setLevel(logging.DEBUG)
```

## Performance Tips

1. **Batch Task Creation**: Create multiple tasks together for better performance
2. **Worker Scaling**: Match worker count to your workload and CPU cores
3. **Context Usage**: Use `auto_commit=False` for frequent context updates, then save manually
4. **Database Optimization**: Index `queued_tasks.state` and `queued_tasks.date_enqueued`
5. **Connection Pooling**: Ensure proper database connection pool configuration
