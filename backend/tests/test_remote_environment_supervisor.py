import json
import signal
import os
import sys
import subprocess
import pytest
from types import SimpleNamespace
from backend.scripts import supervise_environment as supervisor


@pytest.fixture(autouse=True)
def linux_signal_constants(monkeypatch):
    # Windows runs the state/lifecycle tests; the deployed supervisor is Linux.
    monkeypatch.setattr(signal, 'SIGKILL', 9, raising=False)


def test_waits_for_response_before_switch_and_stops_before_starting_new_environment(tmp_path):
    state = tmp_path / 'selection.json'
    state.write_text('{"prefix":""}')
    clock = [0]
    result = supervisor.watch_child(SimpleNamespace(poll=lambda:None), state, 'pp_', 8080,
        now=lambda:clock[0], sleep=lambda seconds:clock.__setitem__(0,clock[0]+seconds), probe=lambda _: 'pp_')
    assert result == 'switch' and clock[0] == 3


def test_wrong_prefix_and_unready_backend_cannot_complete_startup(tmp_path):
    clock = [0]
    result = supervisor.watch_child(SimpleNamespace(poll=lambda:None), tmp_path/'state.json', 'pp_',8080,
        startup_seconds=3, now=lambda:clock[0], sleep=lambda seconds:clock.__setitem__(0,clock[0]+seconds), probe=lambda _: '')
    assert result == 'startup_failed'


def test_failed_target_rolls_back_once_and_retains_audit(tmp_path):
    state=tmp_path/'state.json'
    state.write_text(json.dumps({'prefix':'','previous_prefix':'pp_','operator_gid':'admin'}))
    assert supervisor.rollback(state,'')
    assert supervisor.selected_prefix(state) == 'pp_'
    assert json.loads(state.read_text())['restart_failed']
    assert 'restart_failed_rollback' in state.with_suffix('.audit.jsonl').read_text()
    assert not supervisor.rollback(state,'pp_')


def test_rollback_never_overwrites_a_newer_selection(tmp_path):
    state=tmp_path/'state.json'
    state.write_text('{"prefix":"pp_","previous_prefix":""}')
    assert not supervisor.rollback(state,'')


def test_stop_signals_only_owned_group_and_forces_stuck_children(monkeypatch):
    calls=[]
    monkeypatch.setattr(supervisor.os,'killpg',lambda pid,sig:calls.append((pid,sig)),raising=False)
    waits=[]
    def wait(timeout):
        waits.append(timeout)
        if len(waits)==1: raise subprocess.TimeoutExpired('owned',timeout)
    child=SimpleNamespace(pid=123,poll=lambda:None,wait=wait)
    supervisor.stop_child(child)
    assert calls == [(123,signal.SIGTERM),(123,signal.SIGKILL),(123,signal.SIGKILL)]
    assert waits == [30,10]


def test_stop_reaps_stuck_worker_even_after_master_exited(monkeypatch):
    calls=[]
    monkeypatch.setattr(supervisor.os,'killpg',lambda pid,sig:calls.append((pid,sig)),raising=False)
    supervisor.stop_child(SimpleNamespace(pid=123,poll=lambda:1))
    assert calls == [(123,signal.SIGKILL)]


@pytest.mark.skipif(os.name != 'posix', reason='real process-group termination requires Linux/POSIX')
def test_real_stuck_owned_process_group_is_stopped_before_restart():
    child=subprocess.Popen([sys.executable,'-u','-c',
        'import signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); print("ready",flush=True); time.sleep(60)'],
        start_new_session=True,stdout=subprocess.PIPE,text=True)
    try:
        assert child.stdout.readline().strip() == 'ready'
        supervisor.stop_child(child,grace_seconds=0.1)
        assert child.poll() is not None
    finally:
        supervisor.stop_child(child,grace_seconds=0.1)
        child.stdout.close()
