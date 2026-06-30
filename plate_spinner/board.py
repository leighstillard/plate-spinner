from __future__ import annotations
from datetime import datetime, timezone
from .models import ColumnSnapshot, BoardSnapshot
from .prioritization import select_next_item
from .store import Store

def parse_dt(s):
    if not s: return None
    return datetime.fromisoformat(s.replace('Z','+00:00'))

class BoardService:
    def __init__(self, store: Store, now=None, stale_after_seconds: int = 7200):
        self.store=store; self._now=now; self.stale_after_seconds=stale_after_seconds
    def now_dt(self): return self._now() if self._now else datetime.now(timezone.utc)
    def now(self): return self.now_dt().isoformat()
    def create_column(self,name,id=None,kind=None,description=None,aliases=(),filters=None): return self.store.create_concern(name,id=id,kind=kind,description=description,aliases=aliases,manual_filter=filters or {})
    def rename_column(self,id,name): return self.store.update_concern(id,name=name)
    def reorder_columns(self,ids):
        out=[]; pos=0
        for id in ids: out.append(self.store.update_concern(id,position=pos)); pos+=1
        # renumber any columns omitted from the request so positions stay unique
        for c in self.store.list_concerns(include_archived=True):
            if c.id not in ids: self.store.update_concern(c.id,position=pos); pos+=1
        return out
    def archive_column(self,id): return self.store.archive_concern(id)
    def map_candidate(self,cand):
        if cand.concern_hint:
            h=cand.concern_hint.lower()
            for c in self.store.list_concerns():
                vals=[c.id.lower(), c.name.lower()] + [a.lower() for a in c.aliases]
                if c.kind: vals.append(c.kind.lower())
                if h in vals: return c.id
        return None
    def upsert_candidate(self,cand,now=None): return self.store.upsert_candidate(cand,self.map_candidate(cand),now or self.now())
    def assign_item(self,item_id, concern_id): return self.store.update_item(item_id, concern_id=concern_id)
    def pin_item(self,item_id, rank=0): return self.store.update_item(item_id, manual_rank=rank)
    def snooze_item(self,item_id, until):
        if not until: raise ValueError('snooze requires an "until" timestamp')
        try: parse_dt(until)
        except ValueError: raise ValueError(f'invalid snooze timestamp: {until!r}')
        return self.store.update_item(item_id, snoozed_until=until)
    def dismiss_item(self,item_id): return self.store.update_item(item_id, status='dismissed')
    def mark_done(self,item_id): return self.store.update_item(item_id, status='done', completed_at=self.now())
    def focus(self, column_id):
        for c in self.get_snapshot().columns:
            if c.column.id==column_id or c.column.name==column_id: return c
        raise KeyError(column_id)
    def get_snapshot(self, include_archived=False, queue_limit=10):
        nowdt=self.now_dt(); cols=[]
        for col in self.store.list_concerns(include_archived):
            items=self.store.list_items(col.id, include_done=False)
            nxt, exps=select_next_item(items, nowdt)
            expmap={e.item_id:e for e in exps}
            queue=[i for i in items if i.id != (nxt.id if nxt else None)][:queue_limit]
            cols.append(ColumnSnapshot(col,nxt,expmap.get(nxt.id) if nxt else None,tuple(queue),sum(i.status=='blocked' for i in items),sum(i.status=='waiting' for i in items),sum(i.status=='candidate' for i in items)))
        items=self.store.list_items(include_done=False)
        unmapped=[i.to_dict() for i in items if i.concern_id is None and i.status not in ('dismissed','done')]
        blocked=[{'item':i.to_dict(),'blocked_by':list(i.blocked_by),'blocker_status':[self._status_or_external(x) for x in i.blocked_by]} for i in items if i.status=='blocked' or i.blocked_by]
        health=[]
        for h in self.store.list_scan_health():
            last=h.get('last_scanned_at'); stale=True
            if last:
                stale=(nowdt-parse_dt(last)).total_seconds()>self.stale_after_seconds
            health.append({'source_type':h['source_type'],'source_id':h['source_id'],'last_status':h['last_status'],'last_error':h['last_error'],'last_scanned_at':last,'last_summary_json':h['last_summary_json'],'stale':stale})
        empty=[c.column.id for c in cols if c.column.status=='active' and c.next_item is None]
        return BoardSnapshot(tuple(cols),{'unmapped_candidates':unmapped,'blocked_items':blocked,'connector_health':health,'empty_active_columns':empty},self.now())
    def _status_or_external(self,id):
        try: return self.store.get_item(id).status
        except Exception: return 'external_or_missing'
