"""
backend/rule_engine/models.py
──────────────────────────────
各 node_type 的 Pydantic 上下文模型（可执行本体）。

用途：
  1. 为规则引擎提供类型化的 context 契约
  2. 文档化各节点类型的字段语义

随 onto_properties 定义扩展，此处保持与数据库最终一致。
"""
from typing import Optional
from pydantic import BaseModel


class OperationContext(BaseModel):
    title: str = ""
    vpps: str = ""
    std_time: Optional[int] = None        # 标准工时（秒）
    torque: Optional[float] = None        # 力矩值（N·m）
    qualification: Optional[str] = None  # 操作员资质等级


class StationContext(BaseModel):
    title: str = ""
    vpps: str = ""
    seq_no: Optional[int] = None
    tools_calibrated: Optional[bool] = None
    headcount: Optional[int] = None


class EquipmentContext(BaseModel):
    title: str = ""
    vpps: str = ""
    model_no: Optional[str] = None
    certification_date: Optional[str] = None
    calibration_interval: Optional[int] = None  # 天


class ToolContext(BaseModel):
    title: str = ""
    vpps: str = ""
    model_no: Optional[str] = None
    calibrated: Optional[bool] = None


# node_type → context class 的映射（供外部按需使用）
CONTEXT_MODELS: dict = {
    "operation":       OperationContext,
    "station_process": StationContext,
    "physical_equipment": EquipmentContext,
    "physical_tool":   ToolContext,
}
