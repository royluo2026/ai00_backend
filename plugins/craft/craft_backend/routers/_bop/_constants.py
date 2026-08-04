"""
backend/routers/_bop/_constants.py
─────────────────────────────────
BOP 子包共享常量：权限 Depends、SQL 列名/键名、SQL 模板、映射表等。
"""
from pathlib import Path as _Path

from backend.platform_sdk.auth import require_role

# ── 权限分组 ─────────────────────────────────────────────────────────────────
_SUPER_ADMIN = require_role("super_admin")
_ADMIN = require_role("super_admin", "knowledge_admin")
_WRITE = require_role("super_admin", "team_admin", "project_admin", "knowledge_admin", "member")
_READ  = require_role("super_admin", "team_admin", "project_admin",
                      "rule_admin", "knowledge_admin", "member")

# ── 工段 ─────────────────────────────────────────────────────────────────────
_SEC_KEYS = ['gid','name','factory_gid','sort_order','color','canvas_x','canvas_y','canvas_w','canvas_h','owner_gid','created_at']
_SEC_COLS = "gid,name,factory_gid,sort_order,color,canvas_x,canvas_y,canvas_w,canvas_h,owner_gid,created_at"

# ── 工位 ─────────────────────────────────────────────────────────────────────
_STA_KEYS = ['gid','code','name','factory_section_gid','canvas_x','canvas_y','takt_time','height_mm','meta','created_at']
_STA_COLS = "gid,code,name,factory_section_gid,canvas_x,canvas_y,takt_time,height_mm,meta,created_at"

# ── BOP 版本 ──────────────────────────────────────────────────────────────────
_VER_KEYS = ['gid','project_gid','factory_gid','vehicle_model_gid',
             'version_tag','bop_name','version_family_gid',
             'parent_version_gid','change_note',
             'maturity','takt_time','status','frozen_at','published_at','archived_at',
             'version_type','pbom_version_gid','owner_gid',
             'data_stage',
             'meta','created_at','updated_at']
_VER_COLS = ("gid,project_gid,factory_gid,vehicle_model_gid,"
             "version_tag,bop_name,version_family_gid,"
             "parent_version_gid,change_note,"
             "maturity,takt_time,status,frozen_at,published_at,archived_at,"
             "version_type,pbom_version_gid,owner_gid,"
             "data_stage,"
             "meta,created_at,updated_at")

# ── 布局模板 ──────────────────────────────────────────────────────────────────
_LTPL_KEYS = ['gid','name','factory_gid','team_id','stations','meta','created_at']
_LTPL_COLS = "gid,name,factory_gid,team_id,stations,meta,created_at"

# ── Fork 预设 ─────────────────────────────────────────────────────────────────
_PRESET_KEYS = ['gid','name','description','include_node_types','field_rules',
                'meta_key_rules','team_gid','created_by','created_at','updated_at']
_PRESET_COLS = ("gid,name,description,include_node_types,field_rules,"
                "meta_key_rules,team_gid,created_by,created_at,updated_at")

# ── BOP 条目 SQL ──────────────────────────────────────────────────────────────
_ENTRY_LIST_SQL = """
    WITH link_counts AS (
        SELECT
            entry_gid,
            SUM(CASE WHEN is_primary = TRUE  THEN 1 ELSE 0 END) AS primary_link_count,
            SUM(CASE WHEN is_primary = FALSE THEN 1 ELSE 0 END) AS tracking_link_count
        FROM workmanship_bop_bop_entry_links
        WHERE version_gid = %s
        GROUP BY entry_gid
    )
    SELECT
        e.gid,
        e.version_gid,
        e.parent_gid,
        e.node_type,
        e.sort_order,
        e.level,
        e.ai00_level,
        e.title,
        e.vpps,
        e.vpps_desc,
        e.parent_bop_title,
        e.child_vpps,
        e.owner_gid,
        e.created_by,
        e.meta,
        e.created_at,
        e.updated_at,
        COALESCE(e.process_flow_pic, '[]') AS process_flow_pic,
        el.gid         AS link_gid,
        el.link_type,
        el.entity_gid,
        CASE
            WHEN v.frozen_at IS NOT NULL THEN el.snapshot_data
            WHEN el.entity_gid IS NOT NULL THEN
                CASE el.link_type
                    WHEN 'bop_line'     THEN JSON_OBJECT('gid',ln.gid,'project_gid',ln.project_gid,'name',ln.title,'version_no',ln.version_no,'owner_gid',ln.owner_gid,'vpps',ln.vpps,'created_at',ln.created_at,'updated_at',ln.updated_at,'ext',ln.ext)
                    WHEN 'bop_station'  THEN JSON_OBJECT('gid',st.gid,'project_gid',st.project_gid,'name',st.title,'version_no',st.version_no,'owner_gid',st.owner_gid,'vpps',st.vpps,'created_at',st.created_at,'updated_at',st.updated_at,'ext',st.ext)
                    WHEN 'bop_process'  THEN JSON_OBJECT('gid',pr.gid,'project_gid',pr.project_gid,'bop_version_gid',pr.bop_version_gid,'name',pr.name,'process_code',pr.process_code,'standard_time',pr.standard_time,'version_no',pr.version_no,'vpps',pr.vpps,'vpps_desc',pr.vpps_desc,'params',pr.params,'source_type',pr.source_type,'source_ref_gid',pr.source_ref_gid,'created_at',pr.created_at,'updated_at',pr.updated_at,'ext',pr.ext)
                    WHEN 'bop_steps'    THEN JSON_OBJECT('gid',op.gid,'project_gid',op.project_gid,'name',op.title,'operation_code',op.operation_code,'station_height',op.station_height,'vpps',op.vpps,'vpps_desc',op.vpps_desc,'params',op.params,'source_type',op.source_type,'source_ref_gid',op.source_ref_gid,'created_at',op.created_at,'updated_at',op.updated_at,'vd_time',op.vd_time,'total_time',op.total_time,'floor_height_need',op.floor_height_need,'process_flow_pic',op.process_flow_pic,'process_chart_pic',op.process_chart_pic,'vpps_part',op.vpps_part,'part_feed',op.part_feed,'ext',op.ext)
                    WHEN 'bop_operator' THEN JSON_OBJECT('gid',opr.gid,'project_gid',opr.project_gid,'name',opr.title,'version_no',opr.version_no,'operator_code',opr.operator_code,'headcount',opr.headcount,'owner_gid',opr.owner_gid,'vpps',opr.vpps,'created_at',opr.created_at,'updated_at',opr.updated_at,'ext',opr.ext)
                    WHEN 'pbom_part'    THEN JSON_OBJECT('gid',pb.gid,'snapshot_gid',pb.snapshot_gid,'part_no',pb.part_no,'name',pb.title,'quantity',pb.quantity,'unit',pb.unit,'material',pb.material,'parent_gid',pb.parent_gid,'meta',pb.meta,'vpps',pb.vpps,'vpps_desc',pb.vpps_desc,'created_at',pb.created_at)
                END
        END AS entity_data,
        COALESCE(lc.primary_link_count, 0)   AS primary_link_count,
        COALESCE(lc.tracking_link_count, 0)  AS tracking_link_count
    FROM workmanship_bop_bop_entries e
    JOIN workmanship_bop_bop_versions v ON v.gid = e.version_gid
    LEFT JOIN workmanship_bop_bop_entry_links el
        ON el.entry_gid = e.gid AND el.version_gid = e.version_gid AND el.is_primary = TRUE
    LEFT JOIN link_counts lc ON lc.entry_gid = e.gid
    LEFT JOIN workmanship_bop_bop_line     ln  ON ln.gid  = el.entity_gid AND el.link_type = 'bop_line'
    LEFT JOIN workmanship_bop_bop_station  st  ON st.gid  = el.entity_gid AND el.link_type = 'bop_station'
    LEFT JOIN workmanship_bop_bop_process  pr  ON pr.gid  = el.entity_gid AND el.link_type = 'bop_process'
    LEFT JOIN workmanship_bop_bop_steps    op  ON op.gid  = el.entity_gid AND el.link_type = 'bop_steps'
    LEFT JOIN workmanship_bop_bop_operator opr ON opr.gid = el.entity_gid AND el.link_type = 'bop_operator'
    LEFT JOIN workmanship_bop_pbom          pb  ON pb.gid  = el.entity_gid AND el.link_type = 'pbom_part'
    WHERE e.version_gid = %s AND e.is_deleted = FALSE
    ORDER BY e.sort_order
"""

_ENTRY_KEYS = [
    'gid', 'version_gid', 'parent_gid',
    'node_type', 'sort_order', 'level', 'ai00_level',
    'title', 'vpps', 'vpps_desc', 'parent_bop_title', 'child_vpps',
    'owner_gid', 'created_by', 'meta',
    'created_at', 'updated_at',
    'process_flow_pic',
    'link_gid', 'link_type', 'entity_gid', 'entity_data',
    'primary_link_count', 'tracking_link_count',
]

_ENTRY_BY_GID_SQL = """
    SELECT
        e.gid, e.version_gid, e.parent_gid,
        e.node_type, e.sort_order, e.level, e.ai00_level,
        e.title, e.vpps, e.vpps_desc, e.parent_bop_title, e.child_vpps,
        e.owner_gid, e.created_by, e.meta,
        e.created_at, e.updated_at,
        COALESCE(e.process_flow_pic, '[]') AS process_flow_pic,
        el.gid         AS link_gid,
        el.link_type,
        el.entity_gid,
        CASE
            WHEN v.frozen_at IS NOT NULL THEN el.snapshot_data
            WHEN el.entity_gid IS NOT NULL THEN
                CASE el.link_type
                    WHEN 'bop_line'     THEN JSON_OBJECT('gid',ln.gid,'project_gid',ln.project_gid,'name',ln.title,'version_no',ln.version_no,'owner_gid',ln.owner_gid,'vpps',ln.vpps,'created_at',ln.created_at,'updated_at',ln.updated_at,'ext',ln.ext)
                    WHEN 'bop_station'  THEN JSON_OBJECT('gid',st.gid,'project_gid',st.project_gid,'name',st.title,'version_no',st.version_no,'owner_gid',st.owner_gid,'vpps',st.vpps,'created_at',st.created_at,'updated_at',st.updated_at,'ext',st.ext)
                    WHEN 'bop_process'  THEN JSON_OBJECT('gid',pr.gid,'project_gid',pr.project_gid,'bop_version_gid',pr.bop_version_gid,'name',pr.name,'process_code',pr.process_code,'standard_time',pr.standard_time,'version_no',pr.version_no,'vpps',pr.vpps,'vpps_desc',pr.vpps_desc,'params',pr.params,'source_type',pr.source_type,'source_ref_gid',pr.source_ref_gid,'created_at',pr.created_at,'updated_at',pr.updated_at,'ext',pr.ext)
                    WHEN 'bop_steps'    THEN JSON_OBJECT('gid',op.gid,'project_gid',op.project_gid,'name',op.title,'operation_code',op.operation_code,'station_height',op.station_height,'vpps',op.vpps,'vpps_desc',op.vpps_desc,'params',op.params,'source_type',op.source_type,'source_ref_gid',op.source_ref_gid,'created_at',op.created_at,'updated_at',op.updated_at,'vd_time',op.vd_time,'total_time',op.total_time,'floor_height_need',op.floor_height_need,'process_flow_pic',op.process_flow_pic,'process_chart_pic',op.process_chart_pic,'vpps_part',op.vpps_part,'part_feed',op.part_feed,'ext',op.ext)
                    WHEN 'bop_operator' THEN JSON_OBJECT('gid',opr.gid,'project_gid',opr.project_gid,'name',opr.title,'version_no',opr.version_no,'operator_code',opr.operator_code,'headcount',opr.headcount,'owner_gid',opr.owner_gid,'vpps',opr.vpps,'created_at',opr.created_at,'updated_at',opr.updated_at,'ext',opr.ext)
                    WHEN 'pbom_part'    THEN JSON_OBJECT('gid',pb.gid,'snapshot_gid',pb.snapshot_gid,'part_no',pb.part_no,'name',pb.title,'quantity',pb.quantity,'unit',pb.unit,'material',pb.material,'parent_gid',pb.parent_gid,'meta',pb.meta,'vpps',pb.vpps,'vpps_desc',pb.vpps_desc,'created_at',pb.created_at)
                END
        END AS entity_data
    FROM workmanship_bop_bop_entries e
    JOIN workmanship_bop_bop_versions v ON v.gid = e.version_gid
    LEFT JOIN workmanship_bop_bop_entry_links el
        ON el.entry_gid = e.gid AND el.version_gid = e.version_gid AND el.is_primary = TRUE
    LEFT JOIN workmanship_bop_bop_line     ln  ON ln.gid  = el.entity_gid AND el.link_type = 'bop_line'
    LEFT JOIN workmanship_bop_bop_station  st  ON st.gid  = el.entity_gid AND el.link_type = 'bop_station'
    LEFT JOIN workmanship_bop_bop_process  pr  ON pr.gid  = el.entity_gid AND el.link_type = 'bop_process'
    LEFT JOIN workmanship_bop_bop_steps    op  ON op.gid  = el.entity_gid AND el.link_type = 'bop_steps'
    LEFT JOIN workmanship_bop_bop_operator opr ON opr.gid = el.entity_gid AND el.link_type = 'bop_operator'
    LEFT JOIN workmanship_bop_pbom          pb  ON pb.gid  = el.entity_gid AND el.link_type = 'pbom_part'
    WHERE e.gid = %s AND e.is_deleted = FALSE
"""

# ── AI00 逻辑分级 ─────────────────────────────────────────────────────────────
_AI00_LEVEL: dict = {
    'factory_bop': 0,
    'line_process': 1,
    'station_process': 2,
    'operator_process': 3,
    'man': 4, 'station_factory': 4, 'process': 4,
    'equipment_factory': 5, 'tool_factory': 5, 'equipment_need': 5,
    'fixture_factory': 5, 'operation': 5, 'issue': 5,
    'standard_task': 5, 'non_standard_task': 5,
    'contral_plan': 5, 'process_chart': 5,
    'knowledge': 5, 'rule': 5,
    'floor_height_factory': 5,
    'part': 6, 'non_standard_part': 6, 'standard_part': 6,
    'support_material': 6, 'tool_need': 6, 'fixture_need': 6,
    'jack_pos': 6,
}

# ── 快照映射 ──────────────────────────────────────────────────────────────────
_LINK_SNAPSHOT_MAP = {
    'bop_line':           ('workmanship_bop_bop_line',              None),
    'bop_station':        ('workmanship_bop_bop_station',           None),
    'bop_process':        ('workmanship_bop_bop_process',           None),
    'bop_steps':          ('workmanship_bop_bop_steps',             None),
    'bop_operator':       ('workmanship_bop_bop_operator',          None),
    'physical_equipment': ('workmanship_bop_bop_equipments',        None),
    'physical_tool':      ('workmanship_bop_bop_tools',             None),
    'physical_fixture':   ('workmanship_bop_bop_fixtures',          None),
    'project_equipment':  ('workmanship_bop_bop_equipments',        None),
    'project_tooling':    ('workmanship_bop_bop_fixtures',          None),
    'project_tools':      ('workmanship_bop_bop_tools',             None),
    'floor_height':       ('workmanship_bop_bop_floor_height',      None),
    'control_plan':       ('workmanship_bop_bop_control_plan',      None),
    'process_chart':      ('workmanship_bop_bop_process_charts',    None),
    'jack_pos':           ('workmanship_bop_bop_jack_pos',          None),
    'pbom_part':          ('workmanship_bop_pbom',                  None),
    'issue':              ('workmanship_work_issues',               None),
    'task_std':           ('workmanship_work_tasks',                None),
    'task_custom':        ('workmanship_work_tasks',                None),
    'rule_std':           ('workmanship_know_craft_rules',     None),
    'rule_custom':        ('workmanship_know_craft_rules',     None),
}

# ── GID 字段解析映射（entity-detail 面板用） ─────────────────────────────────
# field_name → (table, name_col)
_GID_RESOLVE_MAP: dict = {
    'project_gid':          ('workmanship_proj_projects',            'name'),
    'factory_gid':          ('workmanship_factory_factories',        'name'),
    'factory_section_gid':  ('workmanship_factory_factory_sections', 'name'),
    'vehicle_model_gid':    ('workmanship_proj_vehicle_models',      'name'),
    'version_gid':          ('workmanship_bop_bop_versions',         'bop_name'),
    'bop_version_gid':      ('workmanship_bop_bop_versions',         'bop_name'),
    'pbom_version_gid':     ('workmanship_bop_bop_versions',         'bop_name'),
    'parent_version_gid':   ('workmanship_bop_bop_versions',         'bop_name'),
    'version_family_gid':   ('workmanship_bop_bop_versions',         'bop_name'),
    'factory_line_gid':     ('workmanship_factory_factory_lines',    'name'),
    'station_gid':          ('workmanship_factory_factory_stations', 'name'),
}

# ── 图片上传 ──────────────────────────────────────────────────────────────────
_BOP_PICS_DIR = _Path(__file__).parent.parent.parent.parent.parent.parent / "backend" / "static" / "uploads" / "bop_pics"
_BOP_PICS_MAX = 5 * 1024 * 1024  # 5 MB

# ── 深拷贝实体表 ──────────────────────────────────────────────────────────────
_DEEP_COPY_ENTITY_TABLES: dict = {
    'bop_line':          ('workmanship_bop_bop_line',          []),
    'bop_station':       ('workmanship_bop_bop_station',        []),
    'bop_process':       ('workmanship_bop_bop_process',        []),
    'bop_steps':         ('workmanship_bop_bop_steps',          []),
    'bop_operator':      ('workmanship_bop_bop_operator',       []),
    'project_equipment': ('workmanship_bop_bop_equipments',     ['file_url', 'attachment']),
    'project_tooling':   ('workmanship_bop_bop_fixtures',       ['file_url', 'attachment']),
    'project_tools':     ('workmanship_bop_bop_tools',          ['file_url', 'attachment']),
    'floor_height':      ('workmanship_bop_bop_floor_height',   ['file_url']),
    'jack_pos':          ('workmanship_bop_bop_jack_pos',       ['file_url']),
    'control_plan':      ('workmanship_bop_bop_control_plan',   ['file_url', 'attachment_url']),
    'process_chart':     ('workmanship_bop_bop_process_charts', ['file_url', 'attachment_url']),
}

# 保留 link（新 link GID），共享原 entity_gid（不复制实体）
_SHARED_ENTITY_LINK_TYPES: set = {
    'physical_equipment', 'physical_tool', 'physical_fixture', 'physical_station',
    'issue', 'task_std', 'task_custom', 'knowledge', 'rule_std', 'rule_custom',
}

# 完全跳过（不复制 link，不复制实体）
_SKIP_LINK_TYPES: set = {'pbom_part'}

# ── Fork 可控字段 ─────────────────────────────────────────────────────────────
_FORK_USER_FIELDS = (
    'title', 'vpps', 'vpps_desc', 'parent_bop_title', 'owner_gid',
)

# ── Auto-link 映射 ────────────────────────────────────────────────────────────
_PROCESS_ENTITY_MAP = {
    'line_process':     ('workmanship_bop_bop_line',     'bop_line'),
    'station_process':  ('workmanship_bop_bop_station',  'bop_station'),
    'operator_process': ('workmanship_bop_bop_operator', 'bop_operator'),
    'process':          ('workmanship_bop_bop_process',  'bop_process'),
    'operation':        ('workmanship_bop_bop_steps',    'bop_steps'),
}
_PART_NODE_TYPES = {'part', 'non_standard_part', 'standard_part', 'support_material'}

_LINK_TARGET_TABLE = {
    # asm_* 工艺层级（存入 DB 的 link_type 值）
    'asm_line_process':     'workmanship_bop_bop_line',
    'asm_station_process':  'workmanship_bop_bop_station',
    'asm_operator_process': 'workmanship_bop_bop_operator',
    'asm_process':          'workmanship_bop_bop_process',
    'asm_operation':        'workmanship_bop_bop_steps',
    # GBOP 标准库（关联面板主要使用）
    'gbop':                 'workmanship_tpl_gbop_entries',
    'process_station':      'workmanship_tpl_gbop_entries',
    # 旧 bop_* 别名（向后兼容）
    'bop_line':             'workmanship_bop_bop_line',
    'bop_station':          'workmanship_bop_bop_station',
    'bop_process':          'workmanship_bop_bop_process',
    'bop_steps':            'workmanship_bop_bop_steps',
    'bop_operator':         'workmanship_bop_bop_operator',
    # PBOM 零件
    'pbom_part':            'workmanship_bop_pbom',
    'usesPart':             'workmanship_bop_pbom',
    # 物理实物资源（工厂现有）
    'physical_equipment':   'workmanship_factory_factory_equipments',
    'physical_tool':        'workmanship_factory_factory_tools',
    'physical_fixture':     'workmanship_factory_factory_fixtures',
    'physical_station':     'workmanship_factory_factory_stations',
    # 项目资源需求
    'project_equipment':    'workmanship_bop_bop_equipments',
    'project_tooling':      'workmanship_bop_bop_fixtures',
    'project_tools':        'workmanship_bop_bop_tools',
    'project_roles':        'workmanship_bop_project_roles',
    # 附属信息
    'floor_height':         'workmanship_bop_bop_floor_height',
    'control_plan':         'workmanship_bop_bop_control_plan',
    'process_chart':        'workmanship_bop_bop_process_charts',
    'jack_pos':             'workmanship_bop_bop_jack_pos',
    # 工作项（auto-link repair 不处理，置 None）
    'issue':                None,
    'task_custom':          None,
    'task_std':             None,
    'knowledge':            None,
    'rule_std':             None,
    'rule_custom':          None,
}

# ── Link Summary 目标表映射 ───────────────────────────────────────────────────
_LINK_TARGET_TABLES = {
    # asm_* 工艺层级
    'asm_line_process':     ('workmanship_bop_bop_line',                'gid', None),
    'asm_station_process':  ('workmanship_bop_bop_station',             'gid', None),
    'asm_operator_process': ('workmanship_bop_bop_operator',            'gid', None),
    'asm_operation':        ('workmanship_bop_bop_steps',               'gid', None),
    # GBOP 标准库
    'gbop':                 ('workmanship_tpl_gbop_entries',       'gid', None),
    'process_station':      ('workmanship_tpl_gbop_entries',       'gid', None),
    # 旧 bop_* 别名（向后兼容）
    'bop_line':             ('workmanship_bop_bop_line',                'gid', None),
    'bop_station':          ('workmanship_bop_bop_station',             'gid', None),
    'bop_process':          ('workmanship_bop_bop_process',             'gid', None),
    'bop_steps':            ('workmanship_bop_bop_steps',               'gid', None),
    'bop_operator':         ('workmanship_bop_bop_operator',            'gid', None),
    # PBOM 零件
    'pbom_part':            ('workmanship_bop_pbom',                    'gid', None),
    'usesPart':             ('workmanship_bop_pbom',                    'gid', None),
    # 物理实物资源（工厂现有）
    'physical_equipment':   ('workmanship_factory_factory_equipments',  'gid', None),
    'physical_tool':        ('workmanship_factory_factory_tools',       'gid', None),
    'physical_fixture':     ('workmanship_factory_factory_fixtures',    'gid', None),
    'physical_station':     ('workmanship_factory_factory_stations',    'gid', None),
    # 项目资源需求
    'project_equipment':    ('workmanship_bop_bop_equipments',          'gid', None),
    'project_tooling':      ('workmanship_bop_bop_fixtures',            'gid', None),
    'project_tools':        ('workmanship_bop_bop_tools',               'gid', None),
    'project_roles':        ('workmanship_bop_project_roles',           'gid', None),
    # 附属信息
    'floor_height':         ('workmanship_bop_bop_floor_height',        'gid', None),
    'control_plan':         ('workmanship_bop_bop_control_plan',        'gid', None),
    'process_chart':        ('workmanship_bop_bop_process_charts',      'gid', None),
    'jack_pos':             ('workmanship_bop_bop_jack_pos',            'gid', None),
    # 工作项 / 知识 / 规则
    'issue':                ('workmanship_proj_issues',                 'gid', None),
    'task_custom':          ('workmanship_proj_tasks',                  'gid', None),
    'task_std':             ('workmanship_proj_tasks',                  'gid', None),
    'rule_std':             ('workmanship_know_craft_rules',       'gid', None),
    'rule_custom':          ('workmanship_know_craft_rules',       'gid', None),
}

# ── Smart Fork 截断深度 ───────────────────────────────────────────────────────
_DEPTH_CUTOFF: dict = {
    'station':   {0, 1, 2},
    'process':   {0, 1, 2, 3, 4},
    'operation': {0, 1, 2, 3, 4, 5},
}
