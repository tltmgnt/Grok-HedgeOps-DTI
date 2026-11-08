"""Detect prohibited tracked paths and common credential patterns without printing values.

This is a limited publication guard, not a complete secret scanner or IP detector.
Native GitHub secret scanning/push protection and owner review remain necessary.
"""
import argparse
from dataclasses import dataclass
import json
from pathlib import Path, PurePosixPath
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
DENIED_PARTS = {'private', 'proprietary', 'secrets', 'credentials'}
DENIED_SUFFIXES = {'.pem', '.key', '.p12', '.pfx', '.sqlite', '.sqlite3', '.db',
                   '.safetensors', '.onnx', '.pkl', '.pickle'}
ENV_EXAMPLES = {'.env.example', '.env.sample', '.env.template'}
PATTERNS = {
    'private-key-header': re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
    'github-token': re.compile(r'\bgh[pousr]_[A-Za-z0-9]{30,}\b|\bgithub_pat_[A-Za-z0-9_]{30,}\b'),
    'provider-api-key': re.compile(r'\bxai-[A-Za-z0-9_-]{24,}\b|\bsk-(?:proj-)?[A-Za-z0-9_-]{24,}\b'),
    'aws-access-key': re.compile(r'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b'),
    'credential-assignment': re.compile(
        r'''(?i)\b(?:ALPACA_(?:PAPER_)?API_(?:KEY|SECRET)|XAI_API_KEY|APCA_API_KEY_ID|APCA_API_SECRET_KEY)\b["']?\s*[:=]\s*["']([^"'\r\n]{20,})["']'''),
}
PLACEHOLDER = re.compile(r'(?i)^(?:replace[_-]|example|placeholder|fake|dummy|your[_-]|\$\{|<)')


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    rule: str
    blob: str = ''


def scan(path, content, *, check_path=True, blob=''):
    findings = []
    name = PurePosixPath(path)
    if check_path:
        prohibited = (bool(set(p.lower() for p in name.parts) & DENIED_PARTS)
                      or name.suffix.lower() in DENIED_SUFFIXES
                      or (name.name.startswith('.env') and name.name not in ENV_EXAMPLES))
        if prohibited:
            findings.append(Finding(path, 0, 'prohibited-public-path', blob))
    if b'\x00' in content:
        return findings
    text = content.decode('utf-8', errors='replace')
    for number, line in enumerate(text.splitlines(), 1):
        for rule, pattern in PATTERNS.items():
            for match in pattern.finditer(line):
                if rule == 'credential-assignment' and PLACEHOLDER.match(match.group(1)):
                    continue
                findings.append(Finding(path, number, rule, blob))
                break
    return findings


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)


def current_findings():
    findings = []
    for raw in git('ls-files', '-z').split(b'\x00'):
        if not raw:
            continue
        path = raw.decode('utf-8')
        local = ROOT / path
        if local.is_symlink():
            # Do not follow a tracked symlink into private files outside the repository.
            findings.append(Finding(path, 0, 'tracked-symlink-requires-review'))
        elif local.is_file():
            findings.extend(scan(path, local.read_bytes()))
    return findings


def history_findings():
    """Inspect unique reachable Git blobs; report identifiers, never matched values."""
    objects = git('rev-list', '--objects', '--all').decode().splitlines()
    candidates = [line.split(' ', 1) for line in objects if ' ' in line]
    if not candidates:
        return []
    query = ''.join(oid + '\n' for oid, _ in candidates).encode()
    metadata = subprocess.check_output(['git', 'cat-file', '--batch-check=%(objectname) %(objecttype)'],
                                       input=query, cwd=ROOT).decode().splitlines()
    blobs = [(oid, path) for (oid, path), meta in zip(candidates, metadata) if meta.endswith(' blob')]
    if not blobs:
        return []
    content = subprocess.check_output(['git', 'cat-file', '--batch'],
                                     input=''.join(oid+'\n' for oid, _ in blobs).encode(), cwd=ROOT)
    findings, offset = [], 0
    for oid, path in blobs:
        end = content.index(b'\n', offset)
        header = content[offset:end].decode().split()
        size = int(header[2])
        body = content[end+1:end+1+size]
        offset = end + 1 + size + 1
        findings.extend(scan(path, body, check_path=False, blob=oid[:12]))
    return findings


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--history', action='store_true', help='Also scan reachable Git history')
    args = parser.parse_args(argv)
    findings = current_findings()
    if args.history:
        findings.extend(history_findings())
    if findings:
        # Do not include matched secret values or source lines in CI logs/artifacts.
        for finding in sorted(set(findings), key=lambda f: (f.path, f.line, f.rule, f.blob)):
            print(json.dumps(finding.__dict__, sort_keys=True))
        print('FAIL: publication boundary needs owner review; secret values omitted')
        return 1
    print('PASS: no prohibited tracked paths or supported credential patterns detected')
    print('LIMIT: this does not prove confidentiality or absence of every secret')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
