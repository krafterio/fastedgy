# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).


def setup_timezone(timezone: str):
    import os
    import time

    os.environ["TZ"] = timezone
    time.tzset()


__all__ = [
    "setup_timezone",
]
