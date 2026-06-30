from __future__ import annotations
import os
from fastapi import FastAPI, Body, HTTPException
from fastapi.responses import HTMLResponse
from .store import Store, init_db
from .board import BoardService
from .cli import run_scan
from .errors import StorageError

DEFAULT_DB=os.environ.get('PLATE_SPINNER_DB', os.path.expanduser('~/.hermes/plate-spinner.sqlite'))
DEFAULT_CONFIG=os.environ.get('PLATE_SPINNER_CONFIG', os.path.expanduser('~/.hermes/plate-spinner.yaml'))

def create_app(store: Store|None=None, service: BoardService|None=None, config_path: str|None=None):
    store=store or Store(DEFAULT_DB); init_db(store.path); service=service or BoardService(store)
    config_path=config_path or DEFAULT_CONFIG
    app=FastAPI(title='Plate Spinner')
    @app.get('/', response_class=HTMLResponse)
    def index(): return HTML
    @app.get('/api/board')
    def board(): return service.get_snapshot().to_dict()
    @app.get('/api/attention')
    def attention(): return service.get_snapshot().attention
    @app.get('/api/columns/{id}')
    def column(id: str): return service.focus(id).to_dict()
    @app.post('/api/scan')
    def scan(source: str|None=None):
        try: summary=run_scan(service, config_path, only_source=source)
        except FileNotFoundError: raise HTTPException(503, f'scan config not found: {config_path}')
        return {'success': True, 'source': source, 'summary': summary}
    @app.post('/api/items/{id}/snooze')
    def snooze(id: str, payload: dict = Body(default={})):
        try: return service.snooze_item(id, payload.get('until')).to_dict()
        except ValueError as e: raise HTTPException(422, str(e))
    @app.post('/api/items/{id}/unsnooze')
    def unsnooze(id: str, payload: dict = Body(default={})): return service.unsnooze_item(id).to_dict()
    @app.post('/api/items/{id}/dismiss')
    def dismiss(id: str, payload: dict = Body(default={})): return service.dismiss_item(id).to_dict()
    @app.post('/api/items/{id}/pin')
    def pin(id: str, payload: dict = Body(default={})): return service.pin_item(id, payload.get('rank',0)).to_dict()
    @app.post('/api/items/{id}/assign')
    def assign(id: str, payload: dict = Body(default={})):
        if 'concern_id' not in payload: raise HTTPException(422, 'concern_id required')
        return service.assign_item(id, payload['concern_id']).to_dict()
    @app.post('/api/columns')
    def create_column(payload: dict):
        if 'name' not in payload: raise HTTPException(422, 'name required')
        try: return service.create_column(payload['name'], id=payload.get('id'), kind=payload.get('kind'), description=payload.get('description'), aliases=tuple(payload.get('aliases',())), filters=payload.get('filters',{})).to_dict()
        except StorageError as e: raise HTTPException(409, str(e))
    @app.patch('/api/columns/{id}')
    def patch_column(id: str, payload: dict):
        if 'name' in payload: store.update_concern(id, name=payload['name'])
        rest={k:v for k,v in payload.items() if k!='name'}
        if rest: store.update_concern(id, **rest)
        return store.get_concern(id).to_dict()
    @app.post('/api/columns/reorder')
    def reorder(payload: dict): return [c.to_dict() for c in service.reorder_columns(payload.get('column_ids',[]))]
    @app.post('/api/columns/{id}/archive')
    def archive(id: str): return service.archive_column(id).to_dict()
    return app

HTML='''<!doctype html><html><head><title>Plate Spinner</title><style>body{font-family:sans-serif;margin:2rem;background:#101418;color:#eee}.panel,.col{border:1px solid #444;border-radius:8px;padding:1rem;margin:.5rem;background:#182028}.board{display:flex;gap:1rem}.why{color:#9cf}</style></head><body><h1>Plate Spinner</h1><section class="panel"><h2>Attention</h2><div id="attention">Loading...</div></section><section class="board" id="board"></section><p id="updated"></p><script>
function esc(s){return String(s==null?'':s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
async function act(url, body={}){await fetch(url,{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(body)}); load()}
async function load(){let b=await (await fetch('/api/board')).json(); let a=b.attention; attention.innerHTML=`<b>Unmapped:</b> ${a.unmapped_candidates.length} <b>Blocked:</b> ${a.blocked_items.length} <b>Connectors:</b> ${a.connector_health.length} <b>Empty:</b> ${esc(a.empty_active_columns.join(', '))}`; board.innerHTML=b.columns.map(c=>`<div class=col><h3>${esc(c.column.name)}</h3>${c.next_item?`<h4>${esc(c.next_item.title)}</h4><div class=why>${(c.next_explanation?.reasons||[]).map(esc).join('<br>')}</div><button onclick="act('/api/items/${c.next_item.id}/snooze',{until:new Date(Date.now()+86400000).toISOString()})">snooze</button><button onclick="act('/api/items/${c.next_item.id}/dismiss')">dismiss</button><button onclick="act('/api/items/${c.next_item.id}/pin',{rank:0})">pin</button>`:'<em>No eligible next item</em>'}<details><summary>Queue (${c.queue.length})</summary>${c.queue.map(i=>`<div>${esc(i.title)}<button onclick="act('/api/items/${i.id}/assign',{concern_id:'${c.column.id}'})">assign here</button></div>`).join('')}</details>${(c.snoozed&&c.snoozed.length)?`<details><summary>Snoozed (${c.snoozed.length})</summary>${c.snoozed.map(i=>`<div>${esc(i.title)} <small>until ${esc(i.snoozed_until)}</small><button onclick="act('/api/items/${i.id}/unsnooze')">unsnooze</button></div>`).join('')}</details>`:''}</div>`).join(''); updated.textContent='Last updated '+new Date().toLocaleTimeString()}
load(); setInterval(load,5000)
</script></body></html>'''
app=create_app()
