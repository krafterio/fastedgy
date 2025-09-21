# CLI - Usage guide

## Using built-in commands

### Start development server
```bash
fastedgy serve
fastedgy serve --host 127.0.0.1 --port 3000 --no-reload
```

### Database operations
```bash
fastedgy db createdb
fastedgy db init --template fastedgy
```

### Translation management
```bash
fastedgy trans extract
fastedgy trans extract fr --package mypackage
```

## Adding custom commands

### Simple command
Create a command in any module that gets imported:

```python
from fastedgy.cli import command, option, pass_cli_context, CliContext

@command()
@option("--name", default="World", help="Name to greet")
@pass_cli_context
def hello(ctx: CliContext, name: str):
    """Say hello to someone."""
    from fastedgy.cli import console
    console.print(f"[green]Hello, {name}![/green]")
```

### Command with group
Create commands organized in groups:

```python
from fastedgy.cli import group, command, option, pass_cli_context, CliContext

@group()
def data():
    """Data management commands."""
    pass

@data.command()
@option("--format", default="json", help="Output format")
@pass_cli_context
def export(ctx: CliContext, format: str):
    """Export application data."""
    from fastedgy.cli import console
    console.print(f"[blue]Exporting data in {format} format...[/blue]")
```

### Rich output
Use Rich components for beautiful terminal output:

```python
from fastedgy.cli import command, pass_cli_context, CliContext, console, Table

@command()
@pass_cli_context
def status(ctx: CliContext):
    """Show application status."""
    table = Table(title="Application Status")
    table.add_column("Component", style="cyan")
    table.add_column("Status", style="green")

    table.add_row("Database", "Connected")
    table.add_row("Cache", "Active")
    table.add_row("Queue", "Running")

    console.print(table)
```

## Command discovery

Commands are automatically discovered when:

1. **Module import**: The module containing your command is imported
2. **Decorator usage**: Commands use the `@command()` decorator
3. **Group registration**: Commands are part of a `@group()`

## Access services

Use the CLI context to access application services:

```python
@command()
@pass_cli_context
async def migrate(ctx: CliContext):
    """Run database migrations."""
    # Access settings
    settings = ctx.get(BaseSettings)

    # Access FastEdgy app and services
    app = await ctx.get_app()
    # Your migration logic here
```

## Error handling

```python
@command()
def risky_command():
    """Command that might fail."""
    try:
        # Your command logic
        pass
    except Exception as e:
        from fastedgy.cli import console
        console.print(f"[red]Error: {str(e)}[/red]")
        raise click.Abort()
```

[Back to Overview](overview.md){ .md-button }
