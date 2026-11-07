"""Regenerate reviewed production/development hash locks with a fixed compiler."""
import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UV_VERSION = '0.13.5'


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--upgrade', action='store_true', help='Resolve newer allowed package versions')
    parser.add_argument('--check', action='store_true', help='Check without modifying committed locks')
    args = parser.parse_args(argv)
    uv = shutil.which('uv')
    if not uv:
        parser.error(f'Install uv=={UV_VERSION} in a development environment first')
    version = subprocess.check_output([uv, '--version'], text=True).split()[1]
    if version != UV_VERSION:
        parser.error(f'Lock generation requires uv=={UV_VERSION}; found {version}')
    with tempfile.TemporaryDirectory() as temporary:
        for source, output in [('requirements.in', 'requirements.txt'),
                               ('requirements-dev.in', 'requirements-dev.txt')]:
            target = ROOT / output
            destination = Path(temporary) / output if args.check else target
            if args.check and target.exists():
                shutil.copyfile(target, destination)
            command = [uv, 'pip', 'compile', '--universal', '--python-version', '3.10',
                       '--python', sys.executable, '--generate-hashes',
                       '--custom-compile-command', 'python scripts/lock_dependencies.py',
                       source, '-o', str(destination)]
            if source == 'requirements-dev.in':
                command.extend(['--constraint', 'requirements.txt'])
            if args.upgrade:
                command.append('--upgrade')
            subprocess.run(command, cwd=ROOT, check=True, stdout=subprocess.DEVNULL)
            if args.check and (not target.exists() or destination.read_bytes() != target.read_bytes()):
                print(f'{output} is out of date; regenerate and review both lockfiles', file=sys.stderr)
                return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
