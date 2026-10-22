"""A domain-local migration must be registered before schema compilation."""
import json
import re
from pathlib import Path


def test_domain_local_migration_tables_have_explicit_consistent_ownership():
    root = Path(__file__).resolve().parents[2]
    domains = json.loads((root / 'backend/capability_v2/official_domains.json').read_text())['domains']
    ownership = {r['table']: r for r in json.loads((root / 'backend/governance/domain_table_ownership.json').read_text())['tables']}
    inventory = {r['table']: r for r in json.loads((root / 'backend/governance/table_inventory.json').read_text())['tables']}
    missing = []
    for domain in domains:
        for name in domain['database']['schema_paths']:
            if '/domains/' not in name:
                continue
            path = root / name
            for sql in sorted(path.glob('*.sql')) if path.is_dir() else [path]:
                for table in re.findall(r'CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?`?([a-zA-Z_][a-zA-Z0-9_]*)`?\s*\(', sql.read_text(encoding='utf-8'), re.I):
                    if table not in ownership or table not in inventory:
                        missing.append(table)
                        continue
                    for records in (ownership, inventory):
                        assert records[table]['owner'] == domain['domain_id'], table
                        assert records[table]['runtime_domain'] == domain['domain_id'], table
    assert not missing, sorted(set(missing))
