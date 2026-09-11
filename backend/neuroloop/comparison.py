"""Shared comparison service for browser and MCP. No mixed-profile measurements."""
from pathlib import Path
from sqlalchemy import select
import numpy as np
from .db import Session,Evaluation
from .readout import similarity,validate_response,METRIC

def compare_evaluations(ids:list[str]) -> dict:
    if not 2<=len(ids)<=12 or len(set(ids))!=len(ids):
        raise ValueError('Choose between 2 and 12 unique evaluations')
    with Session() as db:
        records=[db.get(Evaluation,identity) for identity in ids]
    if any(record is None for record in records):
        raise ValueError('A selected evaluation does not exist')
    if len({record.profile for record in records})!=1:
        raise ValueError('Different model profiles cannot be compared')
    if any(not record.prediction_path or not Path(record.prediction_path).is_file() for record in records):
        raise ValueError('A selected cortical result file is unavailable')
    arrays=[np.load(record.prediction_path,mmap_mode='r',allow_pickle=False) for record in records]
    for array in arrays:validate_response(array)
    matrix=[[similarity(a,b) for b in arrays] for a in arrays]
    return {'evaluation_ids':ids,'profile':records[0].profile,'metric':METRIC,'matrix':matrix,'meaning':'Predicted cortical-pattern similarity under a fixed representation. Not measured human preference, emotion or purchasing behavior.'}
