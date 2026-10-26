"""The core as patches 0027, 0028 and 0029 leave it, for their tests (not a test itself).

`replay(paths)` returns {path: text} for core files at the pinned commit (core-commit.txt) with every numbered patch of
core-patches/ applied to them, in number order, the way the core is built; only the files asked for are written, so a
patch that touches other files is applied for the hunks that matter and no others. `fresh_tree()` is the same for the
whole set of core files the three patches name, applied with a plain `git apply` and no filter, which is the proof that
they apply to a clean pin plus the stack and change exactly the files they name.

AutoBalance (modules/mod-autobalance) is a third-party module with its own history, outside the core's git: its hunks in
0027 are checked against the installed copy by `autobalance()`.

TORMENT_CORE overrides the core repo the pinned files are read from (default: this repo's azerothcore-wotlk). Nothing in
the core is written; scratch is under build/_agent-scratch.
"""
from pathlib import Path
import os
import re
import shutil
import subprocess
import tempfile

REPO = Path(__file__).resolve().parents[2]
CORE = Path(os.environ.get('TORMENT_CORE') or REPO / 'azerothcore-wotlk')
PIN = (REPO / 'core-commit.txt').read_text(encoding='utf-8').split()[0]
PATCHES = REPO / 'core-patches'
STACK = sorted(PATCHES.glob('[0-9][0-9][0-9][0-9]-*.patch'))
OUT = REPO / 'azerothcore-wotlk/build/_agent-scratch/scripts/life64-patched'
LIFE = [PATCHES / '0027-life-64bit.patch', PATCHES / '0028-hits-64bit.patch', PATCHES / '0029-life-tripwire.patch']
MODULE_PREFIX = 'modules/'


def named(patch):
    """The files a patch writes, as the paths it names."""
    return re.findall(r'^\+\+\+ b/(\S+)', Path(patch).read_text(encoding='utf-8'), re.M)


def core_files(patch):
    return [path for path in named(patch) if not path.startswith(MODULE_PREFIX)]


def pristine(path):
    shot = subprocess.run(['git', '-C', str(CORE), 'show', f'{PIN}:{path}'], capture_output=True)
    return shot.stdout if shot.returncode == 0 else None


def seed(tree, paths):
    """Write the pinned text of each path under `tree`; the paths the pin does not have are returned."""
    absent = []
    for path in paths:
        text = pristine(path)
        if text is None:
            absent.append(path)
            continue
        (tree / path).parent.mkdir(parents=True, exist_ok=True)
        (tree / path).write_bytes(text)
    return absent


def replay(paths, stack=None):
    """{path: text} of the given core files with the stack applied to them (the paths of a file a patch adds are included)."""
    stack = STACK if stack is None else stack
    OUT.mkdir(parents=True, exist_ok=True)
    tree = Path(tempfile.mkdtemp(dir=OUT))
    try:
        subprocess.run(['git', 'init', '-q'], cwd=tree, check=True)
        absent = set(seed(tree, paths))
        include = [f'--include={path}' for path in paths if path not in absent]
        for patch in stack:
            done = subprocess.run(['git', 'apply', *include, str(patch)], cwd=tree, capture_output=True, text=True)
            assert done.returncode == 0, f'{patch.name} does not apply on the patches before it:\n' + done.stderr
        return {path: (tree / path).read_text(encoding='utf-8') for path in paths if (tree / path).exists()}
    finally:
        shutil.rmtree(tree)


def life_files():
    """Every core file the three patches name."""
    seen = []
    for patch in LIFE:
        for path in core_files(patch):
            if path not in seen:
                seen.append(path)
    return seen


def fresh_tree():
    """Apply the stack's core patches, whole and unfiltered, to a clean pin; returns {patch name: files that applying it changed}.

    The three Life patches have their AutoBalance hunks left out (`--exclude`): that module is outside the core's git. A patch
    that writes outside the core tree (a module, the AIO folder) is skipped, and so is one whose files the pin does not have.
    """
    paths = []
    for patch in STACK:
        for path in core_files(patch):
            if path not in paths:
                paths.append(path)
    OUT.mkdir(parents=True, exist_ok=True)
    tree = Path(tempfile.mkdtemp(dir=OUT))
    changed = {}
    try:
        subprocess.run(['git', 'init', '-q'], cwd=tree, check=True)
        seed(tree, paths)
        subprocess.run(['git', 'add', '-A'], cwd=tree, check=True, capture_output=True)
        subprocess.run(['git', '-c', 'user.name=t', '-c', 'user.email=t@t', 'commit', '-q', '-m', 'pin'], cwd=tree, check=True)
        for patch in STACK:
            if patch.name.startswith(('0003', '0008', '0019', '0020', '0021')):
                continue
            exclude = [f'--exclude={MODULE_PREFIX}*']
            done = subprocess.run(['git', 'apply', *exclude, str(patch)], cwd=tree, capture_output=True, text=True)
            assert done.returncode == 0, f'{patch.name} does not apply to a clean pin plus the stack:\n' + done.stderr
            status = subprocess.run(['git', 'status', '--porcelain'], cwd=tree, capture_output=True, text=True, check=True).stdout
            changed[patch.name] = sorted(line[3:] for line in status.splitlines())
            subprocess.run(['git', 'add', '-A'], cwd=tree, check=True, capture_output=True)
            subprocess.run(['git', '-c', 'user.name=t', '-c', 'user.email=t@t', 'commit', '-q', '-m', patch.name], cwd=tree, check=True)
            # what this patch changed is what the commit holds
            shown = subprocess.run(['git', 'show', '--name-only', '--format=', 'HEAD'], cwd=tree, capture_output=True, text=True, check=True).stdout
            changed[patch.name] = sorted(shown.split())
        return changed
    finally:
        shutil.rmtree(tree)


def autobalance(patch):
    """{path: text} of the AutoBalance files the patch names, with the patch in: the installed copy if it carries the patch, else a patched copy."""
    wanted = [path for path in named(patch) if path.startswith('modules/mod-autobalance/')]
    if not wanted:
        return {}
    OUT.mkdir(parents=True, exist_ok=True)
    tree = Path(tempfile.mkdtemp(dir=OUT))
    try:
        for path in wanted:
            (tree / path).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(CORE / path, tree / path)
        subprocess.run(['git', 'init', '-q'], cwd=tree, check=True)     # a tree inside this checkout would be read as part of it
        include = [f'--include={path}' for path in wanted]
        carried = subprocess.run(['git', 'apply', '--reverse', '--check', *include, str(patch)], cwd=tree, capture_output=True)
        if carried.returncode != 0:
            done = subprocess.run(['git', 'apply', *include, str(patch)], cwd=tree, capture_output=True, text=True)
            assert done.returncode == 0, f'{patch.name} does not apply to the installed AutoBalance:\n' + done.stderr
        return {path: (tree / path).read_text(encoding='utf-8') for path in wanted}
    finally:
        shutil.rmtree(tree)
