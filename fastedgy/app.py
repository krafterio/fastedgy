# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from typing import cast, Optional, List, Dict, Any, Union, Type, Sequence, Callable, Coroutine
from fastapi import FastAPI, routing, Depends
from fastedgy.http import ContextRequestMiddleware
from fastedgy.logger import setup_logging
from starlette.routing import BaseRoute
from starlette.middleware import Middleware
from fastapi.responses import Response
from starlette.types import Lifespan
from starlette.requests import Request
from fastedgy.config import BaseSettings, get_settings
from edgy import Database, Registry


class FastEdgy[S : BaseSettings = BaseSettings](FastAPI):
    def __init__(
        self,
        *,
        # FastAPI
        debug: bool = False,
        routes: Optional[List[BaseRoute]] = None,
        summary: Optional[str] = None,
        description: str = "",
        version: str = "0.1.0",
        openapi_url: Optional[str] = "/openapi.json",
        openapi_tags: Optional[List[Dict[str, Any]]] = None,
        servers: Optional[List[Dict[str, Union[str, Any]]]] = None,
        dependencies: Optional[Sequence[Any]] = None,
        default_response_class: Type[Response] = Response,
        docs_url: Optional[str] = "/docs",
        redoc_url: Optional[str] = "/redoc",
        swagger_ui_oauth2_redirect_url: Optional[str] = "/docs/oauth2-redirect",
        swagger_ui_init_oauth: Optional[Dict[str, Any]] = None,
        middleware: Optional[Sequence[Middleware]] = None,
        exception_handlers: Optional[
            Dict[
                Union[int, Type[Exception]],
                Callable[[Request, Any], Coroutine[Any, Any, Response]],
            ]
        ] = None,
        on_startup: Optional[Sequence[Callable[[], Any]]] = None,
        on_shutdown: Optional[Sequence[Callable[[], Any]]] = None,
        lifespan: Optional[Lifespan["FastEdgy"]] = None,
        terms_of_service: Optional[str] = None,
        contact: Optional[Dict[str, Union[str, Any]]] = None,
        license_info: Optional[Dict[str, Union[str, Any]]] = None,
        openapi_prefix: str = "",
        root_path: str = "",
        root_path_in_servers: bool = True,
        responses: Optional[Dict[Union[int, str], Dict[str, Any]]] = None,
        callbacks: Optional[List[BaseRoute]] = None,
        webhooks: Optional[routing.APIRouter] = None,
        deprecated: Optional[bool] = None,
        include_in_schema: bool = True,
        swagger_ui_parameters: Optional[Dict[str, Any]] = None,
        generate_unique_id_function: Callable[[routing.APIRoute], str] = lambda route: f"{route.tags[0] if route.tags else 'default'}_{route.name}",
        separate_input_output_schemas: bool = True,
        **extra: Any,
    ) -> None:
        from edgy import Instance, monkay
        settings = get_settings()

        monkay.settings.migration_directory = settings.db_migration_path
        monkay.set_instance(Instance(registry=settings.db_registry), apply_extensions=False)
        monkay.evaluate_settings(on_conflict="keep")

        super().__init__(
            debug=debug,
            routes=routes,
            title=settings.title,
            summary=summary,
            description=description,
            version=version,
            openapi_url=openapi_url,
            openapi_tags=openapi_tags,
            servers=servers,
            dependencies=dependencies,
            default_response_class=default_response_class,
            docs_url=docs_url,
            redoc_url=redoc_url,
            swagger_ui_oauth2_redirect_url=swagger_ui_oauth2_redirect_url,
            swagger_ui_init_oauth=swagger_ui_init_oauth,
            middleware=middleware,
            exception_handlers=exception_handlers,
            on_startup=on_startup,
            on_shutdown=on_shutdown,
            lifespan=lifespan,
            terms_of_service=terms_of_service,
            contact=contact,
            license_info=license_info,
            openapi_prefix=openapi_prefix,
            root_path=root_path,
            root_path_in_servers=root_path_in_servers,
            responses=responses,
            callbacks=callbacks,
            webhooks=webhooks,
            deprecated=deprecated,
            include_in_schema=include_in_schema,
            swagger_ui_parameters=swagger_ui_parameters,
            generate_unique_id_function=generate_unique_id_function,
            separate_input_output_schemas=separate_input_output_schemas,
            **extra,
        )

        setup_logging(
            level=settings.log_level,
            output=settings.log_output,
            format=settings.log_format,
            log_file=settings.log_path,
        )

        self.state.settings = settings
        self.state.db = settings.db
        self.state.db_registry = settings.db_registry

        monkay.set_instance(Instance(registry=settings.db_registry, app=self))

        self.add_middleware(ContextRequestMiddleware)

    @property
    def settings(self) -> BaseSettings:
        if not hasattr(self.state, 'settings'):
            raise ValueError("Settings not found in the application state")

        return cast(S, self.state.settings)

    @property
    def db(self) -> Database:
        if not hasattr(self.state, 'db'):
            raise ValueError("Database not found in the application state")

        return cast(Database, self.state.db)

    @property
    def db_registry(self) -> Registry:
        if not hasattr(self.state, 'db_registry'):
            raise ValueError("Registry not found in the application state")

        return cast(Registry, self.state.db_registry)

    def initialize(self):
        pass


__all__ = [
    "FastEdgy",
]
