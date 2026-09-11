"""Read-only local research view. This application never launches model inference."""
import marimo
__generated_with='0.24.0'
app=marimo.App(width='full',css_file='theme.css')

@app.cell
def _():
    import marimo as mo
    import pandas as pd
    import sqlite3,json
    from pathlib import Path
    import plotly.graph_objects as go
    return mo,pd,sqlite3,json,Path,go

@app.cell
def _(mo):
    refresh=mo.ui.run_button(label='Refresh recorded evidence')
    mo.vstack([mo.Html('''<style>:root{--accent-9:#147a82;--accent-10:#153d50}body{background:#f6f8fa}h1,h2,h3{color:#172e3d;font-family:Segoe UI,Arial,sans-serif}a{color:#147a82}</style>'''),mo.md('''# NeuroLoop / Research
    ### Follow the evidence.
    This companion notebook reads the same saved data as your workspace, including archived verification history.
    Explore timelines, interventions and compute cost. Refreshing never starts a model run.

    [Return to NeuroLoop workspace ↗](http://localhost:3010/workspace?view=research)'''),refresh])
    return (refresh,)

@app.cell
def _(Path,sqlite3,pd,refresh):
    refresh.value
    root=Path(__file__).resolve().parents[1]
    database=root/'data/neuroloop.db'
    if database.exists():
        connection=sqlite3.connect(f'file:{database.as_posix()}?mode=ro',uri=True)
        runs=pd.read_sql_query('SELECT r.id, p.name AS project, r.mode, r.status, r.evaluations_used, r.max_evaluations, r.compute_seconds, r.stop_reason, r.created_at FROM runs r LEFT JOIN projects p ON r.project_id=p.id ORDER BY r.created_at DESC',connection)
        experiments=pd.read_sql_query('SELECT run_id, sequence, operator, hypothesis, baseline_score, candidate_score, decision, evidence, created_at FROM experiments ORDER BY created_at',connection)
        evaluations=pd.read_sql_query('SELECT e.id, a.name AS creative, e.profile, e.evidence, e.duration_seconds, e.created_at FROM evaluations e LEFT JOIN assets a ON e.asset_id=a.id ORDER BY e.created_at DESC',connection)
        stats=pd.read_sql_query('SELECT context, operator, successes, failures, total_gain, total_seconds FROM policy_stats',connection)
        connection.close()
    else:
        runs,experiments,evaluations,stats=[pd.DataFrame() for _ in range(4)]
    return root,runs,experiments,evaluations,stats

@app.cell
def _(mo,runs,experiments,go):
    costs=go.Figure()
    if not runs.empty:
        completed=runs[runs.status=='completed'].head(20).iloc[::-1]
        costs.add_trace(go.Bar(x=completed.id.str[:8],y=completed.compute_seconds,marker_color='#147a82',name='Compute seconds'))
    costs.update_layout(template='plotly_white',height=330,title='Recorded compute per completed run',xaxis_title='Run ID',yaxis_title='Seconds',paper_bgcolor='#ffffff',plot_bgcolor='#ffffff')
    mo.vstack([mo.md('## The experiment record'),mo.ui.tabs({'Runs':mo.ui.table(runs,selection=None,page_size=10) if not runs.empty else mo.md('No recorded runs.'),'Interventions':mo.ui.table(experiments.drop(columns=['evidence']),selection=None,page_size=10) if not experiments.empty else mo.md('No recorded interventions.'),'Compute cost':mo.ui.plotly(costs)})])
    return

@app.cell
def _(mo,evaluations):
    choices={f"{row['creative']} · {row['id'][:8]}":row['id'] for _,row in evaluations.iterrows()} if not evaluations.empty else {}
    selected=mo.ui.dropdown(choices,value=next(iter(choices),None),label='Saved cortical evaluation')
    selected
    return (selected,)

@app.cell
def _(mo,selected,evaluations,json,go):
    if selected.value and not evaluations.empty:
        record=evaluations[evaluations.id==selected.value].iloc[0]
        evidence=json.loads(record['evidence'])
        figure=go.Figure()
        for label,key,color in [('Left hemisphere','left_mean','#147a82'),('Right hemisphere','right_mean','#398795')]:
            figure.add_trace(go.Scatter(x=evidence['times'],y=evidence[key],mode='lines+markers',name=label,line={'color':color}))
        figure.update_layout(template='plotly_white',paper_bgcolor='#ffffff',plot_bgcolor='#ffffff',title='Saved cortical mean by hemisphere',xaxis_title='Official segment start (seconds)',yaxis_title='Predicted model response units',height=400)
        display=mo.vstack([mo.ui.plotly(figure),mo.md('**Interpretation:** hemispheric means summarize predicted cortical values. They are not measured attention or emotional probabilities.'),mo.accordion({'Full numerical provenance':mo.json(evidence)})])
    else:
        display=mo.md('Choose an evaluation to inspect its actual saved cortical timeline.')
    display
    return

@app.cell
def _(mo,stats):
    if not stats.empty:
        summary=stats.copy()
        summary['attempts']=summary.successes+summary.failures
        summary['mean_gain']=summary.total_gain/summary.attempts.clip(lower=1)
        summary['mean_seconds']=summary.total_seconds/summary.attempts.clip(lower=1)
        policy_display=mo.ui.table(summary,selection=None,page_size=10)
    else:
        policy_display=mo.md('No policy statistics yet. Neural weights are frozen; valid experiments update only search statistics.')
    mo.vstack([mo.md('## Context-scoped operator experience'),policy_display,mo.md('''### Validation boundaries
    **Artifact improvement:** compare against a fixed reference objective.
    **Policy improvement:** requires fresh-versus-experienced policies on unseen briefs under equal budgets.
    **Human preference:** requires actual human evaluation. Neither a rising model score nor two models agreeing proves it.

    Kragel maps still require registration and transfer validation. TSAM is an optional experimental CPU readout with uncalibrated logits; scientific validation remains deferred. Service connection checks and current execution holds are available in the NeuroLoop workspace.''')])
    return

@app.cell
def _(mo,runs):
    project_filter=mo.ui.dropdown({'All recorded projects':'all', **{name:name for name in sorted(runs.project.dropna().unique())}},value='All recorded projects',label='Chart project filter')
    mo.vstack([mo.md('## The search, in perspective\nFilter the saved ledger and inspect decisions, trajectory and compute. Archived records are included; these are not held-out performance estimates.'),project_filter])
    return (project_filter,)

@app.cell
def _(mo,Path,runs,experiments,stats,project_filter):
    import sys
    chart_path=Path(__file__).resolve().parent
    if str(chart_path) not in sys.path: sys.path.insert(0,str(chart_path))
    from charts import experiment_figures
    filtered_runs=runs if project_filter.value=='all' else runs[runs.project==project_filter.value]
    filtered_experiments=experiments[experiments.run_id.isin(filtered_runs.id)]
    figures=experiment_figures(filtered_runs,filtered_experiments,stats if project_filter.value=='all' else stats.iloc[0:0])
    mo.vstack([mo.md(f'**{len(filtered_runs)} runs / {len(filtered_experiments)} interventions** in this selection. Costs refer to whole runs, not attributed per-edit compute.'),mo.ui.tabs({name:mo.ui.plotly(fig) for name,fig in figures.items()}) if figures else mo.md('No recorded data matches this filter.'),mo.md('**Parallel coordinates:** drag vertically along an axis to brush a range; double-click to clear. Mean gain and observed outcomes describe this sample only. Operator experience aggregates all retained contexts and is shown only with All recorded projects.')])
    return

if __name__=='__main__':app.run()
