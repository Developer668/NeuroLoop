"""Explicit deterministic commands; this is not an LLM or simulated chat."""
from sqlalchemy import select,func
from .db import Session,Run,Evaluation,now

def command(value: str) -> dict:
    key=value.strip().lower()
    links=[]
    if key=='/status':
        with Session() as db:
            active=db.scalar(select(func.count()).select_from(Run).where(Run.status.in_(['queued','running'])))
            evaluations=db.scalar(select(func.count()).select_from(Evaluation))
        from .execution_guard import execution_status
        held=execution_status()['paused']
        message=f'{active} queued or running jobs. {evaluations} saved cortical evaluations, including retained history. '+('Model execution is paused after a graphics crash. The worker and Launch agent are stopped; saved evidence remains available.' if held else 'Read current hardware telemetry before starting another model run.')
        links=[{'label':'System & connections','href':'/workspace?view=connections'}]
    elif key=='/latest':
        with Session() as db:
            latest=db.scalar(select(Evaluation).order_by(Evaluation.created_at.desc()).limit(1))
            message=f'Latest saved evaluation: {latest.id}. Profile: {latest.profile}. Recorded compute: {latest.duration_seconds:.2f} seconds. These are model predictions, not a measured viewer response.' if latest else 'No completed cortical evaluations yet. Add media and start an analysis.'
            if latest: links=[{'label':'Open this cortical result','href':'/workspace?view=brain&evaluation='+latest.id}]
    elif key=='/experiments':
        with Session() as db:
            counts=dict(db.execute(select(Run.status,func.count()).group_by(Run.status)).all())
        message='Recorded run outcomes: '+(', '.join(f'{count} {status}' for status,count in sorted(counts.items())) or 'none yet')+'. Includes retained history; completion does not establish scientific accuracy.'
        links=[{'label':'Inspect experiment history','href':'/workspace?view=runs'}]
    elif key=='/connections':
        from .delivery import receipts
        rows=receipts()
        message=f'In the latest {len(rows)} export receipts, {sum(r["status"]=="delivered" for r in rows)} were verified remotely. W&B Inference and TypeSafe remain deferred. The service check can test current connectivity.'
        links=[{'label':'Open connections','href':'/workspace?view=connections'}]
    else:
        message='Available local commands: /status, /latest, /experiments, /connections and /help. Free-form AI conversation is not connected yet. Your draft stays intact; no AI answer has been generated.'
    return {'command':key,'message':message,'links':links,'checked_at':now(),'provider':'local-deterministic-commands'}
