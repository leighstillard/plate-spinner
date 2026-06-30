from __future__ import annotations
import json, sqlite3, hashlib
from pathlib import Path
from .models import ConcernColumn, SourceRef, WorkItem, utc_now
from .connectors.base import NormalizedCandidate, DEFAULT_PRECEDENCE
from .errors import StorageError

def init_db(path: str):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    con=sqlite3.connect(path)
    con.executescript("""
    PRAGMA user_version=1;
    CREATE TABLE IF NOT EXISTS concerns(id TEXT PRIMARY KEY,name TEXT NOT NULL,kind TEXT,description TEXT,position INTEGER NOT NULL,status TEXT NOT NULL,aliases_json TEXT NOT NULL DEFAULT '[]',manual_filter_json TEXT NOT NULL DEFAULT '{}',created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS work_items(id TEXT PRIMARY KEY,concern_id TEXT,title TEXT NOT NULL,summary TEXT,status TEXT NOT NULL,primary_source_type TEXT NOT NULL,primary_source_id TEXT NOT NULL,primary_external_id TEXT NOT NULL,primary_url TEXT,dedupe_key TEXT NOT NULL UNIQUE,source_precedence INTEGER NOT NULL,urgency INTEGER NOT NULL,due_at TEXT,scheduled_start_at TEXT,blocked_by_json TEXT NOT NULL DEFAULT '[]',labels_json TEXT NOT NULL DEFAULT '[]',participants_json TEXT NOT NULL DEFAULT '[]',manual_rank INTEGER,snoozed_until TEXT,raw_json TEXT NOT NULL DEFAULT '{}',created_at TEXT NOT NULL,updated_at TEXT NOT NULL,completed_at TEXT);
    CREATE TABLE IF NOT EXISTS work_item_refs(item_id TEXT NOT NULL,source_type TEXT NOT NULL,source_id TEXT NOT NULL,external_id TEXT NOT NULL,url TEXT,dedupe_key TEXT NOT NULL,last_seen_at TEXT NOT NULL,is_primary INTEGER NOT NULL DEFAULT 0,PRIMARY KEY(item_id,source_type,source_id,external_id));
    CREATE TABLE IF NOT EXISTS scan_cursors(source_type TEXT NOT NULL,source_id TEXT NOT NULL,cursor TEXT,last_status TEXT NOT NULL DEFAULT 'never_run',last_error TEXT,last_summary_json TEXT NOT NULL DEFAULT '{}',last_scanned_at TEXT,PRIMARY KEY(source_type,source_id));
    """); con.commit(); con.close()

def _id(prefix,s): return prefix+'_'+hashlib.sha1(s.encode()).hexdigest()[:12]
def _json(x): return json.dumps(x, sort_keys=True)
def _loads(s, default):
    if not s: return default
    return json.loads(s)

class Store:
    def __init__(self,path: str): self.path=path
    def con(self):
        init_db(self.path); c=sqlite3.connect(self.path); c.row_factory=sqlite3.Row; return c
    def create_concern(self, name, id=None, kind=None, description=None, aliases=(), manual_filter=None, position=None):
        now=utc_now(); manual_filter=manual_filter or {}; id=id or name.lower().replace(' ','-')
        with self.con() as c:
            if c.execute('select 1 from concerns where id=?',(id,)).fetchone():
                raise StorageError(f'concern already exists: {id}')
            if position is None:
                r=c.execute('select coalesce(max(position),-1)+1 p from concerns').fetchone(); position=r['p']
            c.execute('insert into concerns values(?,?,?,?,?,?,?,?,?,?)',(id,name,kind,description,position,'active',_json(list(aliases)),_json(manual_filter),now,now))
        return self.get_concern(id)
    def get_concern(self,id):
        with self.con() as c: r=c.execute('select * from concerns where id=?',(id,)).fetchone()
        if not r: raise KeyError(id)
        return ConcernColumn(id=r['id'],name=r['name'],kind=r['kind'],description=r['description'],position=r['position'],status=r['status'],aliases=tuple(_loads(r['aliases_json'],[])),manual_filter=_loads(r['manual_filter_json'],{}),created_at=r['created_at'],updated_at=r['updated_at'])
    def list_concerns(self, include_archived=False):
        q='select * from concerns '+('' if include_archived else "where status='active'")+' order by position,id'
        with self.con() as c: rows=c.execute(q).fetchall()
        return [self.get_concern(r['id']) for r in rows]
    def update_concern(self,id, **kw):
        cur=self.get_concern(id); data=cur.to_dict(); data.update({k:v for k,v in kw.items() if v is not None}); data['updated_at']=utc_now()
        with self.con() as c: c.execute('update concerns set name=?,kind=?,description=?,position=?,status=?,aliases_json=?,manual_filter_json=?,updated_at=? where id=?',(data['name'],data.get('kind'),data.get('description'),data['position'],data['status'],_json(list(data.get('aliases') or [])),_json(data.get('manual_filter') or {}),data['updated_at'],id))
        return self.get_concern(id)
    def archive_concern(self,id): return self.update_concern(id,status='archived')
    def row_to_item(self,r):
        ref=SourceRef(r['primary_source_type'],r['primary_source_id'],r['primary_external_id'],r['primary_url'],r['dedupe_key'],r['updated_at'],True)
        return WorkItem(id=r['id'],title=r['title'],summary=r['summary'],status=r['status'],concern_id=r['concern_id'],primary_ref=ref,source_precedence=r['source_precedence'],urgency=r['urgency'],due_at=r['due_at'],scheduled_start_at=r['scheduled_start_at'],blocked_by=tuple(_loads(r['blocked_by_json'],[])),labels=tuple(_loads(r['labels_json'],[])),participants=tuple(_loads(r['participants_json'],[])),manual_rank=r['manual_rank'],snoozed_until=r['snoozed_until'],created_at=r['created_at'],updated_at=r['updated_at'],completed_at=r['completed_at'],raw=_loads(r['raw_json'],{}))
    def upsert_candidate(self,cand: NormalizedCandidate, concern_id: str|None, now: str):
        item_id=_id('wi', cand.dedupe_key); prec=cand.source_precedence if cand.source_precedence is not None else DEFAULT_PRECEDENCE.get(cand.source_type,50)
        with self.con() as con:
            old=con.execute('select * from work_items where dedupe_key=?',(cand.dedupe_key,)).fetchone()
            if old:
                item_id=old['id']; status=old['status'] if old['status'] in ('dismissed','done') else cand.status
                con.execute('update work_items set concern_id=coalesce(?,concern_id),title=?,summary=?,status=?,source_precedence=?,urgency=?,due_at=?,scheduled_start_at=?,blocked_by_json=?,labels_json=?,participants_json=?,raw_json=?,updated_at=? where id=?',(concern_id,cand.title,cand.summary,status,prec,cand.urgency,cand.due_at,cand.scheduled_start_at,_json(list(cand.blocked_by)),_json(list(cand.labels)),_json(list(cand.participants)),_json(cand.raw),now,item_id))
            else:
                con.execute('insert into work_items values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(item_id,concern_id,cand.title,cand.summary,cand.status,cand.source_type,cand.source_id,cand.external_id,cand.url,cand.dedupe_key,prec,cand.urgency,cand.due_at,cand.scheduled_start_at,_json(list(cand.blocked_by)),_json(list(cand.labels)),_json(list(cand.participants)),None,None,_json(cand.raw),now,now,None))
            con.execute('insert or replace into work_item_refs values(?,?,?,?,?,?,?,?)',(item_id,cand.source_type,cand.source_id,cand.external_id,cand.url,cand.dedupe_key,now,1))
        return self.get_item(item_id)
    def get_item(self,id):
        with self.con() as c: r=c.execute('select * from work_items where id=?',(id,)).fetchone()
        if not r: raise KeyError(id)
        return self.row_to_item(r)
    def list_items(self, concern_id=None, include_done=True):
        q='select * from work_items'; args=[]; clauses=[]
        if concern_id is not None: clauses.append('concern_id=?'); args.append(concern_id)
        if not include_done: clauses.append("status not in ('done','dismissed')")
        if clauses: q += ' where '+ ' and '.join(clauses)
        q+=' order by title,id'
        with self.con() as c: rows=c.execute(q,args).fetchall()
        return [self.row_to_item(r) for r in rows]
    def update_item(self,id, **kw):
        cur=self.get_item(id); data=cur.to_dict(); data.update(kw); data['updated_at']=utc_now()
        with self.con() as c:
            c.execute('update work_items set concern_id=?,title=?,summary=?,status=?,source_precedence=?,urgency=?,due_at=?,scheduled_start_at=?,blocked_by_json=?,labels_json=?,participants_json=?,manual_rank=?,snoozed_until=?,raw_json=?,updated_at=?,completed_at=? where id=?',(data['concern_id'],data['title'],data['summary'],data['status'],data['source_precedence'],data['urgency'],data['due_at'],data['scheduled_start_at'],_json(list(data['blocked_by'])),_json(list(data['labels'])),_json(list(data['participants'])),data['manual_rank'],data['snoozed_until'],_json(data['raw']),data['updated_at'],data['completed_at'],id))
        return self.get_item(id)
    def record_scan_health(self,source_type,source_id,cursor,last_status,last_error,last_summary_json,last_scanned_at):
        with self.con() as c: c.execute('insert or replace into scan_cursors values(?,?,?,?,?,?,?)',(source_type,source_id,cursor,last_status,last_error,_json(last_summary_json),last_scanned_at))
    def list_scan_health(self):
        with self.con() as c: rows=c.execute('select * from scan_cursors order by source_type,source_id').fetchall()
        return [dict(r)|{'last_summary_json':_loads(r['last_summary_json'],{})} for r in rows]
