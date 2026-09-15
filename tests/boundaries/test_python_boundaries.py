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
        "apps/control-api/src/bff_control/domains/projects/service.py",
        "from bff_control.domains.projects.repository import ProjectRepository\n",
    )

    result = _run(tmp_path)

    assert result.returncode == 0, result.stderr


def test_allows_infrastructure_importing_core(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "apps/control-api/src/bff_control/infrastructure/db/database.py",
        "from bff_control.core.settings import DatabaseSettings\n",
    )

    result = _run(tmp_path)

    assert result.returncode == 0, result.stderr


def test_blocks_core_importing_business_domain(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "apps/control-api/src/bff_control/core/security.py",
        "from bff_control.domains.projects.service import ProjectService\n",
    )

    result = _run(tmp_path)

    assert result.returncode == 1
    assert "core modules must not import domains" in result.stderr


def test_blocks_core_importing_api(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "apps/control-api/src/bff_control/core/security.py",
        "from bff_control.api.dependencies import current_user\n",
    )

    result = _run(tmp_path)

    assert result.returncode == 1
    assert "core modules must not import api" in result.stderr


def test_blocks_core_relative_import_of_infrastructure(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "apps/control-api/src/bff_control/core/security.py",
        "from ..infrastructure.db import database\n",
    )

    result = _run(tmp_path)

    assert result.returncode == 1
    assert "core modules must not import infrastructure" in result.stderr


def test_blocks_domain_importing_api_by_relative_path(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "apps/control-api/src/bff_control/domains/projects/service.py",
        "from ...api import dependencies\n",
    )

    result = _run(tmp_path)

    assert result.returncode == 1
    assert "domain modules must not import api" in result.stderr


def test_blocks_cross_domain_repository_import(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "apps/control-api/src/bff_control/domains/bindings/service.py",
        "from bff_control.domains.credentials.repository import CredentialRepository\n",
    )

    result = _run(tmp_path)

    assert result.returncode == 1
    assert "cross-domain imports may not reach another domain's repository" in result.stderr


def test_blocks_cross_domain_models_relative_import(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "apps/control-api/src/bff_control/domains/bindings/service.py",
        "from ..credentials.models import Credential\n",
    )

    result = _run(tmp_path)

    assert result.returncode == 1
    assert "cross-domain imports may not reach another domain's models" in result.stderr


def test_repository_itself_respects_python_boundaries() -> None:
    root = Path(__file__).resolve().parents[2]

    result = _run(root)

    assert result.returncode == 0, result.stderr
