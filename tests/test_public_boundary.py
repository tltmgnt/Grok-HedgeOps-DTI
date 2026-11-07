"""Publication-guard failure modes; fixture credentials are assembled at runtime."""
import importlib.util
import json
from pathlib import Path
import subprocess
import pytest

MODULE = Path(__file__).resolve().parents[1]/'scripts/check_public_boundary.py'
spec = importlib.util.spec_from_file_location('public_boundary', MODULE)
guard = importlib.util.module_from_spec(spec)
# dataclass resolves the defining module through sys.modules.
import sys
sys.modules[spec.name] = guard
spec.loader.exec_module(guard)


def test_private_paths_and_model_files_cannot_be_published():
    for path in ['private/strategy.py', 'proprietary/model.py', '.env', '.env.production',
                 'credentials/broker.json', 'weights/model.safetensors', 'account.sqlite3']:
        assert any(f.rule == 'prohibited-public-path' for f in guard.scan(path, b'ordinary content'))


def test_environment_examples_can_contain_clear_placeholders():
    content = b'XAI_API_KEY="replace_with_your_key"\n'
    assert guard.scan('.env.example', content) == []


def test_provider_token_is_detected_without_value_in_findings():
    token = 'xai-' + 'Ab19'*10
    findings = guard.scan('config.py', ('value="'+token+'"').encode())
    assert findings[0].rule == 'provider-api-key'
    assert token not in json.dumps([f.__dict__ for f in findings])


def test_literal_broker_assignment_is_detected():
    secret = 'A9qB'*10
    content = ('ALPACA_API_SECRET="'+secret+'"').encode()
    assert any(f.rule == 'credential-assignment' for f in guard.scan('config.py', content))


def test_tracked_symlink_is_never_followed(tmp_path, monkeypatch):
    outside = tmp_path.parent/'outside-private-test.txt'
    outside.write_text('private data')
    link = tmp_path/'config.py'
    link.symlink_to(outside)
    monkeypatch.setattr(guard, 'ROOT', tmp_path)
    monkeypatch.setattr(guard, 'git', lambda *args: b'config.py\x00')
    findings = guard.current_findings()
    assert findings[0].rule == 'tracked-symlink-requires-review'
    outside.unlink()


def test_deleted_token_remains_detectable_in_history(tmp_path, monkeypatch):
    def git(*args):
        return subprocess.check_output(['git', *args], cwd=tmp_path)
    git('init', '-q')
    git('config', 'user.name', 'Test')
    git('config', 'user.email', 'test@example.invalid')
    token = 'ghp_' + 'A1b2'*10
    (tmp_path/'config.py').write_text('value="'+token+'"\n')
    git('add', 'config.py')
    git('commit', '-qm', 'Fixture credential')
    (tmp_path/'config.py').write_text('value="removed"\n')
    git('add', 'config.py')
    git('commit', '-qm', 'Remove fixture credential')
    monkeypatch.setattr(guard, 'ROOT', tmp_path)
    assert guard.current_findings() == []
    findings = guard.history_findings()
    assert any(f.rule == 'github-token' and f.blob for f in findings)
    assert token not in json.dumps([f.__dict__ for f in findings])


def test_normal_public_code_is_not_blocked():
    assert guard.scan('paper_research_agent.py', b'key = os.getenv("XAI_API_KEY", "")\n') == []


def test_private_key_header_is_detected():
    header = '-----BEGIN ' + 'PRIVATE KEY-----'
    assert any(f.rule == 'private-key-header' for f in guard.scan('config.txt', header.encode()))
