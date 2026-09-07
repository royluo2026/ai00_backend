"""Export unpublished exact desktop definitions; never replace the Catalog."""
import json
import subprocess
from pathlib import Path

from backend.capabilities.registry_next import CapabilityRegistry
from backend.base.desktop_actions import DEFINITIONS, register_desktop_capabilities
from backend.capability_v2.business_definition import business_definition_hash
from backend.tests.support.desktop_round5_fixtures import execute_base_matrix
from backend.tests.support.desktop_round5_agent_fixtures import execute_agent_matrix
from plugins.agent.agent_backend.capabilities import register_capabilities as register_agent
from plugins.agent.agent_backend.capabilities.desktop_actions import DEFINITIONS as AGENT_DEFINITIONS
from plugins.project_management.project_management_backend.capabilities import register_capabilities as register_project
from plugins.project_management.project_management_backend.capabilities.desktop_actions import DEFINITIONS as PROJECT_DEFINITIONS
from backend.tests.support.desktop_round5_project_fixtures import execute_project_matrix
from backend.base.desktop_artifacts import DEFINITIONS as ARTIFACT_DEFINITIONS
from plugins.craft.craft_backend.capabilities.desktop_exchange import DEFINITIONS as EXCHANGE_DEFINITIONS, register_desktop_exchange
from backend.tests.test_desktop_round5_exchange import execute_file_matrix
from backend.base.desktop_templates import DEFINITIONS as TEMPLATE_DEFINITIONS
from plugins.craft.craft_backend.capabilities.desktop_vpps import ID as VPPS_ID, register_desktop_vpps
from backend.tests.test_desktop_round5_gateway import execute_gateway_matrix

ROOT = Path(__file__).resolve().parents[2]


def main():
    registry = CapabilityRegistry()
    register_desktop_capabilities(registry)
    capabilities = [registry.get(row[0], 1).descriptor.model_dump(mode='json') for row in DEFINITIONS]
    register_agent(registry, canvas_runtime=None)
    capabilities.extend(registry.get(capability_id,version).descriptor.model_dump(mode='json') for capability_id,version in [(d[0],d[1]) for d in AGENT_DEFINITIONS]+[('agent.interaction.chat.change.apply',3)])
    register_project(registry)
    capabilities.extend(registry.get(row[0],1).descriptor.model_dump(mode='json') for row in PROJECT_DEFINITIONS)
    register_desktop_exchange(registry)
    capabilities.extend(registry.get(row[0],1).descriptor.model_dump(mode='json') for row in [*ARTIFACT_DEFINITIONS,*EXCHANGE_DEFINITIONS,*TEMPLATE_DEFINITIONS])
    register_desktop_vpps(registry)
    capabilities.append(registry.get(VPPS_ID,1).descriptor.model_dump(mode='json'))
    value = {'status': 'unpublished_candidate', 'source_revision': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        'published_catalog_changed': False, 'machine_passed': False, 'human_approved': False, 'runtime_verified': False,
        'capabilities': capabilities, 'business_definition_hashes': {f"{d['id']}@{d['major_version']}": business_definition_hash(d) for d in capabilities},
        'verification': 'backend/tests/test_desktop_round5_base.py; deterministic SQL/external ports, not live runtime approval'}
    (ROOT / 'docs/governance/desktop-round5-candidates.json').write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    gateway_groups=execute_gateway_matrix()
    for group,rows in gateway_groups.items():
        (ROOT / f'backend/tests/fixtures/desktop_round5_{group}_outcomes.json').write_text(json.dumps({'fixture_kind':'Real registered owner handler + Gateway + LegacyServerGatewayPolicy + actual approval/schema/reliability; deterministic identity and SQL/external I/O ports','rows':rows},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(f'{len(capabilities)} unpublished candidates; {sum(map(len,gateway_groups.values()))} actual owner -> Gateway outcomes')


if __name__ == '__main__':
    main()
