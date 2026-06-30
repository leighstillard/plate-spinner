
from dataclasses import dataclass, field
from typing import Any, Protocol

DEFAULT_PRECEDENCE={'manual':0,'project_plan':10,'github':20,'todo':30,'inbox_calendar':40,'generic':50}
@dataclass(frozen=True)
class ConnectorContext:
    now: str
    since: str|None=None
    cursor: str|None=None
    config: dict[str,Any]=field(default_factory=dict)
    dry_run: bool=False
@dataclass(frozen=True)
class NormalizedCandidate:
    source_type: str
    source_id: str
    external_id: str
    dedupe_key: str
    title: str
    summary: str|None=None
    url: str|None=None
    status: str='candidate'
    concern_hint: str|None=None
    source_precedence: int|None=None
    urgency: int=0
    due_at: str|None=None
    scheduled_start_at: str|None=None
    blocked_by: tuple[str,...]=()
    labels: tuple[str,...]=()
    participants: tuple[str,...]=()
    raw: dict[str,Any]=field(default_factory=dict)
    def __post_init__(self):
        for f in ('source_type','source_id','external_id','dedupe_key','title'):
            if not getattr(self,f): raise ValueError(f'{f} required')
@dataclass(frozen=True)
class ScanResult:
    candidates: tuple[NormalizedCandidate,...]
    cursor: str|None=None
    warnings: tuple[str,...]=()
class SourceConnector(Protocol):
    name: str; source_type: str; source_id: str
    def scan(self, context: ConnectorContext) -> ScanResult: ...
