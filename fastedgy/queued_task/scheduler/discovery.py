# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import importlib
import logging
import pkgutil

logger = logging.getLogger("queued_task.scheduler")


def discover_scheduled_tasks(package_name: str) -> None:
    """Discover and register all scheduled tasks in the given package.

    Importing each module triggers the @scheduled_task decorator, which
    registers the task in the ScheduledTaskRegistry.

    This follows the same pattern as fastedgy.cli.discover_cli_commands().

    Args:
        package_name: Dotted package name (e.g., "scheduler")
    """
    try:
        package = importlib.import_module(package_name)
    except ImportError:
        logger.debug(
            f"No scheduled tasks package '{package_name}' found, skipping discovery"
        )
        return

    if not hasattr(package, "__path__"):
        logger.debug(f"'{package_name}' is not a package, skipping discovery")
        return

    prefix = package.__name__ + "."

    for _, module_name, is_pkg in pkgutil.iter_modules(package.__path__, prefix):
        try:
            importlib.import_module(module_name)
            logger.debug(f"Discovered scheduled task module: {module_name}")
        except Exception as e:
            logger.error(f"Error importing scheduled task module '{module_name}': {e}")

        if is_pkg:
            discover_scheduled_tasks(module_name)
