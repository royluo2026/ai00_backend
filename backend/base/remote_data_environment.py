"""Persistent selection for the single-instance managed remote backend."""
import json
import os
from pathlib import Path
from backend.db.table_prefix import REMOTE_BACKEND_ORIGINS

REMOTE_PREFIXES = ('pp_', '')
_active_prefix = None


def remote_switch_configured(values=None):
    values = os.environ if values is None else values
    return (values.get('AI00_DEPLOY_PROFILE') == 'production'
            and values.get('TABLE_PREFIX') == 'pp_'
            and values.get('PUBLIC_URL', '').rstrip('/') in REMOTE_BACKEND_ORIGINS
            and values.get('AI00_ALLOW_DATA_ENVIRONMENT_SWITCH') == '1'
            and bool(values.get('ENV_FILE')) and Path(values['ENV_FILE']).is_absolute()
            and bool(values.get('AI00_DATA_ENVIRONMENT_STATE_FILE'))
            and Path(values['AI00_DATA_ENVIRONMENT_STATE_FILE']).is_absolute())


def selected_prefix(path):
    if not path.exists():
        return 'pp_'
    if path.is_symlink() or path.stat().st_size > 4096:
        raise ValueError('invalid remote environment state')
    record = json.loads(path.read_text(encoding='utf-8'))
    if record.get('prefix') not in REMOTE_PREFIXES:
        raise ValueError('remote backend permits only pp_ and unprefixed tables')
    return record['prefix']


def activate_remote_environment():
    global _active_prefix
    if not remote_switch_configured():
        return
    if os.getenv('AI00_REMOTE_ENVIRONMENT_SUPERVISED') != '1':
        raise RuntimeError('remote switching requires the managed environment supervisor')
    _active_prefix = selected_prefix(Path(os.environ['AI00_DATA_ENVIRONMENT_STATE_FILE']))
    # Recheck persisted selections on every master start, before serving traffic.
    from backend.base.data_environment import availability, connect, inspect_schemas
    connection = connect()
    try:
        if availability(inspect_schemas(connection))[_active_prefix]:
            raise RuntimeError('selected remote environment schema is unavailable')
    finally:
        connection.close()
    from backend.base.data_environment import register_restart
    # The supervisor watches the atomic selection and restarts the whole master.
    register_restart(lambda: None)


def runtime_table_prefix():
    return _active_prefix if _active_prefix is not None else os.getenv('TABLE_PREFIX', '').strip()
