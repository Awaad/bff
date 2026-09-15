from pathlib import Path

from scripts.check_github_actions_pins import find_unpinned_actions


def _write_workflow(root: Path, body: str) -> None:
    workflow = root / ".github" / "workflows" / "ci.yml"
    workflow.parent.mkdir(parents=True, exist_ok=True)
    workflow.write_text(body, encoding="utf-8")


def test_accepts_full_commit_sha(tmp_path: Path) -> None:
    _write_workflow(
        tmp_path,
        "steps:\n  - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1\n",
    )

    assert find_unpinned_actions(tmp_path) == []


def test_rejects_moving_major_tag(tmp_path: Path) -> None:
    _write_workflow(
        tmp_path,
        "steps:\n  - uses: actions/checkout@v7\n",
    )

    violations = find_unpinned_actions(tmp_path)

    assert len(violations) == 1
    assert "full 40-character commit SHA" in violations[0]


def test_allows_repository_local_actions(tmp_path: Path) -> None:
    _write_workflow(
        tmp_path,
        "steps:\n  - uses: ./.github/actions/setup\n",
    )

    assert find_unpinned_actions(tmp_path) == []


def test_container_actions_require_digest(tmp_path: Path) -> None:
    _write_workflow(
        tmp_path,
        "steps:\n  - uses: docker://alpine:3.22\n",
    )

    violations = find_unpinned_actions(tmp_path)

    assert len(violations) == 1
    assert "sha256 digest" in violations[0]
