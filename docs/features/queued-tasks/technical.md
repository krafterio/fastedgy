# Queued Tasks Technical Details

Architecture, CLI commands, monitoring, and troubleshooting for the Queued Task system.

## Architecture Overview

The Queued Task system is built around PostgreSQL for reliable task storage and coordination across multiple workers and servers.

### Core Components

1. **Task Storage**: PostgreSQL tables store task definitions, state, and logs
2. **Worker Pool**: Background processes that execute tasks
3. **Notification System**: PostgreSQL NOTIFY/LISTEN for real-time task dispatch
4. **Context System**: Nested context tracking with database persistence
5. **Dependency Management**: Parent-child task relationships with cascade handling

### Task Lifecycle

```
Enqueued → Picked up → Running → Completed/Failed
    ↓           ↓          ↓           ↓
  Database   Worker    Context    Logs/Results
```

## CLI Commands

### Queue Management

```bash
# Check queue status
fastedgy queue status

# Start 3 worker processes
fastedgy queue start --workers=3

# 3 worker processes running up to 5 tasks each (15 concurrent tasks)
fastedgy queue start --workers=3 --concurrency=5

# Clear pending tasks (development only)
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
fastedgy serve

# Start server with workers
fastedgy serve --workers=3

# Start only workers (no HTTP)
fastedgy serve --workers=3 --no-http
```

## Configuration

### Environment Variables

```bash
# Worker settings
QUEUED_TASK_WORKERS=4                  # Worker processes (default: 1)
QUEUED_TASK_CONCURRENCY=4              # Tasks per worker (default: CPU count)
QUEUE_POLLING_INTERVAL=2              # Seconds between queue polls
QUEUE_FALLBACK_POLLING_INTERVAL=30    # Fallback when NOTIFY fails

# Task settings
QUEUE_TASK_TIMEOUT=300                # Max seconds per task
QUEUE_MAX_RETRIES=3                   # Max retry attempts

# Database settings
QUEUE_USE_POSTGRESQL_NOTIFY=true      # Enable PostgreSQL NOTIFY/LISTEN
QUEUE_NOTIFY_CHANNEL=queue_new_task   # PostgreSQL notification channel
```

### Runtime Configuration

```python
from fastedgy.dependencies import get_service
from fastedgy.queued_task import QueuedTaskConfig

# Modify settings at runtime
config = get_service(QueuedTaskConfig)
config.workers = 4
config.concurrency = 5
config.task_timeout = 600
```

## Worker processes

The manager is a supervisor, not an executor. It claims tasks, dispatches them
to `QUEUED_TASK_WORKERS` worker processes over a pipe, and is the only one to
hold the per-container singletons: cron scheduler, stuck-task reaper, retention
purge, auto-remove sweep, heartbeat and the NOTIFY listener. Each worker runs up
to `QUEUED_TASK_CONCURRENCY` tasks at once on its own event loop, with database
pools of its own.

Concurrency of a container is `workers x concurrency`. Cores come from the
worker count alone: one event loop never exceeds one core, whatever the cgroup
allows.

### Why processes rather than replicas

Both buy cores, but a replica also duplicates the entire manager: notification
listener, fallback polling, stuck-task reaper, retention purge, auto-remove
sweep, heartbeat and the cron scheduler (deduplicated by advisory lock, i.e.
work done and thrown away on every replica but one), plus a full set of
database pools. Workers buy the same cores for one manager, and the channel
capacities keep their meaning since the manager remains the only claimant.

### Failure of a worker

A worker that dies mid-task is respawned, and the manager recovers what it was
holding immediately, without waiting for the `claimed_by` lease to expire:

- a task the worker never started goes straight back to `enqueued`, no attempt
  burned
- a task it had started counts as an attempt: re-enqueued with the usual
  exponential delay, then failed as `WorkerProcessDied` once the retry budget is
  spent

Every recovery statement is guarded on `state = 'doing'`, so a task that
finalized itself just before its worker died is never resurrected.

### A worker whose event loop stops turning

Each worker pushes a heartbeat from its own event loop every 10s, so a loop that
stops turning stops beating. What the manager does with a missed beat depends on
what the worker holds, because the two cases are not equally decidable:

- **idle** (nothing in flight): no task body can be holding the loop, so silence
  is unambiguous. Killed after 60s.
- **busy**: a CPU-bound async body legitimately blocks the loop and is
  indistinguishable from a wedge, so the only honest bound is the one the rest
  of the system already treats as impossible for a legitimate run: twice
  `task_timeout`, the stale-`doing` reaper criterion.
- **never started**: a worker that has not beaten once within 120s never
  finished importing the application.

A long *sync* task is not affected: it runs in an executor thread, its worker
keeps beating. Killing is all the manager has to do, the closed pipe then drives
the usual death path, which recovers the tasks and respawns the worker.

On `SIGTERM`, the manager tells every worker to stop over the pipe (not by
signal, so an application `SIGTERM` handler meant for HTTP draining is not
triggered in a worker), each cancels its in-flight tasks, which mark themselves
`stopped` with `resume_requested`, and workers still alive at the end of the
grace period are killed. If the manager itself dies hard, workers notice the
closed pipe and exit on their own rather than lingering as orphans.

### Applications

`fastedgy.queued_task.services.worker_process.is_worker_process()` tells an
application lifespan it is running inside a worker, so it can skip what only the
manager or an HTTP process needs: listeners of its own, warm-up writes,
background loops that must stay singletons per container.

## Database Schema

### Core Tables

```sql
-- Tasks
CREATE TABLE queued_tasks (
    id UUID PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    state VARCHAR(50) NOT NULL,
    parent_task UUID REFERENCES queued_tasks(id),
    date_enqueued TIMESTAMP,
    date_started TIMESTAMP,
    date_done TIMESTAMP,
    context JSONB,
    result JSONB,
    error_message TEXT
);

-- Task logs
CREATE TABLE queued_task_logs (
    id SERIAL PRIMARY KEY,
    queued_task_id UUID REFERENCES queued_tasks(id),
    type VARCHAR(50),
    message TEXT,
    date_created TIMESTAMP
);

-- Workers
CREATE TABLE queued_task_workers (
    id SERIAL PRIMARY KEY,
    server_name VARCHAR(255),
    max_workers INTEGER,
    active_workers INTEGER,
    idle_workers INTEGER,
    is_running BOOLEAN,
    last_heartbeat TIMESTAMP
);
```

## Monitoring and Debugging

### Database Queries

View task status:

```sql
-- All recent tasks
SELECT id, name, state, date_enqueued, date_started, date_done, parent_task
FROM queued_tasks
ORDER BY date_enqueued DESC
LIMIT 50;

-- Task logs
SELECT qt.name, qtl.type, qtl.message, qtl.date_created
FROM queued_task_logs qtl
JOIN queued_tasks qt ON qtl.queued_task_id = qt.id
ORDER BY qtl.date_created DESC
LIMIT 100;

-- Active workers
SELECT server_name, max_workers, active_workers, idle_workers, is_running, last_heartbeat
FROM queued_task_workers
WHERE is_running = true;

-- Task hierarchy
WITH RECURSIVE task_hierarchy AS (
  SELECT id, name, parent_task, 1 as level, ARRAY[id] as path
  FROM queued_tasks
  WHERE parent_task IS NULL

  UNION ALL

  SELECT qt.id, qt.name, qt.parent_task, th.level + 1, th.path || qt.id
  FROM queued_tasks qt
  JOIN task_hierarchy th ON qt.parent_task = th.id
)
SELECT level, REPEAT('  ', level - 1) || name as indented_name, id, path
FROM task_hierarchy
ORDER BY path;
```

### Performance Monitoring

```python
# Custom monitoring endpoint
@router.get("/admin/queue-metrics")
async def get_queue_metrics():
    # Query database for metrics
    return {
        "pending_tasks": await count_pending_tasks(),
        "running_tasks": await count_running_tasks(),
        "failed_tasks_today": await count_failed_tasks_today(),
        "average_task_duration": await get_average_task_duration(),
        "active_workers": await count_active_workers(),
    }
```

### Debug Mode

Enable detailed logging:

```python
import logging

# Enable debug logging
logging.getLogger("queued_task").setLevel(logging.DEBUG)

# This shows task creation, pickup, execution steps
```

## Troubleshooting

### Common Issues

**Tasks stuck in "enqueued" state:**
- Check workers are running: `fastedgy queue status`
- Start workers: `fastedgy queue start --workers=3` (3 processes)
- Check database connectivity

**Tasks failing silently:**
- Verify function imports available to workers
- Check task function signatures match
- Review worker logs for Python errors

**High memory usage:**
- Reduce `QUEUED_TASK_WORKERS` or `QUEUED_TASK_CONCURRENCY`
- Check for memory leaks in task functions

**Database connection issues:**
- Verify PostgreSQL NOTIFY/LISTEN support
- Set `QUEUE_USE_POSTGRESQL_NOTIFY=false` to disable
- Check database connection pool settings

### Diagnostic Commands

```bash
# Check worker processes
ps aux | grep "fastedgy queue"

# Check database connections
# (Run in PostgreSQL)
SELECT state, count(*) FROM pg_stat_activity
WHERE datname = 'your_database'
GROUP BY state;

# Check notification channels
SELECT * FROM pg_stat_activity WHERE query LIKE '%LISTEN%';
```

## Performance Tuning

### Optimization Tips

1. **Worker Scaling**: Match worker count to workload and CPU cores
2. **Batch Processing**: Group small tasks into batches
3. **Connection Pooling**: Ensure proper database connection pool configuration
4. **Task Granularity**: Balance task size - not too small, not too large
5. **Context Usage**: Use `auto_commit=False` for frequent updates

### Database Indexing

Optimize task queries:

```sql
-- Index for task state queries
CREATE INDEX idx_queued_tasks_state ON queued_tasks(state);

-- Index for date-based queries
CREATE INDEX idx_queued_tasks_date_enqueued ON queued_tasks(date_enqueued);

-- Index for parent-child relationships
CREATE INDEX idx_queued_tasks_parent ON queued_tasks(parent_task);
```

## Production Deployment

### Multi-Server Setup

Deploy across multiple servers:

```bash
# Server 1: HTTP + Workers
fastedgy serve --workers=4

# Server 2: Workers only
fastedgy serve --workers=8 --no-http

# Server 3: Workers only
fastedgy serve --workers=8 --no-http
```

### Health Checks

Monitor queue health:

```python
@router.get("/health/queue")
async def queue_health():
    try:
        # Check database connectivity
        await test_db_connection()

        # Check if workers are responding
        active_workers = await count_active_workers()

        # Check for stuck tasks
        stuck_tasks = await count_stuck_tasks()

        if active_workers == 0:
            return {"status": "unhealthy", "reason": "no_active_workers"}

        if stuck_tasks > 10:
            return {"status": "degraded", "reason": "tasks_stuck"}

        return {"status": "healthy", "workers": active_workers}

    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}
```

### Backup and Recovery

Task data backup:

```bash
# Backup task tables
pg_dump -t queued_tasks -t queued_task_logs -t queued_task_workers your_db > queue_backup.sql

# Restore
psql your_db < queue_backup.sql
```

## Integration Patterns

### With Container Service

Tasks can use dependency injection:

```python
from fastedgy.dependencies import get_service


async def service_using_task(data_id: int):
    # Get services within task
    email_service = get_service(EmailService)
    db_service = get_service(DatabaseService)

    # Use services
    data = await db_service.get_data(data_id)
    result = await email_service.send_report(data)

    return result
```

### With FastAPI Middleware

Custom middleware for task context:

```python
@app.middleware("http")
async def task_context_middleware(request: Request, call_next):
    # Set context for tasks triggered by this request
    request_id = str(uuid.uuid4())

    # Store in request state for access by endpoints
    request.state.request_id = request_id

    response = await call_next(request)
    return response
```

## Security Considerations

### Task Isolation

Tasks run in the same process as workers, so:

- Validate all task inputs
- Sanitize data before processing
- Use resource limits to prevent abuse
- Consider sandboxing for untrusted code

### Access Control

```python
# Restrict queue management endpoints
@router.post("/admin/queue/clear")
async def clear_queue(current_user: User = Depends(get_admin_user)):
    # Only admins can manage queue
    clear_all_tasks()
    return {"cleared": True}
```

## Migration Guide

### From Other Task Queues

Migrating from Celery or similar:

```python
# Celery style
@celery_app.task
def old_task(data):
    return process_data(data)


# FastEdgy style
async def new_task(data):
    return await process_data(data)


# Usage
# old_task.delay(data)  # Celery
tasks.add_task(new_task, data)  # FastEdgy
```

## Quick Reference

### CLI Commands
```bash
fastedgy queue status          # Check status
fastedgy queue start -w 4      # Start workers
fastedgy queue clear           # Clear tasks (dev)
```

### Key Environment Variables
```bash
QUEUED_TASK_WORKERS=4         # Worker processes
QUEUED_TASK_CONCURRENCY=4     # Tasks per worker
QUEUE_TASK_TIMEOUT=300        # Task timeout
QUEUE_MAX_RETRIES=3           # Retry count
```

### Monitoring Queries
```sql
-- Task counts by state
SELECT state, count(*) FROM queued_tasks GROUP BY state;

-- Recent failures
SELECT name, error_message, date_done FROM queued_tasks
WHERE state = 'failed' AND date_done > NOW() - INTERVAL '1 hour';
```
