# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from typing import (
    Any,
    AsyncContextManager,
    Awaitable,
    Callable,
    Dict,
    Optional,
    Type,
    TypeVar,
    Union,
    cast,
    overload,
)
from typing_extensions import Concatenate, ParamSpec

P = ParamSpec("P")
R = TypeVar("R")
T = TypeVar("T")
A = TypeVar("A")

import asyncio
import importlib
import inspect
import logging
import pkgutil

from functools import update_wrapper

# Fastedgy imports
from fastedgy.app import FastEdgy
from fastedgy.config import BaseSettings
from fastedgy.dependencies import Token

# Rich Click
import rich_click as click
from rich_click.decorators import _AnyCallable

# Rich
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

# Click Core
from rich_click import Argument as Argument, RichCommand, RichGroup
from rich_click import Context as Context
from rich_click import Parameter as Parameter

# Click Decorators
from rich_click import argument as argument
from rich_click import option as option
from rich_click import confirmation_option as confirmation_option
from rich_click import help_option as help_option
from rich_click import password_option as password_option
from rich_click import version_option as version_option

# Click Exceptions
from rich_click import Abort as Abort
from rich_click import BadArgumentUsage as BadArgumentUsage
from rich_click import BadOptionUsage as BadOptionUsage
from rich_click import BadParameter as BadParameter
from rich_click import ClickException as ClickException
from rich_click import FileError as FileError
from rich_click import MissingParameter as MissingParameter
from rich_click import NoSuchOption as NoSuchOption
from rich_click import UsageError as UsageError

# Click Formatting
from rich_click import HelpFormatter as HelpFormatter
from rich_click import wrap_text as wrap_text

# Click Globals
from rich_click import get_current_context as get_current_context

# Clck Terminal UI
from rich_click import clear as clear
from rich_click import confirm as confirm
from rich_click import echo_via_pager as echo_via_pager
from rich_click import edit as edit
from rich_click import getchar as getchar
from rich_click import launch as launch
from rich_click import pause as pause
from rich_click import progressbar as progressbar
from rich_click import prompt as prompt
from rich_click import secho as secho
from rich_click import style as style
from rich_click import unstyle as unstyle

# Click Types
from rich_click import BOOL as BOOL
from rich_click import Choice as Choice
from rich_click import DateTime as DateTime
from rich_click import File as File
from rich_click import FLOAT as FLOAT
from rich_click import FloatRange as FloatRange
from rich_click import INT as INT
from rich_click import IntRange as IntRange
from rich_click import ParamType as ParamType
from rich_click import Path as Path
from rich_click import STRING as STRING
from rich_click import Tuple as Tuple
from rich_click import UNPROCESSED as UNPROCESSED
from rich_click import UUID as UUID

# Click Utilities
from rich_click import echo as echo
from rich_click import format_filename as format_filename
from rich_click import get_app_dir as get_app_dir
from rich_click import get_binary_stream as get_binary_stream
from rich_click import get_text_stream as get_text_stream
from rich_click import open_file as open_file


CmdType = TypeVar("CmdType", bound=click.Command)
G = TypeVar("G", bound=click.Group)


_cli_groups: Dict[str, click.Group] = {}
_cli_commands: Dict[str, click.Command] = {}


logger = logging.getLogger("cli.command")
console = Console()


def getCliLogger(suffix: str) -> logging.Logger:
    return logger.getChild(suffix)


def register_commands_in_group(package_name: str, cli_group: click.Group) -> None:
    """
    Register all CLI commands in the given package in the given CLI group.
    """
    package = importlib.import_module(package_name)

    for _, module_name, is_pkg in pkgutil.iter_modules(
        package.__path__, package.__name__ + "."
    ):
        if not is_pkg:
            module = importlib.import_module(module_name)

            for name, obj in inspect.getmembers(module):
                if isinstance(obj, click.Command) and not isinstance(obj, click.Group):
                    cli_group.add_command(obj)


def register_cli_commands(cli: click.Group) -> None:
    """
    Register all discovered CLI commands with the main CLI group.
    """
    # Discover all CLI commands
    discover_cli_commands(__name__)

    # Register all CLI groups with their commands
    for group_name, g in _cli_groups.items():
        cli.add_command(g, name=group_name)

    # Register all CLI commands without groups
    for command_name, cmd in _cli_commands.items():
        parent = find_group_name(cli, cmd)

        if parent is None:
            cli.add_command(cmd, name=command_name)


def discover_cli_commands(package_name: str) -> None:
    """
    Discover and register all CLI commands in the given package.
    """
    package = importlib.import_module(package_name)
    prefix = package.__name__ + "."

    for _, module_name, is_pkg in pkgutil.iter_modules(package.__path__, prefix):
        # Import the module and register any CLI commands
        # Note: Commands using the decorator pattern are registered automatically
        # when the module is imported
        module = importlib.import_module(module_name)

        # Find and register click.Group objects (from @click.group())
        for name, obj in inspect.getmembers(module):
            if isinstance(obj, click.Group) and obj not in _cli_groups.values():
                group_name = getattr(obj, "name", name)
                _cli_groups[group_name] = obj

            elif (
                isinstance(obj, click.Command)
                and not isinstance(obj, click.Group)
                and obj not in _cli_commands.values()
            ):
                command_name = getattr(obj, "name", name)
                _cli_commands[command_name] = obj

        if is_pkg:
            # Recursively discover commands in subpackages
            discover_cli_commands(module_name)


def find_group_name(root_group: click.Group, cmd: click.Command) -> str | None:
    for group_name, group_command in root_group.commands.items():
        if isinstance(group_command, click.Group):
            for group_cmd_name, group_cmd in group_command.commands.items():
                if group_cmd is cmd:
                    return group_command.name

    return None


class Command(RichCommand):
    def invoke(self, ctx: Context) -> Any:
        invoke = super().invoke(ctx)

        if inspect.iscoroutinefunction(self.callback):
            return asyncio.run(invoke)

        return invoke


class Group(RichGroup):
    def command(
        self, *args: Any, **kwargs: Any
    ) -> Union[Callable[[Callable[..., Any]], Command], Command]:
        def decorator(f: Callable[..., Any]) -> Command:
            kwargs.setdefault("cls", Command)

            return cast(Command, super(Group, self).command(*args, **kwargs)(f))

        return decorator


def command(
    name: Union[Optional[str], _AnyCallable] = None,
    cls: Optional[Type[CmdType]] = None,
    **attrs: Any,
) -> Union[Command, Callable[[_AnyCallable], Union[RichCommand, CmdType]]]:
    if cls is None:
        cls = Command

    return click.command(name, cls, **attrs)


# variant: no call, directly as decorator for a function.
@overload
def group(name: _AnyCallable) -> RichGroup: ...


# variant: with positional name and with positional or keyword cls argument:
# @group(namearg, GroupCls, ...) or @group(namearg, cls=GroupCls, ...)
@overload
def group(
    name: Optional[str],
    cls: Type[G],
    **attrs: Any,
) -> Callable[[_AnyCallable], G]: ...


# variant: name omitted, cls _must_ be a keyword argument, @group(cmd=GroupCls, ...)
@overload
def group(
    name: None = None,
    *,
    cls: Type[G],
    **attrs: Any,
) -> Callable[[_AnyCallable], G]: ...


# variant: with optional string name, no cls argument provided.
@overload
def group(
    name: Optional[str] = ..., cls: None = None, **attrs: Any
) -> Callable[[_AnyCallable], RichGroup]: ...


def group(
    name: Union[str, _AnyCallable, None] = None,
    cls: Optional[Type[G]] = None,
    **attrs: Any,
) -> Union[Group, Callable[[_AnyCallable], Union[RichGroup, G]]]:
    if cls is None:
        cls = Group

    return click.group(name, cls, **attrs)


def pass_context(f: "Callable[Concatenate[Context, P], R]") -> "Callable[P, R]":
    """Marks a callback as wanting to receive the current context
    object as first argument.
    """
    if inspect.iscoroutinefunction(inspect.unwrap(f)):

        async def async_func(*args: "P.args", **kwargs: "P.kwargs") -> "R":
            return await f(get_current_context(), *args, **kwargs)

        wrapped_func = async_func
    else:

        def sync_func(*args: "P.args", **kwargs: "P.kwargs") -> "R":
            return f(get_current_context(), *args, **kwargs)

        wrapped_func = sync_func

    return cast(Callable[P, R], update_wrapper(wrapped_func, f))


def pass_cli_context(f: "Callable[Concatenate[CliContext, P], R]") -> "Callable[P, R]":
    """Similar to :func:`pass_context`, but only pass the object on the
    context onwards (:attr:`Context.obj`).  This is useful if that object
    represents the state of a nested system.
    """
    if inspect.iscoroutinefunction(inspect.unwrap(f)):

        async def async_func(*args: "P.args", **kwargs: "P.kwargs") -> "R":
            return await f(get_current_context().obj, *args, **kwargs)

        wrapped_func = async_func
    else:

        def sync_func(*args: "P.args", **kwargs: "P.kwargs") -> "R":
            return f(get_current_context().obj, *args, **kwargs)

        wrapped_func = sync_func

    return cast(Callable[P, R], update_wrapper(wrapped_func, f))


def initialize_app(f: "Callable[P, R]") -> "Callable[P, R]":
    """Automatically initialize the application."""
    if inspect.iscoroutinefunction(inspect.unwrap(f)):

        async def async_func(*args: "P.args", **kwargs: "P.kwargs") -> "R":
            ctx = get_current_context().obj
            ctx.app.initialize()
            return await f(*args, **kwargs)

        wrapped_func = async_func
    else:

        def sync_func(*args: "P.args", **kwargs: "P.kwargs") -> "R":
            ctx = get_current_context().obj
            ctx.app.initialize()
            return f(*args, **kwargs)

        wrapped_func = sync_func

    return cast(Callable[P, R], update_wrapper(wrapped_func, f))


def lifespan(f: "Callable[P, R]") -> "Callable[P, R]":
    """
    Decorator that automatically wraps the lifespan context for CLI commands.
    Allows using FastEdgy services in CLI commands without manually managing
    `async with ctx.lifespan()`.

    Compatible with other decorators like @pass_cli_context.

    Usage:
        @cli.command()
        @cli.initialize_app
        @cli.pass_cli_context  # this will pass ctx as first argument
        @cli.lifespan
        def my_command(ctx: CliContext):
            # Services are now available
            service = get_service(MyService)

        # Or without @pass_cli_context:
        @cli.command()
        @cli.initialize_app
        @cli.lifespan
        def my_other_command():
            # Services are still available via get_service
            service = get_service(MyService)
    """
    if inspect.iscoroutinefunction(inspect.unwrap(f)):

        async def async_func(*args: "P.args", **kwargs: "P.kwargs") -> "R":
            ctx = get_current_context().obj
            async with ctx.lifespan():
                return await f(*args, **kwargs)

        wrapped_func = async_func
    else:

        def sync_func(*args: "P.args", **kwargs: "P.kwargs") -> "R":
            ctx = get_current_context().obj

            async def _run():
                async with ctx.lifespan():
                    return f(*args, **kwargs)

            return asyncio.run(_run())

        wrapped_func = sync_func

    return cast(Callable[P, R], update_wrapper(wrapped_func, f))


def make_pass_decorator(
    object_type: Type[T], ensure: bool = False
) -> Callable[["Callable[Concatenate[T, P], R]"], "Callable[P, R]"]:
    """Given an object type this creates a decorator that will work
    similar to :func:`pass_obj` but instead of passing the object of the
    current context, it will find the innermost context of type
    :func:`object_type`.

    This generates a decorator that works roughly like this::

        from functools import update_wrapper

        def decorator(f):
            @pass_context
            def new_func(ctx, *args, **kwargs):
                obj = ctx.find_object(object_type)
                return ctx.invoke(f, obj, *args, **kwargs)
            return update_wrapper(new_func, f)
        return decorator

    :param object_type: the type of the object to pass.
    :param ensure: if set to `True`, a new object will be created and
                   remembered on the context if it's not there yet.
    """

    def decorator(f: "Callable[Concatenate[T, P], R]") -> "Callable[P, R]":
        if inspect.iscoroutinefunction(inspect.unwrap(f)):

            async def async_func(*args: "P.args", **kwargs: "P.kwargs") -> "R":
                ctx = get_current_context()

                obj: T | None
                if ensure:
                    obj = ctx.ensure_object(object_type)
                else:
                    obj = ctx.find_object(object_type)

                if obj is None:
                    raise RuntimeError(
                        "Managed to invoke callback without a context"
                        f" object of type {object_type.__name__!r}"
                        " existing."
                    )

                return await cast(Awaitable[R], ctx.invoke(f, obj, *args, **kwargs))

            wrapped_func = async_func
        else:

            def sync_func(*args: "P.args", **kwargs: "P.kwargs") -> "R":
                ctx = get_current_context()

                obj: T | None
                if ensure:
                    obj = ctx.ensure_object(object_type)
                else:
                    obj = ctx.find_object(object_type)

                if obj is None:
                    raise RuntimeError(
                        "Managed to invoke callback without a context"
                        f" object of type {object_type.__name__!r}"
                        " existing."
                    )

                return ctx.invoke(f, obj, *args, **kwargs)

            wrapped_func = sync_func

        return cast(Callable[P, R], update_wrapper(wrapped_func, f))

    return decorator


def pass_meta_key(
    key: str, *, doc_description: str | None = None
) -> "Callable[[Callable[Concatenate[Any, P], R]], Callable[P, R]]":
    """Create a decorator that passes a key from
    :attr:`click.Context.meta` as the first argument to the decorated
    function.

    :param key: Key in ``Context.meta`` to pass.
    :param doc_description: Description of the object being passed,
        inserted into the decorator's docstring. Defaults to "the 'key'
        key from Context.meta".

    .. versionadded:: 8.0
    """

    def decorator(f: "Callable[Concatenate[Any, P], R]") -> "Callable[P, R]":
        if inspect.iscoroutinefunction(inspect.unwrap(f)):

            async def async_func(*args: "P.args", **kwargs: "P.kwargs") -> R:
                ctx = get_current_context()
                obj = ctx.meta[key]
                return await cast(Awaitable[R], ctx.invoke(f, obj, *args, **kwargs))

            wrapped_func = async_func
        else:

            def sync_func(*args: "P.args", **kwargs: "P.kwargs") -> R:
                ctx = get_current_context()
                obj = ctx.meta[key]
                return ctx.invoke(f, obj, *args, **kwargs)

            wrapped_func = sync_func

        return cast(Callable[P, R], update_wrapper(wrapped_func, f))

    if doc_description is None:
        doc_description = f"the {key!r} key from :attr:`click.Context.meta`"

    decorator.__doc__ = (
        f"Decorator that passes {doc_description} as the first argument"
        " to the decorated function."
    )
    return decorator


class CliContext[S: BaseSettings = BaseSettings, A: FastEdgy = FastEdgy]:
    """CLI application context containing settings and app instance."""

    def __init__(self, settings: S):
        self.settings: S = settings
        self._app: A | None = None

    @property
    def app(self) -> A:
        if self._app is None:
            from fastedgy.importer import import_from_string

            app_factory = import_from_string(self.settings.app_factory)
            self._app = app_factory()

        return self._app

    def lifespan(self) -> AsyncContextManager:
        return self.app.router.lifespan_context(self.app)

    def has(self, key: Union[Type[T], Token[T], str]) -> bool:
        return self.app.has_service(key)

    def get(self, key: Union[Type[T], Token[T], str]) -> T:
        return self.app.get_service(key)


@group()
@option(
    "--env-file", default=".env", help="The environment file to use (default: .env)."
)
@pass_context
def cli(ctx, env_file: str):
    """FastEdgy CLI"""
    from fastedgy.config import init_settings

    ctx.obj = CliContext(init_settings(env_file))


def main():
    try:
        discover_cli_commands("cli")
    except Exception:
        pass
    register_cli_commands(cli)
    cli()


__all__ = [
    # Click Core
    "Argument",
    "Context",
    "Parameter",
    # Click Decorators
    "argument",
    "option",
    "confirmation_option",
    "help_option",
    "password_option",
    "version_option",
    # Click Exceptions
    "Abort",
    "BadArgumentUsage",
    "BadOptionUsage",
    "BadParameter",
    "ClickException",
    "FileError",
    "MissingParameter",
    "NoSuchOption",
    "UsageError",
    # Click Formatting
    "HelpFormatter",
    "wrap_text",
    # Click Globals
    "get_current_context",
    # Click Terminal UI
    "clear",
    "confirm",
    "echo_via_pager",
    "edit",
    "getchar",
    "launch",
    "pause",
    "progressbar",
    "prompt",
    "secho",
    "style",
    "unstyle",
    # Click Types
    "BOOL",
    "Choice",
    "DateTime",
    "File",
    "FLOAT",
    "FloatRange",
    "INT",
    "IntRange",
    "ParamType",
    "Path",
    "STRING",
    "Tuple",
    "UNPROCESSED",
    "UUID",
    # Click Utilities
    "echo",
    "format_filename",
    "get_app_dir",
    "get_binary_stream",
    "get_text_stream",
    "open_file",
    # Custom
    "CliContext",
    "Command",
    "Group",
    "command",
    "group",
    "pass_context",
    "pass_cli_context",
    "initialize_app",
    "lifespan",
    "make_pass_decorator",
    "pass_meta_key",
    "register_cli_commands",
    "register_commands_in_group",
    "find_group_name",
    "discover_cli_commands",
    # Console
    "console",
    "Panel",
    "Table",
    # App
    "getCliLogger",
    "cli",
    "main",
]
