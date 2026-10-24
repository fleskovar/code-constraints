"""scripts/release.py moves every version line together, and nothing else."""

import importlib.util
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("release", ROOT / "scripts" / "release.py")
release = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(release)


def test_write_version_updates_every_version_file(tmp_path):
    for rel in release.VERSION_FILES:
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(ROOT / rel, tmp_path / rel)
    old = release.read_version(tmp_path)
    new = release.next_version(old, "patch")

    release.write_version(new, tmp_path)

    for rel in release.VERSION_FILES:
        before = (ROOT / rel).read_text(encoding="utf-8")
        after = (tmp_path / rel).read_text(encoding="utf-8")
        assert new in after
        # Only the version line changed: target-version, python_version, etc. stay.
        changed = [a for a, b in zip(after.splitlines(), before.splitlines()) if a != b]
        assert len(changed) == 1 and new in changed[0]


def test_next_version():
    assert release.next_version("1.2.3", "patch") == "1.2.4"
    assert release.next_version("1.2.3", "minor") == "1.3.0"
    assert release.next_version("1.2.3", "major") == "2.0.0"
