from datetime import datetime, timedelta
from .models import SelectionExplanation

def parse_dt(s):
    if not s: return None
    dt = datetime.fromisoformat(s.replace('Z','+00:00'))
    if dt.tzinfo is None:
        from datetime import timezone
        dt = dt.replace(tzinfo=timezone.utc)
    return dt

def select_next_item(items, now: datetime):
    exps=[]; eligible=[]
    for i in items:
        reasons=[]; skip=None
        if i.status in ('done','dismissed'): skip='closed'
        elif i.snoozed_until and parse_dt(i.snoozed_until)>now: skip='snoozed until '+i.snoozed_until
        elif i.status=='blocked' and i.blocked_by: skip='blocked by '+', '.join(i.blocked_by)
        elif i.status=='waiting' and i.manual_rank is None and not (i.due_at and parse_dt(i.due_at)<=now+timedelta(days=3)): skip='waiting'
        due=parse_dt(i.due_at); due_bucket=9
        if due:
            if due < now: due_bucket=0; reasons.append('why it won: overdue')
            elif due.date()==now.date(): due_bucket=1; reasons.append('why it won: due today')
            elif due <= now+timedelta(days=3): due_bucket=2; reasons.append('why it won: due soon')
        if i.manual_rank is not None: reasons.append('why it won: manual pin')
        if i.urgency: reasons.append(f'why it won: urgency {i.urgency}')
        if not reasons: reasons.append('why it won: deterministic source precedence and stable tie-break')
        life={'in_progress':0,'ready':1,'candidate':2,'waiting':3,'blocked':8}.get(i.status,5)
        score=(i.manual_rank if i.manual_rank is not None else 999999, life, due_bucket, -i.urgency, i.source_precedence, (i.title or '').lower(), i.id)
        exp=SelectionExplanation(i.id, skip is None, score, tuple(reasons), skip)
        exps.append(exp)
        if skip is None: eligible.append((score,i,exp))
    eligible.sort(key=lambda x:x[0])
    return (eligible[0][1] if eligible else None, [e for _,_,e in eligible]+[e for e in exps if not e.eligible])
