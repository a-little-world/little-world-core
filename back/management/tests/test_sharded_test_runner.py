"""Tests for the deterministic hash-based CI test sharding runner."""

import os
import unittest
from unittest import mock

from back.sharded_test_runner import ShardedDiscoverRunner, _iter_tests, shard_of
from django.test import SimpleTestCase
from django.test.runner import DiscoverRunner

SHARD_COUNT = 6
FAKE_TEST_COUNT = 120


def _build_fake_suite(count=FAKE_TEST_COUNT):
    class _FakeTest(unittest.TestCase):
        def runTest(self):
            pass

    suite = unittest.TestSuite()
    for index in range(count):
        test = _FakeTest()
        test.id = lambda index=index: f"management.tests.test_fake.Case.test_{index:03d}"
        suite.addTest(test)
    return suite


def _ids(suite):
    return {test.id() for test in _iter_tests(suite)}


class ShardOfTests(SimpleTestCase):
    def test_is_deterministic_and_in_range(self):
        for test_id in ("a.b.C.test_x", "management.tests.test_foo.Case.test_bar", ""):
            first = shard_of(test_id, SHARD_COUNT)
            self.assertEqual(first, shard_of(test_id, SHARD_COUNT))
            self.assertGreaterEqual(first, 0)
            self.assertLess(first, SHARD_COUNT)

    def test_single_shard_always_zero(self):
        for test_id in ("a.b.C.test_x", "other.test", ""):
            self.assertEqual(shard_of(test_id, 1), 0)


class ShardedDiscoverRunnerTests(SimpleTestCase):
    def _build_shard(self, shard, total=SHARD_COUNT, suite=None):
        suite = suite if suite is not None else _build_fake_suite()
        with mock.patch.object(DiscoverRunner, "build_suite", return_value=suite):
            runner = ShardedDiscoverRunner()
            with mock.patch.dict(os.environ, {"DJ_TEST_SHARDS": str(total), "DJ_TEST_SHARD": str(shard)}):
                return runner.build_suite()

    def test_shards_are_disjoint_and_cover_everything(self):
        full = _ids(_build_fake_suite())
        seen = set()
        for shard in range(1, SHARD_COUNT + 1):
            shard_ids = _ids(self._build_shard(shard))
            self.assertTrue(shard_ids.isdisjoint(seen), f"shard {shard} overlaps a previous shard")
            seen |= shard_ids
        self.assertEqual(seen, full)

    def test_shard_distribution_is_spread(self):
        for shard in range(1, SHARD_COUNT + 1):
            shard_ids = _ids(self._build_shard(shard))
            self.assertTrue(shard_ids, f"shard {shard} is empty, partition is degenerate")

    def test_single_shard_returns_unfiltered_suite(self):
        full = _ids(_build_fake_suite())
        with mock.patch.object(DiscoverRunner, "build_suite", return_value=_build_fake_suite()):
            runner = ShardedDiscoverRunner()
            with mock.patch.dict(os.environ, {"DJ_TEST_SHARDS": "1", "DJ_TEST_SHARD": "1"}):
                self.assertEqual(_ids(runner.build_suite()), full)

    def test_unset_shards_returns_unfiltered_suite(self):
        full = _ids(_build_fake_suite())
        with mock.patch.object(DiscoverRunner, "build_suite", return_value=_build_fake_suite()):
            runner = ShardedDiscoverRunner()
            with mock.patch.dict(os.environ, {}, clear=False):
                os.environ.pop("DJ_TEST_SHARDS", None)
                os.environ.pop("DJ_TEST_SHARD", None)
                self.assertEqual(_ids(runner.build_suite()), full)

    def test_out_of_range_shard_raises(self):
        with mock.patch.object(DiscoverRunner, "build_suite", return_value=_build_fake_suite()):
            runner = ShardedDiscoverRunner()
            with mock.patch.dict(os.environ, {"DJ_TEST_SHARDS": str(SHARD_COUNT), "DJ_TEST_SHARD": "99"}):
                with self.assertRaises(ValueError):
                    runner.build_suite()
