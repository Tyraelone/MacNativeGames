"""Optional device replay gate for the shared shader-variant metadata prewarm.

Set MNG_COLD_SCENE_TSV to an externally stored DM_NVN_TSV recording and
MNG_COLD_SCENE_FRAME to the first visible scene frame. The ordinary test suite
does not require game files or a GPU.
"""

import os
from pathlib import Path
import unittest


def recorded_frame():
    path = os.environ.get("MNG_COLD_SCENE_TSV")
    frame = os.environ.get("MNG_COLD_SCENE_FRAME")
    if not path or not frame:
        return None
    values = {}
    target = frame + "\t"
    with Path(path).open(encoding="utf-8") as recording:
        for line in recording:
            if line.startswith(target):
                _, name, raw = line.rstrip("\n").split("\t", 2)
                values[name] = float(raw)
    return values


class GenericColdSceneTest(unittest.TestCase):
    def test_new_scene_variant_lookup_is_prepared(self):
        values = recorded_frame()
        if values is None:
            self.skipTest("external cold-scene replay was not requested")
        self.assertIn("@cold_prog_variant_ms", values)
        self.assertIn("@pso_new", values)
        self.assertEqual(values["@pso_new"], 0)
        self.assertLessEqual(values["@cold_prog_variant_ms"], 8.0)

    def test_scene_pool_residency_is_batched(self):
        max_commits = os.environ.get("MNG_COLD_RES_MAX_COMMITS")
        values = recorded_frame()
        if values is None or not max_commits:
            self.skipTest("external residency replay was not requested")
        self.assertIn("@cold_res_actual_commits", values)
        self.assertLessEqual(values["@cold_res_actual_commits"], float(max_commits))


if __name__ == "__main__":
    unittest.main()
