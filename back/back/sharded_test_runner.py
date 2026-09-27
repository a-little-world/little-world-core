"""Deterministic hash-based sharding for the Django test suite.

CI runs the suite as several parallel jobs. Each job executes the same command
with ``DJ_TEST_SHARDS`` and ``DJ_TEST_SHARD`` set, and this runner keeps only the
tests whose id hashes into that shard. Every test belongs to exactly one shard
and the union over all shards is the full suite, so newly added tests are picked
up automatically without maintaining a manifest.

Unset ``DJ_TEST_SHARDS`` (the local development default) makes the runner a
no-op that executes everything.
"""

import os
import unittest
import zlib

from django.test.runner import DiscoverRunner


def _iter_tests(suite):
    for test in suite:
        if isinstance(test, unittest.TestSuite):
            yield from _iter_tests(test)
        else:
            yield test


def shard_of(test_id: str, total: int) -> int:
    """Return a stable, process-independent shard index in ``[0, total)``.

    ``zlib.crc32`` is used instead of the builtin ``hash`` because the latter is
    randomized per process and would not partition tests consistently.
    """
    return zlib.crc32(test_id.encode("utf-8")) % total


class ShardedDiscoverRunner(DiscoverRunner):
    """Run only the tests hashing to ``DJ_TEST_SHARD`` of ``DJ_TEST_SHARDS``."""

    def build_suite(self, test_labels=None, **kwargs):
        suite = super().build_suite(test_labels, **kwargs)
        total = int(os.environ.get("DJ_TEST_SHARDS", "1") or "1")
        if total <= 1:
            return suite
        shard = int(os.environ.get("DJ_TEST_SHARD", "1") or "1")
        if not 1 <= shard <= total:
            raise ValueError(f"DJ_TEST_SHARD must be in [1, {total}], got {shard}")
        return self.test_suite(test for test in _iter_tests(suite) if shard_of(test.id(), total) == shard - 1)
