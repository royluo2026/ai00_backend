import pytest


MEMBERS=[{"vpps_gid":"900","parent_scope_gid":None,"node_level":"process","order_key":"a"},{"vpps_gid":"900","parent_scope_gid":None,"node_level":"process","order_key":"b"}]


def test_root_members_use_non_null_scope_and_repeat_vpps():
    from plugins.craft.craft_backend.data.bop_vpps_groups import MemoryBopVppsGroupStore
    store=MemoryBopVppsGroupStore(); group=store.create_group(space_gid="10",boundary_node_gid="20",actor_gid="30")
    version=store.create_adjustment(group_gid=group["group_gid"],members=MEMBERS,expected_current=None,actor_gid="30")
    assert all(member["parent_scope_gid"] for member in version["members"])
    assert [m["vpps_gid"] for m in version["members"]].count("900")==2


def test_reference_is_preserved_when_adjustment_becomes_current():
    from plugins.craft.craft_backend.data.bop_vpps_groups import MemoryBopVppsGroupStore
    store=MemoryBopVppsGroupStore(); group=store.create_group(space_gid="10",boundary_node_gid="20",actor_gid="30")
    ref=store.create_reference(group_gid=group["group_gid"],members=MEMBERS,actor_gid="30")
    adj=store.create_adjustment(group_gid=group["group_gid"],members=MEMBERS,expected_current=None,actor_gid="30")
    current=store.set_current(group_gid=group["group_gid"],version_gid=adj["version_gid"],expected_current=None,actor_gid="30")
    assert current["reference_version_gid"]==ref["version_gid"]


def test_current_pointer_uses_cas():
    from plugins.craft.craft_backend.data.bop_vpps_groups import MemoryBopVppsGroupStore,VppsGroupError
    store=MemoryBopVppsGroupStore(); group=store.create_group(space_gid="10",boundary_node_gid="20",actor_gid="30")
    adj=store.create_adjustment(group_gid=group["group_gid"],members=MEMBERS,expected_current=None,actor_gid="30")
    store.set_current(group_gid=group["group_gid"],version_gid=adj["version_gid"],expected_current=None,actor_gid="30")
    with pytest.raises(VppsGroupError,match="resource_version_conflict"):store.set_current(group_gid=group["group_gid"],version_gid=adj["version_gid"],expected_current=None,actor_gid="30")


def test_generation_identity_is_stable_and_isolated_per_target_group():
    from plugins.craft.craft_backend.data.bop_vpps_groups import MemoryBopVppsGroupStore
    s=MemoryBopVppsGroupStore();a=s.create_group(space_gid="10",boundary_node_gid="20",actor_gid="30");b=s.create_group(space_gid="10",boundary_node_gid="21",actor_gid="30")
    kw={"members":MEMBERS,"actor_gid":"30","reference_version_gid":"700","matcher_policy_hash":"sha256:"+"a"*64}
    first=s.create_generated(group_gid=a["group_gid"],**kw); replay=s.create_generated(group_gid=a["group_gid"],**kw); other=s.create_generated(group_gid=b["group_gid"],**kw)
    assert replay["version_gid"]==first["version_gid"]
    assert other["version_gid"]!=first["version_gid"]
