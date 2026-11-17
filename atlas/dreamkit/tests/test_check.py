import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "skills/dream/scripts"))
from check import check  # noqa: E402

EXAMPLE = Path(__file__).parents[1] / "example"


def test_example_passes():
    assert check(EXAMPLE) == []


def test_problems(tmp_path):
    repo = tmp_path / "tier"
    shutil.copytree(EXAMPLE, repo)
    (repo / "topics/orphan.md").write_text("---\nname: Orphan\ndescription: d\ntype: user\n---\nx\n")
    (repo / "topics/bad.md").write_text("no frontmatter\n")
    (repo / "INDEX.md").write_text((repo / "INDEX.md").read_text() + "- [Bad](topics/bad.md)\n- [Gone](topics/gone.md)\n")
    p = check(repo, max_lines=5)
    assert any(x.startswith("INDEX.md has") for x in p)
    assert "topics/orphan.md: not linked from INDEX.md or a page it links" in p
    assert "topics/bad.md: no frontmatter" in p
    assert "INDEX.md: broken link topics/gone.md" in p
    (repo / "topics/orphan.md").write_text("---\nname: Orphan\ntype: guess\n---\n")
    p = check(repo)
    assert "topics/orphan.md: frontmatter has no description" in p
    assert any("type 'guess'" in x for x in p)
