from __future__ import annotations
import json, re
from pathlib import Path
import yaml
from .base import NormalizedCandidate

def parse_md(path, source_type, source_id=None):
    p=Path(path); out=[]; source_id=source_id or str(path)
    for n,line in enumerate(p.read_text().splitlines(),1):
        m=re.match(r'\s*- \[( |x|X)\]\s*(.*)', line)
        if not m: continue
        done=m.group(1).lower()=='x'; text=m.group(2)
        def tok(name):
            mm=re.search(rf'\b{name}:([^\s]+)', text); return mm.group(1) if mm else None
        labels=tuple(x[1:] for x in re.findall(r'#[\w-]+', text))
        url=(re.search(r'https?://\S+', text) or [None]).group(0) if re.search(r'https?://\S+', text) else None
        clean=re.sub(r'\b(due|concern|blocked_by|id):[^\s]+','',text); clean=re.sub(r'#[\w-]+','',clean); clean=re.sub(r'https?://\S+','',clean).strip()
        ext=tok('id') or str(n); blocked=tuple(tok('blocked_by').split(',')) if tok('blocked_by') else ()
        out.append(NormalizedCandidate(source_type,source_id,ext,f'{source_type}:{source_id}:{ext}',clean,url=url,status='done' if done else ('blocked' if blocked else 'candidate'),concern_hint=tok('concern'),due_at=tok('due'),blocked_by=blocked,labels=labels))
    return out

def parse_github(path, source_id='repo'):
    data=json.loads(Path(path).read_text()); out=[]
    for x in data:
        num=x.get('number') or x.get('id')
        if num is None: continue
        num=str(num); repo=x.get('repo') or source_id
        labels=tuple(l['name'] if isinstance(l,dict) else l for l in x.get('labels',[]))
        out.append(NormalizedCandidate('github',repo,num,f'github:{repo}:{num}',x.get('title','untitled'),url=x.get('url') or x.get('html_url'),status='done' if x.get('state')=='closed' else 'candidate',concern_hint=x.get('concern_hint') or x.get('concern'),labels=labels,participants=tuple(x.get('assignees',[])),due_at=(x.get('milestone') or {}).get('due_on') if isinstance(x.get('milestone'),dict) else None,raw={'number':num}))
    return out

def parse_jsonl(path, source_id='inbox-calendar-jsonl'):
    out=[]
    for line in Path(path).read_text().splitlines():
        if not line.strip(): continue
        x=json.loads(line); raw={k:v for k,v in x.items() if k not in ('body','full_body','html','attachments_text')}
        if x.get('id') is None: continue
        kind=x.get('kind','email'); ext=str(x.get('id')); title=x.get('title') or x.get('subject') or 'untitled'
        parts=tuple(y for y in [x.get('sender'),x.get('organizer')] if y)
        labels=tuple(x.get('labels',[]));
        out.append(NormalizedCandidate('inbox_calendar',source_id,ext,f'inbox_calendar:{source_id}:{kind}:{ext}',title,summary=x.get('snippet'),url=x.get('url'),concern_hint=x.get('concern_hint'),due_at=x.get('due_at'),scheduled_start_at=x.get('scheduled_start_at'),labels=labels,participants=parts,raw=raw))
    return out

def load_config(path): return yaml.safe_load(Path(path).read_text())
