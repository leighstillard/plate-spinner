from __future__ import annotations
import argparse, json, sys
from .store import Store, init_db
from .board import BoardService
from .connectors.simple import load_config, parse_md, parse_github, parse_jsonl

def make(db):
    s=Store(db); init_db(db); return s, BoardService(s)

def run_scan(svc, config_path, only_source=None):
    cfg=load_config(config_path); summary={'seen':0,'created':0,'updated':0,'unmapped':0,'errors':0}
    for col in cfg.get('columns',[]):
        if not any(c.id==col['id'] for c in svc.store.list_concerns(include_archived=True)):
            svc.create_column(col['name'], id=col['id'], kind=col.get('kind'), aliases=tuple(col.get('aliases',())), filters=col.get('filters',{}))
    for src in cfg.get('sources',[]):
        if only_source and only_source not in (src.get('type'), src.get('id')): continue
        before=len(svc.store.list_items())
        try:
            typ=src['type']
            if typ in ('project_plan','todo'): cands=parse_md(src['path'], typ, src.get('id'))
            elif typ=='github': cands=parse_github(src['fixture_path'], src.get('repo') or src.get('id','repo'))
            elif typ=='inbox_calendar': cands=parse_jsonl(src['path'], src.get('id','inbox-calendar-jsonl'))
            else: cands=[]
            for c in cands:
                item=svc.upsert_candidate(c); summary['seen']+=1
                if item.concern_id is None: summary['unmapped']+=1
            after=len(svc.store.list_items()); summary['created']+=max(0,after-before); summary['updated']+=max(0,len(cands)-max(0,after-before))
            svc.store.record_scan_health(typ, src.get('id',src.get('path','default')), None, 'ok', None, {'seen':len(cands)}, svc.now())
        except Exception as e:
            summary['errors']+=1; svc.store.record_scan_health(src.get('type','unknown'), src.get('id','unknown'), None, 'error', str(e), {'errors':1}, svc.now())
    return summary

def main(argv=None):
    p=argparse.ArgumentParser(); sub=p.add_subparsers(dest='cmd', required=True)
    pi=sub.add_parser('init'); pi.add_argument('--db', required=True)
    pc=sub.add_parser('column'); pcs=pc.add_subparsers(dest='action', required=True); pa=pcs.add_parser('add'); pa.add_argument('name'); pa.add_argument('--id'); pa.add_argument('--kind'); pa.add_argument('--db', required=True)
    ps=sub.add_parser('scan'); ps.add_argument('--config', required=True); ps.add_argument('--db', required=True)
    pb=sub.add_parser('board'); pb.add_argument('--json', action='store_true'); pb.add_argument('--db', required=True)
    pat=sub.add_parser('attention'); pat.add_argument('--json', action='store_true'); pat.add_argument('--db', required=True)
    pf=sub.add_parser('focus'); pf.add_argument('column'); pf.add_argument('--db', required=True)
    pit=sub.add_parser('item'); pits=pit.add_subparsers(dest='action', required=True); psz=pits.add_parser('snooze'); psz.add_argument('item_id'); psz.add_argument('--until', required=True); psz.add_argument('--db', required=True); pd=pits.add_parser('dismiss'); pd.add_argument('item_id'); pd.add_argument('--db', required=True); pp=pits.add_parser('pin'); pp.add_argument('item_id'); pp.add_argument('--rank', type=int, default=0); pp.add_argument('--db', required=True); pas=pits.add_parser('assign'); pas.add_argument('item_id'); pas.add_argument('concern_id'); pas.add_argument('--db', required=True)
    a=p.parse_args(argv)
    if a.cmd=='init': init_db(a.db); return 0
    s,svc=make(a.db)
    if a.cmd=='column' and a.action=='add': print(json.dumps(svc.create_column(a.name,id=a.id,kind=a.kind).to_dict())); return 0
    if a.cmd=='scan': print(json.dumps(run_scan(svc,a.config), sort_keys=True)); return 0
    if a.cmd=='board': print(json.dumps(svc.get_snapshot().to_dict(), sort_keys=True)); return 0
    if a.cmd=='attention': print(json.dumps(svc.get_snapshot().attention, sort_keys=True)); return 0
    if a.cmd=='focus': print(json.dumps(svc.focus(a.column).to_dict(), sort_keys=True)); return 0
    if a.cmd=='item':
        if a.action=='snooze': print(json.dumps(svc.snooze_item(a.item_id,a.until).to_dict())); return 0
        if a.action=='dismiss': print(json.dumps(svc.dismiss_item(a.item_id).to_dict())); return 0
        if a.action=='pin': print(json.dumps(svc.pin_item(a.item_id,a.rank).to_dict())); return 0
        if a.action=='assign': print(json.dumps(svc.assign_item(a.item_id,a.concern_id).to_dict())); return 0
    return 2
if __name__=='__main__': raise SystemExit(main())
