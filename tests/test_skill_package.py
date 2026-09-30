from pathlib import Path
import re
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]


class SkillPackageTests(unittest.TestCase):
    def test_portable_frontmatter_budget_and_conditional_references(self):
        text = (ROOT / "SKILL.md").read_text()
        self.assertTrue(text.startswith("---\n"))
        _, frontmatter, body = text.split("---", 2)
        self.assertRegex(frontmatter, r"(?m)^name: herdr-orchestration$")
        self.assertRegex(frontmatter, r"(?m)^description: .+")
        self.assertLessEqual(len(body.splitlines()), 180)
        self.assertLessEqual(len(body.split()), 1500)
        self.assertIn("scripts/herdr_orchestrate.py", body)
        self.assertNotIn("--prompt-file /path/to/prompt.md", body)
        for target in re.findall(r"\]\(([^)]+)\)", body):
            if target.startswith("http"):
                continue
            self.assertTrue((ROOT / target).is_file(), target)

    def test_document_links_and_scenarios_resolve(self):
        for doc in (ROOT / "README.md", *(ROOT / "references").glob("*.md")):
            body = doc.read_text()
            for target in re.findall(r"\]\(([^)]+)\)", body):
                if target.startswith(("http://", "https://")):
                    continue
                path = target.split("#", 1)[0]
                if path:
                    self.assertTrue((doc.parent / path).exists(), f"{doc.name}: {target}")
        scenarios = (ROOT / "references" / "scenarios.md").read_text()
        for index in range(1, 11):
            self.assertIn(f"U{index:02d}", scenarios)
        metadata = (ROOT / "agents" / "openai.yaml").read_text()
        self.assertIn('display_name: "Herdr Orchestration"', metadata)
        self.assertNotIn("model:", metadata)


if __name__ == "__main__":
    unittest.main()
