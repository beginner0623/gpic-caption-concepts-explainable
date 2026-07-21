import os
from pathlib import Path
import tempfile
import unittest
import zipfile

from scripts.build_code_sync_zip import main


class BuildCodeSyncZipTest(unittest.TestCase):
    def test_preserves_repository_relative_archive_paths(self) -> None:
        previous_cwd = Path.cwd()
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            source = repo / "src" / "pkg" / "module.py"
            source.parent.mkdir(parents=True)
            source.write_text("VALUE = 1\n", encoding="utf-8")
            output = repo / "out" / "sync.zip"

            try:
                os.chdir(repo)
                result = main(
                    [
                        "--output",
                        str(output),
                        "src/pkg/module.py",
                    ]
                )
            finally:
                os.chdir(previous_cwd)

            self.assertEqual(result, 0)
            with zipfile.ZipFile(output) as archive:
                self.assertEqual(archive.namelist(), ["src/pkg/module.py"])


if __name__ == "__main__":
    unittest.main()
