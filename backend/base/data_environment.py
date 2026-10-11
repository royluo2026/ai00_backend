"""Base-owned server-wide data environment selection; fixed test schema baseline."""
from __future__ import annotations

import json
import os
import re
import threading
from time import perf_counter
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlsplit
from uuid import uuid4

import pymysql

PREFIXES = ('test_', 'pp_', '')
NAMES = {'test_': '开发', 'pp_': '预生产', '': '生产（无前缀）'}
_lock = threading.Lock()
_restart = None
_pending = False


def register_restart(callback):
    global _restart
    _restart = callback


def run_supervised_server(server):
    requested = False
    def request_restart():
        nonlocal requested
        requested = True
        server.should_exit = True
    register_restart(request_restart)
    server.run()
    # Uvicorn can return normally when application lifespan startup failed.
    # A nonzero result is essential for the supervisor's previous-environment recovery.
    if not server.started:
        return 1
    return 75 if requested else 0


def state_path():
    value = os.getenv('AI00_DATA_ENVIRONMENT_STATE_FILE', '')
    if not value:
        raise ValueError('未配置环境切换状态文件')
    return Path(value)


def read_selection():
    path = state_path()
    if not path.exists():
        return 'test_'
    value = json.loads(path.read_text(encoding='utf-8'))['prefix']
    if value not in PREFIXES:
        raise ValueError('无效的数据环境')
    return value


def switching_enabled():
    from backend.base.remote_data_environment import remote_switch_configured
    if remote_switch_configured():
        return os.getenv('AI00_REMOTE_ENVIRONMENT_SUPERVISED') == '1' and _restart is not None
    from backend.db.table_prefix import is_local_test_backend_url
    return (os.getenv('AI00_ALLOW_DATA_ENVIRONMENT_SWITCH') == '1'
            and not os.getenv('ENV_FILE') and not os.getenv('AI00_DEPLOY_PROFILE')
            and is_local_test_backend_url(os.getenv('PUBLIC_URL', ''))
            and bool(os.getenv('AI00_DATA_ENVIRONMENT_STATE_FILE')) and _restart is not None)


def _logical(name, prefix):
    candidate = name[len(prefix):] if prefix and name.startswith(prefix) else name
    return candidate if candidate.startswith(('workmanship_', 'ai00_')) or candidate == 'migration_log' else None


def normalize_record(row, prefix):
    result = dict(row)
    for key in ('TABLE_NAME', 'EVENT_OBJECT_TABLE', 'REFERENCED_TABLE_NAME'):
        value = result.get(key)
        if value and (not prefix or value.startswith(prefix)):
            result[key] = _logical(value, prefix) or value
    # Only SQL identifiers / environment-specific trigger messages are normalized.
    # Column names, defaults and comments are business schema and remain exact.
    for key in ('VIEW_DEFINITION', 'ACTION_STATEMENT', 'EXPRESSION'):
        if key in result and prefix:
            from backend.db.table_prefix import _tokens
            tokens = []
            for kind, token in _tokens(result[key]):
                raw = token.strip('`')
                if kind == 'identifier' and raw.startswith(prefix) and (
                        _logical(raw, prefix) or raw[len(prefix):].startswith('base_historical_uploads_no_')):
                    token = token.replace(prefix, '', 1)
                tokens.append(token)
            result[key] = ''.join(tokens)
    return result


def availability(schemas):
    def differences(left, right):
        a, b = schemas[left], schemas[right]
        return [f'{NAMES[left]} / {NAMES[right]}：{name}' for name in sorted(set(a) | set(b)) if a.get(name) != b.get(name)]
    if not schemas['test_']:
        return {p: ['test_ 基准表结构不可读取或为空'] for p in PREFIXES}
    pp = differences('test_', 'pp_')
    return {'test_': [], 'pp_': pp, '': differences('test_', '') + differences('pp_', '') + pp}


def connect():
    from backend.config import get_settings
    url = urlsplit(get_settings().users_db_url)
    return pymysql.connect(host=url.hostname, port=url.port or 3306, user=unquote(url.username or ''),
                           password=unquote(url.password or ''), database=unquote(url.path.lstrip('/')),
                           charset='utf8mb4', connect_timeout=8, read_timeout=30,
                           cursorclass=pymysql.cursors.DictCursor)


def inspect_schemas(connection):
    schemas = {p: defaultdict(list) for p in PREFIXES}
    def collect(category, rows, namekey='TABLE_NAME', drop=()):
        for row in rows:
            name = row[namekey]
            prefix = next((p for p in ('test_', 'pp_') if name.startswith(p)), '')
            logical = _logical(name, prefix)
            if logical is None:
                continue
            record = normalize_record({k: v for k, v in row.items() if k not in drop}, prefix)
            schemas[prefix][logical].append(json.dumps([category, record], sort_keys=True, default=str))
    with connection.cursor() as cursor:
        for category, table, fields in (
            ('tables', 'TABLES', 'TABLE_NAME,TABLE_TYPE,ENGINE,ROW_FORMAT,TABLE_COLLATION,CREATE_OPTIONS'),
            ('columns', 'COLUMNS', 'TABLE_NAME,COLUMN_NAME,ORDINAL_POSITION,COLUMN_DEFAULT,IS_NULLABLE,COLUMN_TYPE,CHARACTER_SET_NAME,COLLATION_NAME,EXTRA,GENERATION_EXPRESSION,COLUMN_COMMENT'),
            ('indexes', 'STATISTICS', 'TABLE_NAME,INDEX_NAME,NON_UNIQUE,SEQ_IN_INDEX,COLUMN_NAME,COLLATION,SUB_PART,INDEX_TYPE,NULLABLE,INDEX_COMMENT'),
            ('constraints', 'TABLE_CONSTRAINTS', 'TABLE_NAME,CONSTRAINT_NAME,CONSTRAINT_TYPE'),
            ('views', 'VIEWS', 'TABLE_NAME,VIEW_DEFINITION,CHECK_OPTION,IS_UPDATABLE,SECURITY_TYPE,CHARACTER_SET_CLIENT,COLLATION_CONNECTION'),
        ):
            cursor.execute('SELECT ' + fields + ' FROM information_schema.' + table + ' WHERE TABLE_SCHEMA=DATABASE()')
            collect(category, cursor.fetchall(), drop=('CONSTRAINT_NAME',) if category == 'constraints' else ())
        cursor.execute('SELECT k.TABLE_NAME,k.COLUMN_NAME,k.ORDINAL_POSITION,k.POSITION_IN_UNIQUE_CONSTRAINT,k.REFERENCED_TABLE_SCHEMA,k.REFERENCED_TABLE_NAME,k.REFERENCED_COLUMN_NAME,r.MATCH_OPTION,r.UPDATE_RULE,r.DELETE_RULE FROM information_schema.KEY_COLUMN_USAGE k JOIN information_schema.REFERENTIAL_CONSTRAINTS r ON k.CONSTRAINT_SCHEMA=r.CONSTRAINT_SCHEMA AND k.TABLE_NAME=r.TABLE_NAME AND k.CONSTRAINT_NAME=r.CONSTRAINT_NAME WHERE k.TABLE_SCHEMA=DATABASE()')
        collect('foreign_keys', cursor.fetchall())
        cursor.execute('SELECT EVENT_OBJECT_TABLE,EVENT_MANIPULATION,ACTION_ORDER,ACTION_STATEMENT,ACTION_TIMING,SQL_MODE FROM information_schema.TRIGGERS WHERE TRIGGER_SCHEMA=DATABASE()')
        collect('triggers', cursor.fetchall(), 'EVENT_OBJECT_TABLE')
        cursor.execute("SELECT TABLE_NAME FROM information_schema.TABLE_CONSTRAINTS WHERE TABLE_SCHEMA=DATABASE() AND CONSTRAINT_TYPE='CHECK'")
        for name in sorted({r['TABLE_NAME'] for r in cursor.fetchall()}):
            cursor.execute('SHOW CREATE TABLE `' + name.replace('`', '``') + '`')
            ddl = list(cursor.fetchone().values())[1]
            checks = [{'TABLE_NAME': name, 'EXPRESSION': re.sub(r'^\s*CONSTRAINT\s+`[^`]+`\s*', '', line).rstrip().rstrip(',')}
                      for line in ddl.splitlines() if re.search(r'\bCHECK\s*\(', line, re.I)]
            collect('checks', checks)
    return {p: {name: sorted(rows) for name, rows in tables.items()} for p, tables in schemas.items()}


def _require_admin(connection, prefix, gid):
    with connection.cursor() as cursor:
        cursor.execute('SELECT system_role,org_role,is_active FROM `' + prefix + 'workmanship_auth_users` WHERE gid=%s', (gid,))
        user = cursor.fetchone()
    if not user or not user['is_active'] or (user.get('org_role') or user.get('system_role')) != 'super_admin':
        raise ValueError('当前账号在此数据环境中不是有效超管')


def _status(connection):
    from backend.db.table_prefix import current_table_prefix
    differences = availability(inspect_schemas(connection))
    enabled = switching_enabled()
    pending = environment_pending()
    return {'active_prefix': current_table_prefix(), 'baseline_prefix': 'test_', 'pending': pending,
            'switch_enabled': enabled, 'options': [
                {'prefix': p, 'name': NAMES[p], 'available': p in allowed_prefixes() and not differences[p] and enabled and not pending,
                 'difference_count': len(differences[p]),
                 'reasons': (['远端只允许预生产和生产环境，测试环境不可切换'] if p not in allowed_prefixes() else differences[p][:30] or ([] if enabled else ['当前后端未启用受控重启，不能切换']))}
                for p in PREFIXES]}


def get_environment(_payload, context):
    from backend.db.table_prefix import current_table_prefix
    connection = connect()
    try:
        _require_admin(connection, current_table_prefix(), context.user_gid)
        try:
            return _status(connection)
        except Exception:
            return {'active_prefix': current_table_prefix(), 'baseline_prefix': 'test_', 'pending': _pending,
                    'switch_enabled': False, 'options': [
                        {'prefix': p, 'name': NAMES[p], 'available': False, 'difference_count': 0,
                         'reasons': ['表结构检查失败，环境不可用']} for p in PREFIXES]}
    finally:
        connection.close()


def allowed_prefixes():
    return ('pp_', '') if os.getenv('AI00_DEPLOY_PROFILE') == 'production' else PREFIXES


def environment_pending():
    from backend.base.remote_data_environment import remote_switch_configured, selected_prefix
    if remote_switch_configured():
        from backend.db.table_prefix import current_table_prefix
        return _pending or selected_prefix(state_path()) != current_table_prefix()
    return _pending


def change_environment(payload, context):
    global _pending
    from backend.db.table_prefix import current_table_prefix
    with _lock:
        if not switching_enabled() or environment_pending():
            raise ValueError('环境切换不可用或正在重启')
        target = payload['prefix']
        active = current_table_prefix()
        if target not in allowed_prefixes() or payload['expected_prefix'] != active:
            raise ValueError('数据环境已变化，请重新检查')
        connection = connect()
        try:
            _require_admin(connection, active, context.user_gid)
            status = _status(connection)  # Reinspect at submission; never trust client availability.
            option = next(o for o in status['options'] if o['prefix'] == target)
            if not option['available']:
                raise ValueError('表结构不一致或检查失败，禁止切换')
            _require_admin(connection, target, context.user_gid)
        finally:
            connection.close()
        if target == active:
            return {'accepted': True, 'prefix': target, 'restarting': False}
        path = state_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        record = {'prefix': target, 'previous_prefix': active, 'operator_gid': context.user_gid,
                  'changed_at': datetime.now(timezone.utc).isoformat()}
        temporary = path.with_name(path.name + '.' + uuid4().hex + '.tmp')
        try:
            temporary.write_text(json.dumps(record), encoding='utf-8')
            with path.with_suffix('.audit.jsonl').open('a', encoding='utf-8') as audit:
                audit.write(json.dumps(record) + '\n')
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)
        _pending = True
        # Allow the Gateway to persist its audit and deliver the response first.
        timer = threading.Timer(3, _restart)
        timer.daemon = True
        timer.start()
        return {'accepted': True, 'prefix': target, 'restarting': True}


def register_data_environment_capabilities(registry):
    from backend.capability_v2.contracts import ExposurePolicy
    from backend.capability_v2.provider_contracts import CapabilitySpec
    from .contracts import INPUT_SCHEMAS, OUTPUT_SCHEMAS
    from .provider import descriptor_for
    for suffix, handler, risk, confirmation in (
        ('active.get', active_environment, 'read', 'none'),
        ('connection.test', test_active_connection, 'read', 'none'),
        ('get', get_environment, 'read', 'none'), ('change.apply', change_environment, 'write', 'user'),
    ):
        cid = 'base.runtime.data_environment.' + suffix
        spec = CapabilitySpec(id=cid, owner='base', description='Inspect or switch server table-prefix environment.',
                              use_when='A super administrator manages the server data environment.',
                              do_not_use_when='A business plugin accesses domain data.', risk=risk, confirmation=confirmation,
                              idempotent=True, permissions=() if suffix == 'active.get' else ('system.tech_config',), plugin_callable=False,
                              input_schema=INPUT_SCHEMAS[cid], output_schema=OUTPUT_SCHEMAS[cid],
                              tags=('base', 'runtime', 'database', 'admin'))
        descriptor = descriptor_for(spec).model_copy(update={
            'exposure': ExposurePolicy(web=True, api=True, plugin=False, agent=False, mcp=False),
            'agent_output_schema': None, 'delegation_policy': 'none', 'data_classification': 'restricted',
        })
        registry.register(spec, handler, descriptor=descriptor)


def active_environment(_payload, _context):
    from backend.db.table_prefix import current_table_prefix
    return {'prefix': current_table_prefix()}


def test_active_connection(_payload, context):
    """Probe the configured runtime database without accepting credentials or writes."""
    from backend.db.table_prefix import current_table_prefix
    from .runtime_database_config import _connection_error_code
    started = perf_counter()
    result = {'connected': False, 'prefix': current_table_prefix(), 'error_code': ''}
    try:
        connection = connect()
    except Exception as error:
        result['error_code'] = _connection_error_code(error)
    else:
        try:
            _require_admin(connection, result['prefix'], context.user_gid)
            try:
                with connection.cursor() as cursor:
                    cursor.execute('SELECT 1 AS ok')
                    result['connected'] = cursor.fetchone().get('ok') == 1
                if not result['connected']:
                    result['error_code'] = 'connection_failed'
            except Exception as error:
                result['error_code'] = _connection_error_code(error)
        finally:
            connection.close()
    result['elapsed_ms'] = int((perf_counter() - started) * 1000)
    return result
