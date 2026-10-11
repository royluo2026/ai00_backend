"""Single-instance remote Gunicorn lifecycle; never overlap data environments."""
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import urlopen

from backend.base.remote_data_environment import remote_switch_configured, selected_prefix


def stop_child(child, grace_seconds=30):
    if child.poll() is None:
        # Popen creates a private session. Signal only this owned process group.
        try:
            os.killpg(child.pid, signal.SIGTERM)
        except ProcessLookupError:
            child.wait(timeout=10)
            return
        try:
            child.wait(timeout=grace_seconds)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(child.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            child.wait(timeout=10)
    # A master may exit before a stuck worker; reap the owned group before launch.
    try:
        os.killpg(child.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def ready_prefix(port):
    try:
        origin = f'http://127.0.0.1:{port}'
        with urlopen(origin + '/ready', timeout=2) as response:
            if response.status != 200:
                return None
        with urlopen(origin + '/api/runtime/data-environment', timeout=2) as response:
            if response.status != 200:
                return None
            data = json.loads(response.read(1025))
        return data['prefix'] if data.get('prefix') in ('pp_', '') else None
    except Exception:
        return None


def watch_child(child, state, active, port, startup_seconds=180,
                now=time.monotonic, sleep=time.sleep, probe=ready_prefix):
    startup_deadline = now() + startup_seconds
    healthy = False
    changed_at = None
    while child.poll() is None:
        target = selected_prefix(state)
        if target != active:
            changed_at = now() if changed_at is None else changed_at
            if now() - changed_at >= 3:
                return 'switch'
        else:
            changed_at = None
        if not healthy:
            healthy = probe(port) == active
            if not healthy and now() >= startup_deadline:
                return 'startup_failed'
        sleep(1)
    return 'stopped' if healthy else 'startup_failed'


def rollback(state, failed_prefix):
    if not state.exists():
        return False
    record = json.loads(state.read_text(encoding='utf-8'))
    previous = record.get('previous_prefix')
    if (record.get('prefix') != failed_prefix or previous not in ('pp_', '')
            or previous == failed_prefix or record.get('restart_failed')):
        return False
    record.update(prefix=previous, restart_failed=True)
    temporary = state.with_suffix('.rollback.tmp')
    try:
        temporary.write_text(json.dumps(record), encoding='utf-8')
        temporary.replace(state)
        with state.with_suffix('.audit.jsonl').open('a', encoding='utf-8') as audit:
            audit.write(json.dumps({'action':'restart_failed_rollback', 'failed_prefix':failed_prefix,
                                    'prefix':previous}) + '\n')
    finally:
        temporary.unlink(missing_ok=True)
    return True


def main():
    from dotenv import load_dotenv
    from backend.scripts.runtime_preflight import evaluate
    env_file = Path(os.environ.get('ENV_FILE', ''))
    if not env_file.is_absolute():
        raise RuntimeError('managed container requires absolute ENV_FILE')
    errors = evaluate(env_file)
    if errors:
        raise RuntimeError('runtime preflight failed: ' + '; '.join(errors))
    load_dotenv(env_file, override=True, interpolate=False)
    command = [sys.executable, '-m', 'gunicorn', 'backend.main:app', '-c', 'backend/gunicorn.conf.py']
    if os.getenv('AI00_ALLOW_DATA_ENVIRONMENT_SWITCH') != '1':
        os.execv(sys.executable, command)
    if not remote_switch_configured() or os.name != 'posix':
        raise RuntimeError('remote switching requires the production profile and absolute persistent state path on Linux')
    if os.getenv('AI00_WEB_WORKERS', '1') != '1':
        raise RuntimeError('remote switching requires one Gunicorn worker and one backend instance')
    state = Path(os.environ['AI00_DATA_ENVIRONMENT_STATE_FILE'])
    state.parent.mkdir(parents=True, exist_ok=True)
    # Refuse a read-only/missing mount before offering a switch in settings.
    from tempfile import NamedTemporaryFile
    with NamedTemporaryFile(dir=state.parent):
        pass
    environment = dict(os.environ, AI00_REMOTE_ENVIRONMENT_SUPERVISED='1')
    child = None
    stopping = False
    def shutdown(_signum, _frame):
        nonlocal stopping
        stopping = True
        if child is not None:
            stop_child(child)
        raise SystemExit(0)
    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    try:
        while not stopping:
            active = selected_prefix(state)
            child = subprocess.Popen(command, env=environment, start_new_session=True)
            try:
                outcome = watch_child(child, state, active, int(os.environ.get('PORT', '8080')))
            finally:
                stop_child(child)
            if outcome == 'switch':
                print('Restarting remote backend for accepted data environment selection.', flush=True)
                continue
            if outcome == 'startup_failed' and rollback(state, active):
                print('Target startup failed; restoring the previous data environment.', flush=True)
                continue
            return child.returncode or 1
    finally:
        if child is not None:
            stop_child(child)


if __name__ == '__main__':
    sys.exit(main())
