# CLI

FastEdgy provides a rich command-line interface built on Rich Click, offering beautiful terminal output and easy extensibility for adding custom commands.

## Key features

- **Rich terminal output**: Beautiful tables, panels, and colored text using Rich
- **Automatic discovery**: Commands are automatically discovered and registered
- **Group organization**: Commands can be organized into logical groups
- **Easy extension**: Add new commands with simple decorators
- **Context system**: Share configuration and services across commands
- **Built-in commands**: Database management, server startup, translations, and queue monitoring

## Built-in commands

FastEdgy includes several useful commands out of the box:

- **`serve`**: Start the development server with hot reload
- **`db createdb`**: Create the database
- **`db init`**: Initialize Alembic for database migrations
- **`trans extract`**: Extract translatable strings for internationalization
- **`queue status`**: Monitor background task queue status

## Command groups

Commands are organized into logical groups:

- **`db`**: Database-related operations (create, migrate, etc.)
- **`trans`**: Translation and internationalization commands
- **`queue`**: Background task queue management

## Architecture

The CLI system uses automatic command discovery to find and register all commands in your application. Commands are defined using decorators and can access shared configuration through the CLI context.

[Usage Guide](guide.md){ .md-button .md-button--primary }
