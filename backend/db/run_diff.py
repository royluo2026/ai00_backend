import sys, io, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

from pathlib import Path

SCHEMA_PREFIX_MAP = {
    'app':         'workmanship_app_',
    'auth':        'workmanship_auth_',
    'bop':         'workmanship_bop_',
    'factory':     'workmanship_factory_',
    'integration': 'workmanship_int_',
    'knowledge':   'workmanship_',
    'proj':        'workmanship_proj_',
    'template':    'workmanship_tpl_',
    'work':        'workmanship_work_',
}

KNOWLEDGE_PREFIX = {
    'knowledge_entries':    'workmanship_know_entries',
    'knowledge_folders':    'workmanship_know_folders',
    'knowledge_items':      'workmanship_know_items',
    'knowledge_favorites':  'workmanship_know_favorites',
    'knowledge_recent':     'workmanship_know_recent',
    'craft_rules':          'workmanship_know_craft_rules',
    'onto_classes':         'workmanship_onto_classes',
    'onto_properties':      'workmanship_onto_properties',
    'onto_relations':       'workmanship_onto_relations',
    'onto_axioms':          'workmanship_onto_axioms',
}

def pg_to_mysql_table(schema, table):
    if schema == 'knowledge':
        return KNOWLEDGE_PREFIX.get(table, 'workmanship_know_' + table)
    prefix = SCHEMA_PREFIX_MAP.get(schema, 'workmanship_' + schema + '_')
    return prefix + table

REPO = Path(r'D:\luoyi8\vault\projects\py\AI00\AI00_root\AI00_root_web')

def _extract_create_cols(text):
    tables = {}
    for m in re.finditer(
        r'CREATE TABLE IF NOT EXISTS\s+(\w+)\s*\((.*?)\)\s*ENGINE=InnoDB',
        text, re.DOTALL | re.IGNORECASE
    ):
        tbl = m.group(1)
        body = m.group(2)
        cols = set()
        for line in body.splitlines():
            s = line.strip().rstrip(',')
            if not s:
                continue
            up = s.upper()
            if any(up.startswith(k) for k in ('PRIMARY', 'UNIQUE', 'INDEX', 'KEY',
                                               'CONSTRAINT', '--', '/*', 'ENGINE')):
                continue
            tok = re.match(r'`?(\w+)`?', s)
            if tok:
                cols.add(tok.group(1))
        tables[tbl] = cols
    return tables

def load_mysql_tables():
    schema_sql = (REPO / 'backend' / 'db' / 'mysql_schema.sql').read_text(encoding='utf-8')
    migrate_py = (REPO / 'backend' / 'db' / 'migrate.py').read_text(encoding='utf-8')
    all_tables = {}
    all_tables.update(_extract_create_cols(schema_sql))
    all_tables.update(_extract_create_cols(migrate_py))
    return all_tables

mysql_tables = load_mysql_tables()
print(f'[MySQL] {len(mysql_tables)} tables (schema.sql + migrate.py)')

dump_file = REPO / 'backend' / 'db' / 'pg_dump.txt'
pg_tables = {}
for line in dump_file.read_text(encoding='utf-8').splitlines():
    parts = line.strip().split()
    if len(parts) < 2:
        continue
    full_table = parts[0]
    col_name   = parts[1]
    if '.' not in full_table:
        continue
    schema, table = full_table.split('.', 1)
    mysql_name = pg_to_mysql_table(schema, table)
    pg_tables.setdefault(mysql_name, set()).add(col_name)

print(f'[PG]    {len(pg_tables)} tables')
print('=' * 70)

missing_tables = sorted(set(pg_tables) - set(mysql_tables))
if missing_tables:
    print(f'\nMISSING TABLES ({len(missing_tables)}) -- PG has, MySQL lacks:')
    for t in missing_tables:
        cols = sorted(pg_tables[t])
        suffix = '...' if len(cols) > 8 else ''
        print(f'  {t}  [{len(cols)} cols]: {", ".join(cols[:8])}{suffix}')
else:
    print('\nOK: all PG tables exist in MySQL')

print('=' * 70)
col_issues = []
for pg_tbl, pg_cols in sorted(pg_tables.items()):
    if pg_tbl not in mysql_tables:
        continue
    my_cols = mysql_tables[pg_tbl]
    missing_cols = sorted(pg_cols - my_cols)
    extra_cols   = sorted(my_cols - pg_cols)
    if missing_cols or extra_cols:
        col_issues.append((pg_tbl, missing_cols, extra_cols))

if col_issues:
    print(f'\nCOLUMN DIFFS in {len(col_issues)} tables:')
    for tbl, missing, extra in col_issues:
        print(f'  [{tbl}]')
        if missing:
            print(f'    MISSING (PG has, MySQL lacks): {", ".join(missing)}')
        if extra:
            print(f'    EXTRA   (MySQL has, PG lacks):  {", ".join(extra)}')
else:
    print('\nOK: all matched tables have identical columns')

print('=' * 70)
print('Done')
