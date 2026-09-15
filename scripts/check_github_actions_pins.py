"""Verify third-party GitHub Actions are pinned to immutable commit SHAs."""

from __future__ import annotations

import re
from pathlib import Path

USES_PATTERN = re.compile(
    r"""^\s*-?\s*uses:\s*["']?(?P<value>[^"'#\s]+)["']?""",
)
FULL_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")


def iter_workflow_files(root: Path) -> list[Path]:
    workflow_root = root / ".github" / "workflows"
    if not workflow_root.exists():
        return []

    return sorted(
        path
        for path in workflow_root.rglob("*")
        if path.is_file() and path.suffix in {".yml", ".yaml"}
    )


def find_unpinned_actions(root: Path) -> list[str]:
    violations: list[str] = []

    for workflow in iter_workflow_files(root):
        for line_number, line in enumerate(
            workflow.read_text(encoding="utf-8").splitlines(),
            start=1,
        ):
            match = USES_PATTERN.match(line)
            if match is None:
                continue

            value = match.group("value")

            # Repository-local actions are versioned with the current checkout.
            if value.startswith("./"):
                continue

            # Container actions need digest pinning, not a Git commit.
            if value.startswith("docker://"):
                image = value.removeprefix("docker://")
                if "@sha256:" not in image:
                    violations.append(
                        f"{workflow.relative_to(root)}:{line_number}: "
                        f"container action must use a sha256 digest ({value})",
                    )
                continue

            if "@" not in value:
                violations.append(
                    f"{workflow.relative_to(root)}:{line_number}: "
                    f"action reference is missing @<sha> ({value})",
                )
                continue

            _, ref = value.rsplit("@", 1)
            if FULL_SHA_PATTERN.fullmatch(ref) is None:
                violations.append(
                    f"{workflow.relative_to(root)}:{line_number}: "
                    f"action must be pinned to a full 40-character commit SHA ({value})",
                )

    return violations


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    violations = find_unpinned_actions(root)

    for violation in violations:
        print(violation)

    if violations:
        print(f"GitHub Actions pin check failed: {len(violations)} violation(s)")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
