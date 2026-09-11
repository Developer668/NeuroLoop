"""Context-scoped Thompson sampling. Statistics adapt; neural weights stay frozen."""
from __future__ import annotations
import random
from sqlalchemy import select
from .db import Session, PolicyStat, now

OPERATORS={
    'contrast_up':('Increase contrast by 8%','A modest contrast increase may move the cortical pattern closer to the references.'),
    'contrast_down':('Reduce contrast by 8%','A modest contrast reduction may move the cortical pattern closer to the references.'),
    'brightness_up':('Increase brightness by 0.035','Test a small luminance change while preserving timing and assets.'),
    'brightness_down':('Reduce brightness by 0.035','Test a small luminance change while preserving timing and assets.'),
    'saturation_up':('Increase saturation by 12%','Test a bounded color-intensity change; this is not a claim about emotion.'),
    'saturation_down':('Reduce saturation by 12%','Test a bounded color-intensity change; this is not a claim about emotion.'),
    'headline_early':('Move headline 0.75 seconds earlier','Test headline timing while preserving the exact copy and source image.'),
    'headline_late':('Move headline 0.75 seconds later','Test headline timing while preserving the exact copy and source image.')}

def choose(context: str,allowed: list[str],excluded: set[str],seed: str) -> dict | None:
    candidates=[x for x in allowed if x in OPERATORS and x not in excluded]
    if not candidates: return None
    rng=random.Random(seed)
    choices=[]
    with Session() as db:
        for name in candidates:
            row=db.get(PolicyStat,f'{context}:{name}')
            good=row.successes if row else 0; bad=row.failures if row else 0
            sampled=rng.betavariate(1+good,1+bad)
            # Rank useful-edit probability per relative observed cost, not a human-preference probability.
            mean_cost=(row.total_seconds/(good+bad)) if row and good+bad else 30.0
            utility=sampled/max(mean_cost,1.0)
            choices.append({'operator':name,'sampled_useful_edit_rate':sampled,'selection_utility':utility,'attempts':good+bad,'successes':good,'failures':bad})
    selected=max(choices,key=lambda x:x['selection_utility'])
    return {**selected,'hypothesis':OPERATORS[selected['operator']][1],'label':OPERATORS[selected['operator']][0],'source':'context-scoped cost-aware Thompson sampling','candidates':choices}

def record_in_session(db, context: str,operator: str,gain: float,seconds: float,threshold: float) -> None:
    key=f'{context}:{operator}'; row=db.get(PolicyStat,key)
    if row is None:
        row=PolicyStat(key=key,context=context,operator=operator,successes=0,failures=0,total_gain=0,total_seconds=0);db.add(row)
    row.successes+=int(gain>=threshold);row.failures+=int(gain<threshold)
    row.total_gain+=gain;row.total_seconds+=seconds;row.updated_at=now()

def record(context: str,operator: str,gain: float,seconds: float,threshold: float) -> None:
    with Session.begin() as db:
        record_in_session(db,context,operator,gain,seconds,threshold)

def history() -> list[dict]:
    with Session() as db:
        rows=db.scalars(select(PolicyStat).order_by(PolicyStat.updated_at.desc())).all()
        return [{'context':x.context,'operator':x.operator,'successes':x.successes,'failures':x.failures,'attempts':x.successes+x.failures,'mean_gain':x.total_gain/max(1,x.successes+x.failures),'mean_seconds':x.total_seconds/max(1,x.successes+x.failures),'updated_at':x.updated_at} for x in rows]
