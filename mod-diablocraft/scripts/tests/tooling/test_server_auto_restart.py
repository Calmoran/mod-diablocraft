#!/usr/bin/env python3
"""Exercise stock startup scripts with disposable processes; never run game binaries."""
import json
import os
from pathlib import Path
import pty
import select
import shutil
import signal
import subprocess
import time

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env

ROOT = Path(__file__).resolve().parents[4]
SCRATCH = ROOT / 'azerothcore-wotlk/build/_agent-scratch/auto-restart'
STOCK = ROOT / 'azerothcore-wotlk/apps/startup-scripts/src'
FAKE = '''#!/usr/bin/python3
import json, os, signal, time
from pathlib import Path
state = Path(os.environ['FAKE_STATE'])
runs = state.read_text().splitlines() if state.exists() else []
mode = os.environ['FAKE_MODES'].split(',')[min(len(runs), len(os.environ['FAKE_MODES'].split(','))-1)]
with state.open('a') as f:
    f.write(json.dumps({'time': time.monotonic(), 'mode': mode}) + '\\n')
signal.signal(signal.SIGINT, signal.SIG_IGN if mode == 'ignore' else lambda *_: os._exit(0))
print('FAKE_READY', flush=True)
if mode == 'segv':
    os.kill(os.getpid(), signal.SIGSEGV)
elif mode.isdigit():
    raise SystemExit(int(mode))
else:
    while True:
        try:
            command = input()
        except EOFError:
            time.sleep(0.05)
            continue
        if command == 'server info':
            print('FAKE_SERVER_INFO_OK', flush=True)
        elif command == 'server shutdown':
            raise SystemExit(0)
'''


def prepare():
    SCRATCH.mkdir(parents=True, exist_ok=True)
    fake = SCRATCH / 'fake-command'
    fake.write_text(FAKE)
    fake.chmod(0o755)
    # GDB needs an ELF executable. Bash executes our fake script via -c <config>;
    # GDB follows its exec into Python, without compiling or loading a game server.
    shutil.copy2('/bin/bash', SCRATCH / 'fake-server')
    return fake


def run_case(label, modes, gdb, interaction=None):
    fake = prepare()
    case = SCRATCH / label
    case.mkdir(exist_ok=True)
    state = case / 'runs.jsonl'
    state.unlink(missing_ok=True)
    for path in case.glob('gdb-*'):
        path.unlink()
    command = [str(STOCK / 'simple-restarter'), str(SCRATCH), 'fake-server', '',
               str(fake), '', '', str(gdb), str(case)]
    pid, fd = pty.fork()
    if pid == 0:
        # The fake command is killed with SIGSEGV on purpose; keep the kernel
        # from piping a core to apport for it (or for anything it starts).
        harness_env.limit_core()
        os.environ.update(FAKE_STATE=str(state), FAKE_MODES=modes,
                          AC_STARTUP_SKIP_GUARD='1', DEBUGINFOD_URLS='')
        os.execv(command[0], command)
    output = b''
    started = time.monotonic()
    sent_info = sent_interrupt = sent_shutdown = False
    interrupted_at = None
    status = None
    ended = 0
    try:
        while time.monotonic() - started < 30:
            ready, _, _ = select.select([fd], [], [], 0.1)
            if ready:
                try:
                    data = os.read(fd, 65536)
                except OSError:
                    data = b''
                output += data
            if interaction == 'delay' and b'will restart in 3 seconds' in output and not sent_interrupt:
                os.write(fd, b'\x03')
                sent_interrupt = True
            if interaction and interaction != 'delay' and b'FAKE_READY' in output and not sent_info:
                os.write(fd, b'server info\n')
                sent_info = True
            if interaction and b'FAKE_SERVER_INFO_OK' in output and not sent_interrupt:
                if interaction == 'shutdown':
                    os.write(fd, b'server shutdown\n')
                else:
                    os.write(fd, b'\x03')
                    interrupted_at = time.monotonic()
                sent_interrupt = True
            if interaction == 'ignore' and interrupted_at and time.monotonic() - interrupted_at > 1 and not sent_shutdown:
                assert os.waitpid(pid, os.WNOHANG) == (0, 0), 'ignored SIGINT killed restarter'
                os.write(fd, b'server shutdown\n')
                sent_shutdown = True
            ended, status = os.waitpid(pid, os.WNOHANG)
            if ended:
                break
        else:
            raise AssertionError('test timeout')
    finally:
        if status is None or not ended:
            os.killpg(pid, signal.SIGKILL)
            os.waitpid(pid, 0)
        os.close(fd)
        (case / 'terminal.log').write_bytes(output)
    code = os.waitstatus_to_exitcode(status)
    runs = [json.loads(line) for line in state.read_text().splitlines()]
    expected = 6 if modes == '1' else len(modes.split(','))
    if interaction == 'delay':
        expected = 1
    assert len(runs) == expected, (label, code, runs, output[-3000:])
    if interaction and interaction != 'delay':
        assert b'FAKE_SERVER_INFO_OK' in output, output
    if modes == '1' and interaction != 'delay':
        assert code == 1 and b'Infinite crash loop prevented' in output, output
    else:
        assert code == 0 or (interaction in ('interrupt', 'delay') and code == -signal.SIGINT), (code, output[-3000:])
    gaps = [round(b['time'] - a['time'], 2) for a, b in zip(runs, runs[1:])]
    assert all(2.8 <= gap <= 6 for gap in gaps), gaps
    if gdb and 'segv' in modes:
        logs = '\n'.join(p.read_text() for p in case.glob('gdb-*.txt'))
        assert 'SIGSEGV' in logs and 'Thread 1' in logs and '#0' in logs, logs
        assert b'terminated with exit code: 1' in output, output
    if '2' in modes:
        assert b'terminated with exit code: 2' in output, output
    print(f'PASS {label}: status={code}, runs={len(runs)}, restart gaps={gaps}', flush=True)


RESTARTER_STUB = ("#!/bin/bash\n"
                  "python3 -c 'import json,os,sys;"
                  "print(json.dumps([os.getcwd(),sys.argv[1:],os.environ.get(\"WITH_CONSOLE\")]))' \"$@\"\n"
                  "ulimit -c\n"
                  "echo \"$SHELL\"\n"
                  "exit 23\n")


def assert_real_shell(result):
    """The restarter stub's third output line is the SHELL it was started with."""
    shell = result.stdout.splitlines()[2]
    assert os.path.basename(shell) == 'bash' and os.access(shell, os.X_OK), ('SHELL is not bash', shell, result)


def prepare_wrapper():
    """Isolated repo layout; both server names contain Bash, never game code."""
    prepare()
    repo = SCRATCH / 'wrapper-fixture'
    scripts = repo / 'mod-diablocraft/scripts'
    server = repo / 'azerothcore-wotlk/build/server'
    stock = repo / 'azerothcore-wotlk/apps/startup-scripts/src'
    for path in (scripts, server / 'configs', stock):
        path.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / 'mod-diablocraft/scripts/run_server.sh', scripts)
    for name in ('worldserver', 'authserver'):
        shutil.copy2('/bin/bash', server / name)
        config = server / 'configs' / (name + '.conf')
        config.write_text(FAKE)
        config.chmod(0o755)
    for name in ('starter', 'simple-restarter'):
        shutil.copy2(STOCK / name, stock)
    return repo


def wrapper_contract():
    repo = prepare_wrapper()
    wrapper = repo / 'mod-diablocraft/scripts/run_server.sh'
    stock = repo / 'azerothcore-wotlk/apps/startup-scripts/src/simple-restarter'
    stock.write_text(RESTARTER_STUB)
    for name, gdb in (('worldserver', '1'), ('authserver', '0')):
        # sudo -u torment-game sets SHELL to that account's nologin shell, and GDB starts
        # the inferior through $SHELL (diablocraft-d9t6): the wrapper must hand the
        # restarter a real shell.
        result = subprocess.run([str(wrapper), name], text=True, capture_output=True, check=False,
                                env=dict(os.environ, SHELL='/usr/sbin/nologin'))
        assert result.returncode == 23, result
        assert_real_shell(result)
        cwd, argv, console = json.loads(result.stdout.splitlines()[0])
        assert cwd == str(repo / 'azerothcore-wotlk/build/server')
        assert argv == [cwd, name, '', 'configs/' + name + '.conf', '', '', gdb, '/home/user/torment-crashes/' + name], argv
        assert console == '1' and result.stdout.splitlines()[1] == 'unlimited', result
    for args in ([], ['bad'], ['worldserver', 'extra']):
        result = subprocess.run([str(wrapper), *args], text=True, capture_output=True, check=False)
        assert result.returncode == 2, result
    prepare_wrapper()  # Restore real stock scripts for manual Herdr fake-console proof.
    print('PASS wrapper contract: both modes, config/cwd/crash paths, core limit, console, status, invalid args', flush=True)


def prepare_tree():
    """The game service tree layout: <tree>/server + <tree>/run_server.sh, and no
    in-repo layout at all (service-accounts plan step 3). Bash stands in for the
    binaries; no game code is executed."""
    prepare()
    tree = SCRATCH / 'wrapper-tree-fixture'
    server = tree / 'server'
    for path in (server / 'configs', tree / 'crashes'):
        path.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / 'mod-diablocraft/scripts/run_server.sh', tree / 'run_server.sh')
    for name in ('worldserver', 'authserver'):
        shutil.copy2('/bin/bash', server / name)
        config = server / 'configs' / (name + '.conf')
        config.write_text(FAKE)
        config.chmod(0o755)
    restarter = server / 'simple-restarter'
    restarter.write_text(RESTARTER_STUB)
    restarter.chmod(0o755)
    return tree


def wrapper_tree_contract():
    tree = prepare_tree()
    here = tree / 'run_server.sh'
    repo_wrapper = ROOT / 'mod-diablocraft/scripts/run_server.sh'
    server = str(tree / 'server')
    for name, gdb in (('worldserver', '1'), ('authserver', '0')):
        expected = [server, name, '', 'configs/' + name + '.conf', '', '', gdb,
                    str(tree / 'crashes' / name)]
        for label, command, extra in (
                ('a copy at the tree root', [str(here), name], {}),
                ('the repo copy with DC_GAME_TREE', [str(repo_wrapper), name], {'DC_GAME_TREE': str(tree)})):
            result = subprocess.run(command, text=True, capture_output=True, check=False,
                                    env=dict(os.environ, SHELL='/usr/sbin/nologin', **extra))
            assert result.returncode == 23, (label, name, result)
            assert_real_shell(result)
            cwd, argv, console = json.loads(result.stdout.splitlines()[0])
            assert cwd == server, (label, name, cwd)
            assert argv == expected, (label, name, argv)
            assert console == '1' and result.stdout.splitlines()[1] == 'unlimited', result
    elsewhere = tree / 'elsewhere'
    result = subprocess.run([str(here), 'authserver'], text=True, capture_output=True, check=False,
                            env=dict(os.environ, DC_CRASH_DIR=str(elsewhere)))
    assert json.loads(result.stdout.splitlines()[0])[1][-1] == str(elsewhere), result
    (tree / 'server' / 'simple-restarter').unlink()
    result = subprocess.run([str(here), 'authserver'], text=True, capture_output=True, check=False)
    assert result.returncode == 1 and 'Missing restarter' in result.stderr, result
    for args in ([], ['bad'], ['worldserver', 'extra']):
        result = subprocess.run([str(here), *args], text=True, capture_output=True, check=False)
        assert result.returncode == 2, result
    print('PASS wrapper tree contract: tree copy and DC_GAME_TREE, crash dirs, missing restarter, invalid args', flush=True)


def main():
    wrapper_contract()
    wrapper_tree_contract()
    for gdb in (0, 1):
        for label, modes, interaction in (
            ('clean', '0', None), ('error', '1,0', None),
            ('restart', '2,0', None), ('segv', 'segv,0', None),
            ('loop', '1', None), ('delay-ctrl-c', '1', 'delay'), ('ctrl-c', 'console', 'interrupt'),
            ('ignore-int', 'ignore', 'ignore'), ('console-shutdown', 'console', 'shutdown'),
        ):
            run_case(f'gdb-{gdb}-{label}', modes, gdb, interaction)


if __name__ == '__main__':
    main()
