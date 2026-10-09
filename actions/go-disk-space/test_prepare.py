import unittest
from prepare import prepare, SDK_PATHS


class DiskTest(unittest.TestCase):
    def test_enough_space_never_removes_sdks(self):
        removed = prepare('.', 8, free=lambda: 14 * 1024 ** 3,
                          remove=lambda _: self.fail('空间足够不应删除'), exists=lambda _: True)
        self.assertEqual(removed, [])

    def test_stops_after_freeing_enough_space(self):
        space = [6 * 1024 ** 3]
        removed = []
        def remove(path):
            removed.append(path)
            space[0] += 6 * 1024 ** 3
        prepare('.', 8, free=lambda: space[0], remove=remove, exists=lambda _: True)
        self.assertEqual(removed, [SDK_PATHS[0]])

    def test_large_builds_keep_twenty_gib_headroom(self):
        space = [8 * 1024 ** 3]
        removed = []
        def remove(path):
            removed.append(path)
            space[0] += 6 * 1024 ** 3
        prepare('.', 20, free=lambda: space[0], remove=remove, exists=lambda _: True)
        self.assertEqual(removed, list(SDK_PATHS[:2]))

    def test_missing_sdks_are_not_removed(self):
        self.assertEqual(prepare('.', 20, free=lambda: 2 * 1024 ** 3,
                                 remove=lambda _: self.fail('目录不存在'), exists=lambda _: False), [])
