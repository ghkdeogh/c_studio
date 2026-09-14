"""Check tracked and unignored candidate files before sharing this source repository."""
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = {'AGENTS.md', '_template/BRIEF.md', '_template/생성상태.md', '_template/renders.md'}
ROOT_FILES = {'AGENTS.md', 'README.md', 'INDEX.md', 'Start-Studio.cmd', '.gitignore', '.gitattributes'}
PREFIXES = ('craft/', 'library/prompts/', 'library/workflows/', 'docs/agent/',
            'docs/runbooks/', '_infra/doc-router/', '_infra/creative-studio/')
SUFFIXES = {'.md', '.json', '.py', '.html', '.css', '.js', '.cjs', '.ps1'}
SECRET = re.compile(r'gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}|'
                    r'AIza[A-Za-z0-9_-]{30,}|sk-[A-Za-z0-9_-]{32,}|'
                    r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----')
PERSONAL_PATH = re.compile(r'[A-Za-z]:[/\\]Users[/\\][^/\\\s]+|/' + r'Users/[^/\s]+|/' + r'home/[^/\s]+')


def allowed(name):
    path = Path(name)
    if name.startswith('productions/'):
        return name[len('productions/'):] in TEMPLATES
    if name in ROOT_FILES or name in {'docs/studio/project-contract.md', '_infra/check_public.py'}:
        return True
    if any(part in {'qa', 'backups', 'logs', '__pycache__', '.studio', 'node_modules'} for part in path.parts):
        return False
    return name.startswith(PREFIXES) and path.suffix in SUFFIXES


def main():
    result = subprocess.run(['git', 'ls-files', '--cached', '--others', '--exclude-standard', '-z'],
                            cwd=ROOT, check=True, stdout=subprocess.PIPE)
    names = sorted(set(result.stdout.decode('utf-8').split('\0')) - {''})
    failures = []
    for name in names:
        path = ROOT / name
        if not allowed(name):
            failures.append((name, 'outside shared source/template scope'))
            continue
        if path.is_symlink() or not path.resolve().is_relative_to(ROOT):
            failures.append((name, 'linked or external path'))
            continue
        if not path.is_file():
            continue
        try:
            content = path.read_text(encoding='utf-8-sig')
        except UnicodeError:
            failures.append((name, 'non-text file'))
            continue
        if SECRET.search(content) or PERSONAL_PATH.search(content):
            failures.append((name, 'possible credential or personal home path; inspect locally'))
    for name, reason in failures:
        print(f'FAIL: {name}: {reason}')
    if failures:
        return 1
    print(f'PASS: {len(names)} source/template files checked. No excluded paths or matched sensitive patterns.')
    print('Pattern checks do not replace reviewing the diff for private content.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
