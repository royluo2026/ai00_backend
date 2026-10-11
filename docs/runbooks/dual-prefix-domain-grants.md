# 单库、共享账号与表边界

2026-10-08 用户确认：连接同一数据库，以不同表区分领域/环境；独立领域账号方案废弃。领域连接 URL 可以全部使用相同账号，test/production 也不要求用户名互斥。不得因共享账号拒绝启动、就绪或候选检查。

领域仍有唯一表 Owner、Repository、迁移和 Capability Gateway 边界。test_ / pp_ 等环境表前缀由受控配置选择；不得把共享账号的数据库访问范围称为物理领域隔离。

runtime_preflight.py 校验完整领域连接、同一 host/port/schema、合法 URL、环境/profile/表前缀一致性，不校验用户名唯一。check_four_scenario_candidate.py 保留两份环境配置及表前缀校验，允许复用账号。

generate_domain_grants.py 的 DOMAIN=USER 绑定允许同名用户；共享账号的授权范围取其覆盖领域表的并集，去重输出，不生成会撤销其他已绑定领域权限的 SQL。脚本只生成文本，不执行授权。verify_single_database_grants.py 复用相同并集。

verify_domain_db_isolation.py 对共享账号验证所绑定领域的表并集；跨前缀访问仅报告观察值，不把允许访问误报为账号冲突或伪称已验证数据库隔离。环境与领域的数据访问边界应通过表前缀、服务授权和静态源码权属验证；需要真实权限修改时由数据库负责人操作。本次不创建、撤销或修改数据库账号。

历史十一/二十二账号及多库 RC 指令均不再作为本项目的部署前置条件。具体发布证据仍按当前产物、契约和运行验证独立记录。
