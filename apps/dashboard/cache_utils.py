import time

from django.core.cache import cache

VERSION_KEY = "dash:version"


def cache_key(path):
    """Every cached dashboard response is tied to the current data version."""
    return f"dash:{cache.get(VERSION_KEY, 0)}:{path}"


def bump_version():
    """Make every cached dashboard response stale at once."""
    cache.set(VERSION_KEY, time.time_ns(), None)