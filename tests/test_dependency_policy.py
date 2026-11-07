"""Failure-mode checks for dependency reproducibility enforcement."""
import importlib.util
from pathlib import Path
import pytest

MODULE_PATH = Path(__file__).resolve().parents[1]/'scripts/check_dependency_policy.py'
spec = importlib.util.spec_from_file_location('dependency_policy', MODULE_PATH)
policy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(policy)


@pytest.fixture
def project(tmp_path, monkeypatch):
    workflows = tmp_path/'.github/workflows'
    workflows.mkdir(parents=True)
    workflows.joinpath('test.yml').write_text('steps:\n  - uses: actions/checkout@'+'a'*40+' # v7\n')
    for name in ('requirements.txt', 'requirements-dev.txt'):
        (tmp_path/name).write_text('example==1.0 \\\n    --hash=sha256:'+'b'*64+'\n')
    for name in ('requirements.in', 'requirements-dev.in'):
        (tmp_path/name).write_text('example>=1,<2\n')
    monkeypatch.setattr(policy, 'ROOT', tmp_path)
    monkeypatch.setattr(policy, 'version', lambda name: '1.0')
    return tmp_path


def test_locked_environment_passes(project):
    policy.main([])


def test_mutable_action_cannot_pass(project):
    (project/'.github/workflows/test.yml').write_text('steps:\n - uses: actions/checkout@v7\n')
    with pytest.raises(SystemExit, match='not an immutable'):
        policy.main([])


def test_partial_action_upgrade_is_detected(project):
    (project/'.github/workflows/other.yml').write_text('steps:\n - uses: actions/checkout@'+'c'*40+'\n')
    with pytest.raises(SystemExit, match='inconsistent'):
        policy.main([])


def test_development_lock_cannot_override_production_pin(project):
    (project/'requirements-dev.txt').write_text('example==1.1 \\\n    --hash=sha256:'+'b'*64+'\n')
    with pytest.raises(SystemExit, match='conflicts'):
        policy.main([])


def test_manifest_constraint_change_requires_compatible_lock(project):
    (project/'requirements.in').write_text('example>=2,<3\n')
    with pytest.raises(SystemExit, match='outside declared bounds'):
        policy.main([])


def test_inactive_python_marker_does_not_require_package(project):
    with (project/'requirements.txt').open('a') as f:
        f.write('example==999 ; python_version < "2" \\\n    --hash=sha256:'+'b'*64+'\n')
    policy.main([])


def test_yaml_extension_cannot_bypass_action_policy(project):
    (project/'.github/workflows/other.yaml').write_text('steps:\n - uses: actions/checkout@v7\n')
    with pytest.raises(SystemExit, match='not an immutable'):
        policy.main([])
