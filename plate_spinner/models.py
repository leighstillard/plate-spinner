
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()

def _tuple(v):
    if v is None: return ()
    return tuple(v)

@dataclass(frozen=True)
class ConcernColumn:
    id: str
    name: str
    kind: str | None = None
    description: str | None = None
    position: int = 0
    status: str = 'active'
    aliases: tuple[str,...] = ()
    manual_filter: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    def to_dict(self): return asdict(self)
    @classmethod
    def from_dict(cls,d):
        d=dict(d); d['aliases']=_tuple(d.get('aliases')); return cls(**d)

@dataclass(frozen=True)
class SourceRef:
    source_type: str
    source_id: str
    external_id: str
    url: str | None = None
    dedupe_key: str = ''
    last_seen_at: str = field(default_factory=utc_now)
    is_primary: bool = True
    def to_dict(self): return asdict(self)
    @classmethod
    def from_dict(cls,d): return cls(**dict(d))

@dataclass(frozen=True)
class WorkItem:
    id: str
    title: str
    summary: str | None = None
    status: str = 'candidate'
    concern_id: str | None = None
    primary_ref: SourceRef | dict = None
    secondary_refs: tuple[SourceRef,...] = ()
    source_precedence: int = 50
    urgency: int = 0
    due_at: str | None = None
    scheduled_start_at: str | None = None
    blocked_by: tuple[str,...] = ()
    labels: tuple[str,...] = ()
    participants: tuple[str,...] = ()
    manual_rank: int | None = None
    snoozed_until: str | None = None
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    completed_at: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)
    def __post_init__(self):
        if isinstance(self.primary_ref, dict): object.__setattr__(self,'primary_ref',SourceRef.from_dict(self.primary_ref))
        object.__setattr__(self,'secondary_refs',tuple(SourceRef.from_dict(x) if isinstance(x,dict) else x for x in self.secondary_refs))
        object.__setattr__(self,'blocked_by',_tuple(self.blocked_by)); object.__setattr__(self,'labels',_tuple(self.labels)); object.__setattr__(self,'participants',_tuple(self.participants))
    def to_dict(self):
        d=asdict(self); return d
    @classmethod
    def from_dict(cls,d): return cls(**dict(d))

@dataclass(frozen=True)
class SelectionExplanation:
    item_id: str
    eligible: bool
    score_tuple: tuple = ()
    reasons: tuple[str,...] = ()
    blocked_or_skipped_reason: str | None = None
    def to_dict(self): return asdict(self)

@dataclass(frozen=True)
class ColumnSnapshot:
    column: ConcernColumn
    next_item: WorkItem | None = None
    next_explanation: SelectionExplanation | None = None
    queue: tuple[WorkItem,...] = ()
    blocked_count: int = 0
    waiting_count: int = 0
    new_candidate_count: int = 0
    def to_dict(self):
        return {'column':self.column.to_dict(),'next_item':self.next_item.to_dict() if self.next_item else None,'next_explanation':self.next_explanation.to_dict() if self.next_explanation else None,'queue':[i.to_dict() for i in self.queue],'blocked_count':self.blocked_count,'waiting_count':self.waiting_count,'new_candidate_count':self.new_candidate_count}

@dataclass(frozen=True)
class BoardSnapshot:
    columns: tuple[ColumnSnapshot,...]
    attention: dict[str, Any]
    generated_at: str
    def to_dict(self): return {'columns':[c.to_dict() for c in self.columns], 'attention':self.attention, 'generated_at':self.generated_at}
