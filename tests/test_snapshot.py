from pathlib import Path
import hashlib
import json
import os
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


def git(repo: Path, *args: str) -> bytes:
    return subprocess.run(["git", "-C", str(repo), *args], check=True,
                          capture_output=True).stdout


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

    def test_staged_change_cancelled_in_working_tree_is_still_visible(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = make_repo(Path(directory))
            observed = clean_snapshot(repo)
            (repo / "README.md").write_text("staged change\n")
            git(repo, "add", "README.md")
            (repo / "README.md").write_text("start\n")
            self.assertEqual(git(repo, "--no-optional-locks", "-c", "diff.autoRefreshIndex=false",
                                 "diff", "--numstat", observed["base_head"]), b"")
            self.assertEqual(changed_paths(Path(observed["repo"]), observed["base_head"],
                                           observed["work_snapshot"]), {"README.md"})

    def test_staged_addition_deleted_from_working_tree_is_still_visible(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = make_repo(Path(directory))
            observed = clean_snapshot(repo)
            path = repo / "staged only.txt"
            path.write_text("new\n")
            git(repo, "add", "--", path.name)
            path.unlink()
            self.assertEqual(changed_paths(Path(observed["repo"]), observed["base_head"],
                                           observed["work_snapshot"]), {path.name})

    def test_committed_change_cancelled_in_index_or_working_tree_is_visible(self):
        for staged in (False, True):
            with self.subTest(staged=staged), tempfile.TemporaryDirectory() as directory:
                repo = make_repo(Path(directory))
                observed = clean_snapshot(repo)
                (repo / "README.md").write_text("committed change\n")
                git(repo, "add", "README.md")
                git(repo, "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
                    "commit", "-qm", "forward")
                (repo / "README.md").write_text("start\n")
                if staged:
                    git(repo, "add", "README.md")
                self.assertEqual(changed_paths(Path(observed["repo"]), observed["base_head"],
                                               observed["work_snapshot"]), {"README.md"})

    def test_rename_chain_preserves_every_name_across_all_git_layers(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = make_repo(Path(directory))
            names = ["outside space\nΩ.txt", "committed space\n中.txt",
                     "staged space\t\n雪.txt", "working space\nè.txt"]
            (repo / names[0]).write_text("moved content\n")
            git(repo, "add", "--", names[0])
            git(repo, "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
                "commit", "-qm", "rename source")
            observed = clean_snapshot(repo)
            git(repo, "mv", "--", names[0], names[1])
            git(repo, "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
                "commit", "-qm", "committed rename")
            git(repo, "mv", "--", names[1], names[2])
            (repo / names[2]).rename(repo / names[3])
            self.assertEqual(changed_paths(Path(observed["repo"]), observed["base_head"],
                                           observed["work_snapshot"]), set(names))

    def test_mixed_changes_include_untracked_names_but_exclude_ignored(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = make_repo(Path(directory))
            (repo / ".gitignore").write_text("ignored/\n")
            git(repo, "add", ".gitignore")
            git(repo, "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
                "commit", "-qm", "ignore fixture")
            observed = clean_snapshot(repo)
            committed = "committed space\nΩ.txt"
            staged = "staged space\n中.txt"
            untracked = "nested/untracked space\n雪.txt"
            (repo / committed).write_text("committed\n")
            git(repo, "add", "--", committed)
            git(repo, "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
                "commit", "-qm", "forward")
            (repo / staged).write_text("staged\n")
            git(repo, "add", "--", staged)
            (repo / "README.md").write_text("unstaged\n")
            (repo / "nested").mkdir()
            (repo / untracked).write_text("untracked\n")
            (repo / "ignored").mkdir()
            (repo / "ignored" / "secret-free-fixture.txt").write_text("ignored\n")
            self.assertEqual(changed_paths(Path(observed["repo"]), observed["base_head"],
                                           observed["work_snapshot"]),
                             {committed, staged, "README.md", untracked})

    def test_unstaged_changes_preserve_binary_deleted_and_mode_only_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = make_repo(Path(directory))
            contents = {"text space\t\nΩ.txt": b"original\n",
                        "binary space\n中.bin": b"\0original",
                        "deleted space\n雪.txt": b"deleted\n",
                        "mode space\nè.sh": b"mode\n"}
            for name, content in contents.items():
                (repo / name).write_bytes(content)
            git(repo, "add", "--", *contents)
            git(repo, "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
                "commit", "-qm", "unstaged fixtures")
            observed = clean_snapshot(repo)
            (repo / "text space\t\nΩ.txt").write_bytes(b"original\nadded\n")
            (repo / "binary space\n中.bin").write_bytes(b"\0changed")
            (repo / "deleted space\n雪.txt").unlink()
            executable = repo / "mode space\nè.sh"
            executable.chmod(executable.stat().st_mode | 0o111)
            self.assertEqual(changed_paths(Path(observed["repo"]), observed["base_head"],
                                           observed["work_snapshot"]), set(contents))

    def test_changed_paths_does_not_refresh_index_or_modify_contents(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = make_repo(Path(directory))
            observed = clean_snapshot(repo)
            readme = repo / "README.md"
            stat = readme.stat()
            new_file = repo / "new file\nΩ.txt"
            new_file.write_text("staged\n")
            git(repo, "add", "--", new_file.name)
            os.utime(readme, ns=(stat.st_atime_ns, stat.st_mtime_ns + 2_000_000_000))
            new_file.write_text("unstaged\n")
            untracked = repo / "untracked.txt"
            untracked.write_text("untracked\n")
            index = repo / ".git" / "index"
            index_before = index.read_bytes()
            index_stat = index.stat()
            contents_before = {path: path.read_bytes() for path in (readme, new_file, untracked)}
            for _ in range(2):
                self.assertEqual(changed_paths(Path(observed["repo"]), observed["base_head"],
                                               observed["work_snapshot"]),
                                 {new_file.name, untracked.name})
                self.assertEqual(index.read_bytes(), index_before)
                self.assertEqual(index.stat().st_mtime_ns, index_stat.st_mtime_ns)
                self.assertEqual({path: path.read_bytes() for path in contents_before},
                                 contents_before)

    def test_changed_paths_rejects_invalid_checkout_and_git_identities(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo = make_repo(root)
            observed = clean_snapshot(repo)
            canonical = Path(observed["repo"])
            nested = canonical / "nested"
            nested.mkdir()
            link = root / "linked"
            link.symlink_to(repo, target_is_directory=True)
            for invalid in (Path("relative"), nested, link):
                with self.subTest(repo=str(invalid)), self.assertRaises(SnapshotError):
                    changed_paths(invalid, observed["base_head"], observed["work_snapshot"])
            with self.assertRaisesRegex(SnapshotError, "branch differs"):
                changed_paths(canonical, observed["base_head"], "clean-sha256:" + "0" * 64)
            missing_base = "0" * len(observed["base_head"])
            payload = json.dumps([str(canonical), observed["branch"], missing_base, "clean"],
                                 separators=(",", ":"))
            snapshot = "clean-sha256:" + hashlib.sha256(payload.encode()).hexdigest()
            with self.assertRaisesRegex(SnapshotError, "no longer an ancestor"):
                changed_paths(canonical, missing_base, snapshot)
            git(repo, "switch", "-q", "--detach")
            with self.assertRaises(SnapshotError):
                changed_paths(canonical, observed["base_head"], observed["work_snapshot"])

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
