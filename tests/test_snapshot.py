from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from herdr_runtime.snapshot import SnapshotError, changed_paths, clean_snapshot  # noqa: E402


def make_repo(root: Path) -> Path:
    repo = root / "project"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True, capture_output=True)
    (repo / "README.md").write_text("start\n")
    subprocess.run(["git", "-C", str(repo), "add", "README.md"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=Test",
                    "-c", "user.email=test@example.invalid", "commit", "-qm", "initial"],
                   check=True, capture_output=True)
    return repo


class SnapshotTests(unittest.TestCase):
    def test_clean_identity_is_stable_and_dirt_blocks(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = make_repo(Path(directory))
            observed = clean_snapshot(repo)
            self.assertEqual(observed["repo"], str(repo.resolve()))
            self.assertEqual(observed["branch"], "main")
            self.assertEqual(observed, clean_snapshot(repo))
            (repo / "README.md").write_text("changed\n")
            with self.assertRaisesRegex(SnapshotError, "existing tracked"):
                clean_snapshot(repo)

    def test_untracked_nested_and_symlink_checkout_block(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo = make_repo(root)
            (repo / "untracked.txt").write_text("data")
            with self.assertRaisesRegex(SnapshotError, "untracked"):
                clean_snapshot(repo)
            (repo / "untracked.txt").unlink()
            (repo / "sub").mkdir()
            with self.assertRaisesRegex(SnapshotError, "exact Git checkout root"):
                clean_snapshot(repo / "sub")
            link = root / "linked"
            link.symlink_to(repo, target_is_directory=True)
            with self.assertRaisesRegex(SnapshotError, "non-symlink"):
                clean_snapshot(link)

    def test_changed_paths_preserves_names_and_includes_untracked_files(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = make_repo(Path(directory))
            observed = clean_snapshot(repo)
            base = observed["base_head"]
            (repo / "README.md").write_text("changed\n")
            (repo / " nested.txt").write_text("new\n")
            (repo / "sub").mkdir()
            (repo / "sub" / "note.txt").write_text("new\n")
            self.assertEqual(changed_paths(Path(observed["repo"]), base, observed["work_snapshot"]),
                             {"README.md", " nested.txt", "sub/note.txt"})
            with self.assertRaisesRegex(SnapshotError, "assigned base_head invalid"):
                changed_paths(Path(observed["repo"]), "not-a-commit", observed["work_snapshot"])

    def test_rename_exposes_removed_and_added_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = make_repo(Path(directory))
            (repo / "outside.txt").write_text("content moved into allowed scope\n")
            subprocess.run(["git", "-C", str(repo), "add", "outside.txt"],
                           check=True, capture_output=True)
            subprocess.run(["git", "-C", str(repo), "-c", "user.name=Test",
                            "-c", "user.email=test@example.invalid", "commit", "-qm", "second"],
                           check=True, capture_output=True)
            observed = clean_snapshot(repo)
            (repo / "allowed").mkdir()
            subprocess.run(["git", "-C", str(repo), "mv", "outside.txt", "allowed/moved.txt"],
                           check=True, capture_output=True)
            self.assertEqual(changed_paths(Path(observed["repo"]), observed["base_head"],
                                           observed["work_snapshot"]),
                             {"outside.txt", "allowed/moved.txt"})

    def test_changed_branch_or_rewound_head_cannot_publish_as_original_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = make_repo(Path(directory))
            (repo / "README.md").write_text("second commit\n")
            subprocess.run(["git", "-C", str(repo), "add", "README.md"],
                           check=True, capture_output=True)
            subprocess.run(["git", "-C", str(repo), "-c", "user.name=Test",
                            "-c", "user.email=test@example.invalid", "commit", "-qm", "second"],
                           check=True, capture_output=True)
            observed = clean_snapshot(repo)
            subprocess.run(["git", "-C", str(repo), "switch", "-q", "-c", "other"],
                           check=True, capture_output=True)
            with self.assertRaisesRegex(SnapshotError, "branch differs"):
                changed_paths(Path(observed["repo"]), observed["base_head"],
                              observed["work_snapshot"])
            subprocess.run(["git", "-C", str(repo), "switch", "-q", "main"],
                           check=True, capture_output=True)
            subprocess.run(["git", "-C", str(repo), "-c", "user.name=Test",
                            "-c", "user.email=test@example.invalid", "commit",
                            "--allow-empty", "-qm", "forward"],
                           check=True, capture_output=True)
            self.assertEqual(changed_paths(Path(observed["repo"]), observed["base_head"],
                                           observed["work_snapshot"]), set())
            subprocess.run(["git", "-C", str(repo), "reset", "--hard", "HEAD~2"],
                           check=True, capture_output=True)
            with self.assertRaisesRegex(SnapshotError, "no longer an ancestor"):
                changed_paths(Path(observed["repo"]), observed["base_head"],
                              observed["work_snapshot"])


if __name__ == "__main__":
    unittest.main()
