"""Recorded evidence for the product dashboard and its companion notebook."""
from sqlalchemy import select,func
from .db import Session,Run,Evaluation,Experiment,Asset,Project,ArchivedRecord,as_dict
from . import policy

def ledger() -> dict:
    with Session() as db:
        assets={a.id:a.name for a in db.scalars(select(Asset)).all()}
        projects={p.id:p.name for p in db.scalars(select(Project)).all()}
        archived={r.record_id for r in db.scalars(select(ArchivedRecord)).all()}
        runs=[{**as_dict(r),'project_name':projects.get(r.project_id,'Recorded project'),'archived':r.id in archived} for r in db.scalars(select(Run).order_by(Run.created_at.desc()).limit(100)).all()]
        experiments=[as_dict(e) for e in db.scalars(select(Experiment).order_by(Experiment.created_at.desc()).limit(200)).all()]
        evaluations=[{**as_dict(e,('prediction_path',)),'asset_name':assets.get(e.asset_id,'Recorded asset'),'archived':e.id in archived} for e in db.scalars(select(Evaluation).order_by(Evaluation.created_at.desc()).limit(100)).all()]
        totals={key:db.scalar(select(func.count()).select_from(model)) for key,model in [('runs',Run),('experiments',Experiment),('evaluations',Evaluation)]}
    return {'runs':runs,'experiments':experiments,'evaluations':evaluations,'statistics':policy.history(),'totals':totals,'coverage':'Latest 100 runs, 100 evaluations and 200 interventions, including archived verification history. No model calls are made.'}
