"""Large inserted BOP details must fit their declared bounded read budget."""
from plugins.simulation.simulation_backend.capabilities.alternate_hierarchies import specs


def test_alternate_hierarchy_detail_budget_accepts_large_bop_without_relaxing_lists():
    definitions = {spec.id: spec for spec, _ in specs()}
    detail = definitions['simulation.environment.alternate_hierarchy.get']
    assert detail.execution_budget is not None
    assert detail.execution_budget.max_output_bytes == 32 * 1024 * 1024
    assert detail.execution_budget.memory_class == 'large'
    assert definitions['simulation.environment.alternate_hierarchy.search'].execution_budget is None

