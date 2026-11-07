"""Check action pins and the installed dependency set, without broker access."""
import argparse
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
import re

from packaging.requirements import Requirement

ROOT = Path(__file__).resolve().parents[1]


def requirements(path):
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith(('#', '--hash=', '-r ', '-c ')):
            continue
        text = line.removesuffix('\\').strip().split(' --hash=', 1)[0]
        requirement = Requirement(text)
        if requirement.marker is None or requirement.marker.evaluate():
            yield requirement


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)
    errors, action_refs = [], {}
    for path in sorted((ROOT / '.github/workflows').iterdir()):
        if path.suffix not in ('.yml', '.yaml'):
            continue
        for ref in re.findall(r'\buses:\s*([^\s#]+)', path.read_text()):
            if ref.startswith('./'):
                continue
            if not re.fullmatch(r'[\w.-]+/[\w./-]+@[0-9a-f]{40}', ref):
                errors.append(f'{path.name}: action reference is not an immutable commit: {ref}')
                continue
            name, sha = ref.rsplit('@', 1)
            action_refs.setdefault(name, set()).add(sha)
    for action, refs in action_refs.items():
        if len(refs) != 1:
            errors.append(f'{action}: inconsistent action commits across workflows')
    locks = ['requirements.txt', 'requirements-dev.txt']
    for name in locks:
        contents = (ROOT / name).read_text()
        if '--hash=sha256:' not in contents:
            errors.append(f'{name}: missing artifact hashes')
        for requirement in requirements(ROOT / name):
            if len(list(requirement.specifier)) != 1 or next(iter(requirement.specifier)).operator != '==':
                errors.append(f'{name}: dependency is not exactly pinned: {requirement}')
            try:
                installed = version(requirement.name)
            except PackageNotFoundError:
                errors.append(f'{name}: missing installed package {requirement.name}')
                continue
            if not requirement.specifier.contains(installed, prereleases=True):
                errors.append(f'{name}: installed {requirement.name}=={installed} conflicts with {requirement}')
    for name in ['requirements.in', 'requirements-dev.in']:
        for requirement in requirements(ROOT / name):
            try:
                installed = version(requirement.name)
            except PackageNotFoundError:
                errors.append(f'{name}: missing installed package {requirement.name}')
                continue
            if not requirement.specifier.contains(installed, prereleases=True):
                errors.append(f'{name}: installed package is outside declared bounds: {requirement}')
    if errors:
        raise SystemExit('\n'.join(errors))
    print('PASS: consistent immutable action references and installed hash-lock versions')


if __name__ == '__main__':
    main()
