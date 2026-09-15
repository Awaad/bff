from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check_python_boundaries.py"


def _write(root: Path, relative: str, content: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _run(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(root)],
        check=False,
        capture_output=True,
        text=True,
    )


def test_allows_same_domain_repository_import(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "apps/control_api/backend_for_framer/domains/projects/service.py",
        "from backend_for_framer.domains.projects.repository import ProjectRepository\n",
    )

    result = _run(tmp_path)

    assert result.returncode == 0, result.stderr


def test_blocks_core_importing_business_domain(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "apps/control_api/backend_for_framer/core/security.py",
        "from backend_for_framer.domains.projects.service import ProjectService\n",
    )

    result = _run(tmp_path)

    assert result.returncode == 1
    assert "core modules must not import business domains" in result.stderr


def test_blocks_cross_domain_repository_import(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "apps/control_api/backend_for_framer/domains/bindings/service.py",
        "from backend_for_framer.domains.credentials.repository import CredentialRepository\n",
    )

    result = _run(tmp_path)

    assert result.returncode == 1
    assert "cross-domain imports may not reach another domain's repository" in result.stderr


def test_blocks_cross_domain_models_import(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "apps/control_api/backend_for_framer/domains/bindings/service.py",
        "from backend_for_framer.domains.credentials.models import Credential\n",
    )

    result = _run(tmp_path)

    assert result.returncode == 1
    assert "cross-domain imports may not reach another domain's models" in result.stderr
