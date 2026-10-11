"""Adopt the managed supervisor when the platform starts Uvicorn directly."""
import os
import sys

from backend.base.remote_data_environment import remote_switch_configured


def adopt_managed_remote_entrypoint():
    if (remote_switch_configured()
            and os.getenv('AI00_REMOTE_ENVIRONMENT_SUPERVISED') != '1'):
        # Replace the initial server instead of leaving a second listener behind.
        # The supervisor marks its Gunicorn child to prevent recursive adoption.
        os.execv(sys.executable, [sys.executable, '-m', 'backend.scripts.supervise_environment'])
