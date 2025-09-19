# Advanced Queued Tasks Usage

Advanced patterns for complex applications including hooks, lifecycle management, and sophisticated task scenarios.

## Task Lifecycle Hooks

Extend task behavior with hooks:

```python
from fastedgy.queued_task import on_pre_create, on_pre_run, on_post_run

@on_pre_create
async def capture_context(task) -> None:
    """Run before task is saved to database"""
    current_workspace = get_current_workspace()
    task.context.update({'workspace_id': current_workspace.id})

@on_pre_run
async def setup_task(task) -> None:
    """Run before task execution"""
    workspace_id = task.context.get('workspace_id')
    if workspace_id:
        setup_workspace_context(workspace_id)

@on_post_run
async def cleanup_task(task, result=None, error=None) -> None:
    """Run after task execution (success or failure)"""
    cleanup_workspace_context()
```

## Task Control and References

Advanced task management:

```python
from fastedgy.queued_tasks import QueuedTasks
import asyncio

@router.post("/controlled-tasks")
async def manage_tasks(tasks: QueuedTasks = Inject(QueuedTasks)):
    # Create task
    task_ref = tasks.add_task(long_running_process, data)

    # Get task ID
    task_id = await task_ref.get_task_id()

    # Check state
    state = await task_ref.get_state()

    # Cancel if needed
    if some_condition:
        task_ref.cancel()
        return {"cancelled": True}

    # Wait for completion
    try:
        result = await task_ref.wait()
        return {"result": result}
    except asyncio.CancelledError:
        return {"cancelled": True}
```

## Local Functions

Queue locally defined functions:

```python
@router.post("/dynamic-task")
async def create_dynamic_task(config: dict, tasks: QueuedTasks = Inject(QueuedTasks)):
    # Define function based on request
    async def dynamic_processing(items: list):
        for item in items:
            if config.get('encrypt'):
                item = encrypt_item(item)
            await process_item(item)
        return {"processed": len(items)}

    # Queue the local function - it will be serialized automatically
    task_ref = tasks.add_task(dynamic_processing, config['items'])
    return {"task_id": await task_ref.get_task_id()}
```

## Complex Context Management

Detailed progress tracking:

```python
from fastedgy.queued_task import set_context, get_context, getLogger

async def complex_processing(dataset_id: int):
    logger = getLogger('data.processing')

    # Set initial context
    set_context('dataset.id', dataset_id)
    set_context('progress', 0)
    set_context('step', 'validation')

    logger.info(f"Starting processing for dataset {dataset_id}")

    # Validation
    await validate_dataset(dataset_id)
    set_context('validation.status', 'completed')
    set_context('progress', 25)

    # Processing
    set_context('step', 'processing')
    results = await process_data(dataset_id)
    set_context('processing.records', len(results))
    set_context('progress', 75)

    # Completion
    set_context('step', 'completed')
    set_context('progress', 100)

    return {"success": True, "records": len(results)}
```

## Batch Processing

Efficient large dataset handling:

```python
async def process_user_batch(user_ids: list[int]):
    set_context('batch.total', len(user_ids))
    set_context('batch.processed', 0)

    for i, user_id in enumerate(user_ids):
        await process_single_user(user_id)

        # Update progress every 10 users
        if i % 10 == 0:
            set_context('batch.processed', i + 1)
            progress = ((i + 1) / len(user_ids)) * 100
            set_context('batch.progress_percent', round(progress, 2))

    return {"processed": len(user_ids)}
```

## Advanced Dependencies

Complex task relationships:

```python
async def create_workflow(project_id: int, tasks: QueuedTasks = Inject(QueuedTasks)):
    # Step 1: Prepare data
    prepare_task = tasks.add_task(prepare_data, project_id)

    # Step 2: Parallel processing
    analyze_task = tasks.add_task(analyze_data, project_id, parent=prepare_task)
    transform_task = tasks.add_task(transform_data, project_id, parent=prepare_task)

    # Step 3: Combine results
    combine_task = tasks.add_task(combine_results, project_id, parent=analyze_task)

    return {"workflow_started": True, "final_task": await combine_task.get_task_id()}
```

## Error Recovery

Advanced error handling:

```python
async def resilient_task(primary_source: str, fallback_source: str):
    set_context('strategy', 'primary_with_fallback')

    try:
        set_context('current_source', primary_source)
        result = await process_from_primary(primary_source)
        set_context('source_used', 'primary')
        return result
    except PrimarySourceError as e:
        set_context('primary_error', str(e))

        # Try fallback
        try:
            set_context('current_source', fallback_source)
            result = await process_from_fallback(fallback_source)
            set_context('source_used', 'fallback')
            return result
        except Exception as fallback_error:
            set_context('all_sources_failed', True)
            raise Exception(f"All sources failed: {e}, {fallback_error}")
```

## Performance Optimization

Resource management:

```python
async def resource_intensive_task(data_id: int):
    # Use context managers for expensive resources
    async with get_db_connection() as conn:
        set_context('connection.acquired', True)

        data = await conn.fetch("SELECT * FROM data WHERE id = $1", data_id)
        result = await process_data(data)

        set_context('records.processed', len(result))
        return result
```

## Testing Advanced Patterns

Mock complex scenarios:

```python
import pytest
from unittest.mock import AsyncMock

@pytest.fixture
async def mock_tasks():
    mock = AsyncMock()
    mock_ref = AsyncMock()
    mock_ref.get_task_id.return_value = "test-123"
    mock.add_task.return_value = mock_ref

    register_service(mock, QueuedTasks, force=True)
    yield mock
    unregister_service(QueuedTasks)

@pytest.mark.asyncio
async def test_workflow(mock_tasks):
    result = await create_workflow(123, mock_tasks)
    assert mock_tasks.add_task.call_count == 4
    assert result["workflow_started"] is True
```

## Next Steps

- **[Technical Details →](technical.md)** - CLI, monitoring, architecture
- **[Getting Started ←](getting-started.md)** - Back to basics
- **[User Guide ←](guide.md)** - Everyday patterns
