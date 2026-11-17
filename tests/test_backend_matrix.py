"""Keep the published backend feature matrix honest.

docs/BACKEND_MATRIX.md is generated from real builds and runs. This test
regenerates it and fails if the committed file drifts, so a backend change
cannot land without updating the published capability table.
"""

import importlib.util
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _matrix_module():
    path = ROOT / "tools" / "backend_matrix.py"
    spec = importlib.util.spec_from_file_location("backend_matrix", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class BackendMatrixTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = _matrix_module()
        cls.rows = cls.module.measure()

    def test_published_matrix_matches_current_backends(self):
        expected = self.module.render_markdown(self.rows)
        published = (ROOT / "docs" / "BACKEND_MATRIX.md").read_text(encoding="utf-8")
        self.assertEqual(
            published,
            expected,
            "docs/BACKEND_MATRIX.md is stale; run `python tools/backend_matrix.py`",
        )

    def test_every_case_records_a_backend_status(self):
        names = {row["name"] for row in self.rows}
        for name, _category, _source, _expected in self.module.CASES:
            self.assertIn(name, names)
            row = next(row for row in self.rows if row["name"] == name)
            self.assertEqual(set(row["backends"]), set(self.module.BACKENDS))


if __name__ == "__main__":
    unittest.main()
