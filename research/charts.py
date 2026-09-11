"""Figures use persisted numerical records only."""
import plotly.graph_objects as go
TEAL='#147a82'
NAVY='#172e3d'
def styled(fig,title,x='',y=''):
    fig.update_layout(template='plotly_white',title=title,height=390,font=dict(family='Segoe UI, sans-serif',color=NAVY),colorway=[TEAL,NAVY,'#80afb1','#998867'],margin=dict(l=55,r=25,t=65,b=65),xaxis_title=x,yaxis_title=y,hovermode='closest')
    return fig

def experiment_figures(runs,experiments,stats):
    figures={}; e=experiments.copy()
    if not e.empty:
        e['gain']=e.candidate_score-e.baseline_score
        valid=e.dropna(subset=['baseline_score','candidate_score'])
        gain=go.Figure()
        for decision,rows in valid.groupby('decision'):
            gain.add_trace(go.Scatter(x=rows.baseline_score,y=rows.candidate_score,mode='markers',name=str(decision),text=rows.operator,customdata=rows.run_id,marker=dict(size=10),hovertemplate='%{text}<br>Baseline %{x:.4f}<br>Candidate %{y:.4f}<br>Run %{customdata}<extra>%{fullData.name}</extra>'))
        gain.add_shape(type='line',x0=-1,x1=1,y0=-1,y1=1,line=dict(color='#a8b6bc',dash='dot'))
        figures['Measured change']=styled(gain,'Did the candidate beat its baseline?','Baseline similarity','Candidate similarity')
        outcome=go.Figure()
        for decision,rows in e.groupby('decision'):
            counts=rows.groupby('operator').size(); outcome.add_trace(go.Bar(x=counts.index,y=counts.values,name=str(decision)))
        outcome.update_layout(barmode='stack')
        figures['Operator outcomes']=styled(outcome,'Every recorded decision, including reverts','Operator','Experiments')
        trajectory=go.Figure()
        for identity,rows in valid.groupby('run_id'):
            rows=rows.sort_values('sequence')
            trajectory.add_trace(go.Scatter(x=rows.sequence,y=rows.candidate_score,mode='lines+markers',name=str(identity)[:8],text=rows.decision))
        figures['Search trajectory']=styled(trajectory,'Candidate scores within each fixed run','Experiment sequence','Reference similarity')
        if not valid.empty:
            joined=valid.merge(runs[['id','compute_seconds','evaluations_used']],left_on='run_id',right_on='id',how='left')
            extent=max(float(joined.gain.abs().max()),1e-6)
            parallel=go.Figure(go.Parcoords(line=dict(color=joined.gain,colorscale=[[0,'#9a7144'],[.5,'#b6c5c8'],[1,TEAL]],cmin=-extent,cmax=extent,showscale=True,colorbar=dict(title='Gain')),dimensions=[dict(label=label,values=joined[key]) for label,key in [('Baseline','baseline_score'),('Candidate','candidate_score'),('Gain','gain'),('Run seconds','compute_seconds'),('Run evaluations','evaluations_used')]]))
            figures['Parallel coordinates']=styled(parallel,'Brush axes to inspect score and whole-run cost')
            parallel.update_layout(margin=dict(t=110),title=dict(y=.97))
    if not runs.empty:
        cost=go.Figure()
        for status,rows in runs.groupby('status'):
            cost.add_trace(go.Scatter(x=rows.evaluations_used,y=rows.compute_seconds,mode='markers',name=str(status),text=rows.id,marker=dict(size=10,opacity=.75)))
        figures['Compute efficiency']=styled(cost,'Recorded work and compute, including failed runs','Evaluations used','Compute seconds')
        counts=runs.groupby('status').size()
        figures['Run reliability']=styled(go.Figure(go.Bar(x=counts.index,y=counts.values,marker_color=TEAL)),'Run outcomes in this selection','Recorded status','Runs')
    if not stats.empty:
        policy=stats.copy(); policy['attempts']=policy.successes+policy.failures; policy=policy[policy.attempts>0]
        figures['Operator experience']=styled(go.Figure(go.Scatter(x=policy.attempts,y=policy.total_gain/policy.attempts,mode='markers',text=policy.context+' / '+policy.operator,marker=dict(size=12,color=TEAL))),'Context experience; not held-out performance','Observed experiments','Mean measured gain')
    return figures

def cortical_figures(evidence):
    times=evidence.get('times',[]); fig=go.Figure()
    for key,label,color in [('left_mean','Left',TEAL),('right_mean','Right',NAVY)]:
        fig.add_trace(go.Scatter(x=times,y=evidence.get(key,[]),mode='lines+markers',name=label,line=dict(color=color)))
    figures={'Hemisphere timeline':styled(fig,'Actual saved cortical means','Official segment start (s)','Model response units')}
    figures['Hemisphere heatmap']=styled(go.Figure(go.Heatmap(x=times,y=['Left','Right'],z=[evidence.get('left_mean',[]),evidence.get('right_mean',[])],colorscale=[[0,NAVY],[.5,'#f4f7f7'],[1,TEAL]],zmid=0,colorbar=dict(title='Units'))),'When hemispheric means differ','Official segment start (s)','Hemisphere')
    return figures
