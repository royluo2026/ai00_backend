# 任务：新建版本弹窗中"所属版本族"改为自动判定（已修改，可继续其他工作）

## 背景

BOP 版本管理系统中，新建版本时：
- 用户选择"所属项目" → 自动判定"所属版本族"（版本族名 = 项目名，不含数据阶段）
- 之前有个下拉框让用户手动选版本族，现在改为自动，用户不可选
- 数据阶段（data_stage）单独选择，同族已用过的阶段禁用

## 已完成的修改

### 文件 `lifecycle_panel.js` 中的 `_buildVersionForm` 方法

1. **删除了版本族 select 下拉框**（原 `const famSel = _sel('— 自成新版本族 —')` + 遍历 allVers 填充 option）
2. **替换为一个信息展示区 `famHint`**（div，显示"加入已有版本族「XXX」（现有 N 个版本）" 或 "将成为新版本族「XXX」" 或 "请先选择项目"）
3. **保留隐藏 input `famSel`**（type=hidden），存放自动判定的版本族 gid，供 `refreshStageOptions` 和 `updatePreview` 等旧逻辑继续使用
4. **新增 `refreshFamilyByProject()` 函数**：根据 `projSel` 所选项目的 `projectName`，扫描 `allVers` 中 `bop_name === projName` 的非模板版本，找到即取 `version_family_gid`，找不到则 `famSel.value = ''`（表示这个项目还没建过任何版本——"新族首版"）
5. **projSel 变更事件** 同时触发：`refreshFamilyByProject` → `refreshStageOptions` → `updatePreview`
6. **createBtn 点击** 前也调用 `refreshFamilyByProject()` 确保使用最新数据
7. **初始加载** 时调用 `refreshFamilyByProject()` 和 `refreshStageOptions()` 做初始化

### 版本戳
- `index.html` 中 `v=20260722b` → `v=20260722d`

### 已推送
- `workmanship-web` → `devteam` remote 的 `test` 分支
- `workmanship-backend` → `devteam` remote 的 `test` 分支

## 相关文件路径

- **源码（web）** : `E:\Projects\ai00\workmanship-web\packages\craft-plugin\web\lineage_view\lifecycle_panel.js`
- **源码（web）** : `E:\Projects\ai00\workmanship-web\packages\craft-plugin\web\lineage_view\index.html`
- **部署（backend 的 dist）**: `E:\Projects\ai00\workmanship-backend\dist\packages\craft-plugin\web\lineage_view\lifecycle_panel.js`
- **部署（backend 的 dist）**: `E:\Projects\ai00\workmanship-backend\dist\packages\craft-plugin\web\lineage_view\index.html`
- **后端版本创建/升版**: `E:\Projects\ai00\workmanship-backend\packages\craft-plugin\backend\bop\versions.py`
- **后端生命周期**: `E:\Projects\ai00\workmanship-backend\packages\craft-plugin\backend\bop\lifecycle.py`
- **前端入口/新建版本弹窗**: `E:\Projects\ai00\workmanship-web\packages\craft-plugin\web\lineage_view\lineage_version_mgr.js`

## 可以继续做的方向

1. **验证测试**：部署后实际点开新建版本弹窗，确认：
   - 版本族区域不再显示可下拉的选择框，而是文字提示
   - 选项目后自动显示"加入已有版本族"或"将成为新版本族"
   - 数据阶段下拉中同族已用过的阶段正确禁用
   - 创建新版本成功后，版本族归属正确
2. **后端部署**：SSH 到服务器重启/重载 backend 服务使修改生效
3. **升版流程**：`lifecycle_panel.js` 中 "升版" Tab 允许选目标阶段（或仅升版本号），老版本做快照，活动版本不变，需要端到端验证
4. **生命周期页签**：当前为 `['init','promote','snapshots','archived']`，如果有其他调整需求
5. **完善/发布功能**：之前注释掉了 `refine` 和 `publish_cycle`，已合并到 promote 中，如需恢复可调整
6. **`bop_name` 净化**: 后端 `create_version` 有 regex 兜底净化，确保库中脏数据也能正常展示
