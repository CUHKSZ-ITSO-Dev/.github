import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('resources', Path(__file__).with_name('resources.py'))
resources = importlib.util.module_from_spec(spec)
spec.loader.exec_module(resources)


class ResourceTests(unittest.TestCase):
    def test_cpu_guest_time_is_not_counted_twice(self):
        self.assertEqual(resources.cpu_ticks('cpu 100 20 30 400 50 6 7 8 90 10\n'), (621, 450))

    def test_available_memory_excludes_reclaimable_cache(self):
        self.assertEqual(resources.memory_used('MemTotal: 8192 kB\nMemFree: 1024 kB\nMemAvailable: 4096 kB\n'), 4096 * 1024)

    def test_disk_uses_available_bytes_not_reserved_blocks(self):
        class Stat:
            f_bavail = 12
            f_bfree = 20
            f_frsize = 4096
        with patch.object(resources.os, 'statvfs', return_value=Stat()):
            self.assertEqual(resources.storage('/work'), 12 * 4096)


if __name__ == '__main__':
    unittest.main()
