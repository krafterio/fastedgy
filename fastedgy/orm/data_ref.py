# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import asyncio
import logging
from typing import cast

from fastedgy.models.base import BaseModel
from fastedgy.models.data_record import DataRecord

logger = logging.getLogger("fastedgy.orm.data_ref")


class DataRefs:
    """Resolves the keys of the data files to the records they created.

    A record declared with ``id("user_system")`` in ``data/*.py`` keeps that key
    across databases, while its id is whatever the sequence handed out. Code
    that has to name such a record - the account an agent writes under, a
    default status - asks here instead of hard-coding an id that only holds in
    one database.

    Resolutions are cached for the life of the process: the loader writes the
    mapping once and a key never changes record. A miss is *not* cached, so a
    worker started before the data was loaded picks the record up as soon as it
    is there.
    """

    def __init__(self, system_user_key: str | None = None) -> None:
        self.system_user_key = system_user_key
        self._ids: dict[str, int] = {}
        self._missing: set[str] = set()
        self._lock = asyncio.Lock()

    async def id(self, key: str) -> int | None:
        """The id of the record [key] names, or None when nothing carries it."""
        if (cached := self._ids.get(key)) is not None:
            return cached

        async with self._lock:
            if (cached := self._ids.get(key)) is not None:
                return cached

            record = await DataRecord.query.get_or_none(key=key)

            if record is None:
                # Warned once per key: a caller asking on every request would
                # otherwise fill the log with the same missing fixture.
                if key not in self._missing:
                    self._missing.add(key)
                    logger.warning("No data record is keyed '%s'", key)

                return None

            self._ids[key] = record.record_id
            self._missing.discard(key)

            return record.record_id

    async def record[M: BaseModel](self, key: str, model_cls: type[M]) -> M | None:
        """The record itself, read through [model_cls].

        None when the key resolves to nothing, and when it resolves to a row
        the model no longer holds - the data file may name a record another
        query has since deleted.
        """
        record_id = await self.id(key)

        return None if record_id is None else await model_cls.query.get_or_none(id=record_id)

    async def system_user_id(self) -> int | None:
        """The account the application acts under, None when it declares none.

        There is deliberately no fallback: taking the first user of the table
        would quietly promote whoever registered first, on any database where
        the data files have not been loaded.
        """
        return None if self.system_user_key is None else await self.id(self.system_user_key)

    async def system_user[M: BaseModel](self, model_cls: type[M]) -> M | None:
        return None if self.system_user_key is None else await self.record(self.system_user_key, model_cls)

    def reset(self, key: str | None = None) -> None:
        """Forgets what was resolved - the whole cache, or a single key.

        For the process that loads the data: a key resolved before the load
        would otherwise keep pointing at the record it replaced.
        """
        if key is None:
            self._ids.clear()
            self._missing.clear()
        else:
            self._ids.pop(key, None)
            self._missing.discard(key)


async def data_ref_id(key: str) -> int | None:
    """The id of the record [key] names, through the registered service."""
    from fastedgy.dependencies import get_service

    return await cast(DataRefs, get_service(DataRefs)).id(key)


async def system_user_id() -> int | None:
    """The id of the account the application acts under, if it declares one."""
    from fastedgy.dependencies import get_service

    return await cast(DataRefs, get_service(DataRefs)).system_user_id()


__all__ = [
    "DataRefs",
    "data_ref_id",
    "system_user_id",
]
