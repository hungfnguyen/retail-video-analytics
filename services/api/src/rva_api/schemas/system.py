from pydantic import BaseModel

from rva_api.schemas.live import ServiceHealth


class ThroughputPoint(BaseModel):
    time: str
    events: int
    frames: float


class LagPoint(BaseModel):
    time: str
    backlog: int
    lag: int
    api: int


class ContainerStatus(BaseModel):
    name: str
    status: str
    cpu: str
    memory: str
    uptime: str


class SystemLogEntry(BaseModel):
    time: str
    level: str
    service: str
    message: str


class PipelineFlowStep(BaseModel):
    name: str
    status: str


class SystemDashboardData(BaseModel):
    generated_at: str
    pipeline_health: list[ServiceHealth]
    throughput: list[ThroughputPoint]
    lag: list[LagPoint]
    containers: list[ContainerStatus]
    logs: list[SystemLogEntry]
    flow: list[PipelineFlowStep]
