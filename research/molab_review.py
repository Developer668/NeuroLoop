# /// script
# requires-python = ">=3.11"
# dependencies = ["marimo>=0.24.0", "pandas>=2.2", "plotly>=6.0"]
# ///
"""Portable CPU-only evidence review; upload a sanitized JSON export. No API keys."""

import marimo

__generated_with = "0.24.1"
app = marimo.App(width="full")


@app.cell
def _():
    import json
    import math
    import marimo as mo
    import pandas as pd
    import plotly.graph_objects as go

    return go, json, math, mo, pd


@app.cell
def _(mo):
    mo.md("""
    # NeuroLoop / Evidence review
    Inspect what the system actually recorded. Historical TRIBE predictions and search outcomes are kept distinct from the fresh TSAM CPU check.

    This notebook performs **no model inference**, reads **no local database**, uses **no credentials** and calls **no sponsor APIs**. Upload the sanitized evidence export below.
    """)
    return


@app.cell
def _(mo):
    upload = mo.ui.file(filetypes=[".json"], kind="area", max_size=5000000, label="Upload neuroloop-evidence.json")
    upload
    return (upload,)


@app.cell
def _(json, mo, pd, upload):
    mo.stop(not upload.value, mo.md("Upload the evidence file to load real records. No demonstration values are inserted."))
    try:
        packet = json.loads(upload.contents())
        if packet.get("schema") != "neuroloop-molab-evidence/v1":
            raise ValueError("Unsupported evidence schema")
        runs = pd.DataFrame(packet["runs"], columns=["id", "status", "evaluations_used", "compute_seconds"])
        experiments = pd.DataFrame(packet["experiments"], columns=["run_id", "sequence", "operator", "baseline_score", "candidate_score", "decision"])
        stats = pd.DataFrame(packet["stats"], columns=["context", "operator", "successes", "failures", "total_gain", "total_seconds"])
        evaluation_records = packet["evaluations"]
        tsam = packet.get("tsam")
    except (ValueError, KeyError, TypeError) as exc:
        mo.stop(True, mo.md(f"**Cannot load this evidence file:** {exc}"))
    mo.vstack([mo.md(f"**{len(runs)} historical runs · {len(experiments)} interventions · {len(evaluation_records)} cortical evaluations**"), mo.callout(mo.md(packet["source"]), kind="info"), mo.accordion({"What this export shares": mo.md(packet["privacy"])})])
    return evaluation_records, experiments, runs, stats, tsam


@app.cell
def _(go, math):
    """Figures use persisted numerical records only."""
    TEAL='#147a82'
    NAVY='#172e3d'
    CHART_GUIDANCE = {
        'Measured change': 'Above the dotted line means the candidate scored higher than its baseline. Check the recorded keep/revert decision: a small gain may miss the acceptance threshold. This is a model-reference score, not audience preference.',
        'Operator outcomes': 'Compare how often each controlled edit was kept, reverted or rejected. Counts describe the selected history; unequal attempts do not establish which operator is best.',
        'Search trajectory': 'Follow candidate scores within each run. A downward step can be a rejected experiment, not a loss of the saved best creative. Different runs may use different reference objectives.',
        'Parallel coordinates': 'Brush an axis to find interventions with similar gain or cost. Each line is an intervention; seconds and evaluation counts belong to its whole run and must not be summed across lines.',
        'Compute efficiency': 'Inspect how recorded compute grows with evaluations, including failed runs. Interrupted runs may have incomplete accounting; this is not a benchmark or a prediction of future latency.',
        'Run reliability': 'See the recorded completion, cancellation and failure counts. These operational outcomes include deliberate cancellations and are not a measured hardware reliability rate.',
        'Operator experience': 'Inspect observed mean gain by context and operator. These are the policyâ€™s past observations, not proof that it improves on unseen projects.',
    }
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
        times=evidence.get('times',[])
        values=[evidence.get('left_mean',[]),evidence.get('right_mean',[])]
        if not times or any(len(row)!=len(times) for row in values):
            return {}
        try:
            if not all(math.isfinite(float(value)) for row in [times,*values] for value in row):
                return {}
        except (TypeError,ValueError):
            return {}
        fig=go.Figure()
        for key,label,color in [('left_mean','Left',TEAL),('right_mean','Right',NAVY)]:
            fig.add_trace(go.Scatter(x=times,y=evidence.get(key,[]),mode='lines+markers',name=label,line=dict(color=color)))
        figures={'Hemisphere timeline':styled(fig,'Actual saved cortical means','Official segment start (s)','Model response units')}
        extent=max(max(abs(float(value)) for row in values for value in row),1e-9)
        figures['Hemisphere heatmap']=styled(go.Figure(go.Heatmap(x=times,y=['Left','Right'],z=values,colorscale=[[0,'#2866a4'],[.5,'#f4f7f7'],[1,'#c94726']],zmin=-extent,zmax=extent,zmid=0,colorbar=dict(title='Units'),hovertemplate='%{y} hemisphere<br>Segment start %{x:.2f} s<br>Mean %{z:.4f} units<extra></extra>')),'Saved hemisphere means over time','Official segment start (s)','Hemisphere')
        return figures

    return CHART_GUIDANCE, cortical_figures, experiment_figures, styled


@app.cell
def _(CHART_GUIDANCE, experiment_figures, experiments, mo, runs, stats):
    figures = experiment_figures(runs, experiments, stats)
    mo.vstack([mo.md("## How did the search behave?"), mo.ui.tabs({name: mo.vstack([mo.md(CHART_GUIDANCE[name]), mo.ui.plotly(fig)]) for name, fig in figures.items()}) if figures else mo.md("No search records in this export.")])
    return


@app.cell
def _(experiments, mo, runs):
    mo.accordion({"Recorded runs": mo.ui.table(runs, selection=None, page_size=10), "All interventions": mo.ui.table(experiments, selection=None, page_size=10)})
    return


@app.cell
def _(evaluation_records, mo):
    cortical_selector = mo.ui.dropdown([record["id"] for record in evaluation_records], value=evaluation_records[0]["id"] if evaluation_records else None, label="Cortical evaluation")
    mo.vstack([mo.md("## Where does the response change over time?"), cortical_selector])
    return (cortical_selector,)


@app.cell
def _(cortical_figures, cortical_selector, evaluation_records, mo):
    cortical_record = next((record for record in evaluation_records if record["id"] == cortical_selector.value), {})
    cortical_plots = cortical_figures(cortical_record)
    mo.vstack([mo.ui.tabs({name: mo.ui.plotly(fig) for name, fig in cortical_plots.items()}) if cortical_plots else mo.md("This evaluation has no complete cortical timeline."), mo.md("The x-axis is the official segment start in the stimulus, not runtime. These are hemisphere means in model-response units, not neurons, measured human emotion or attention. Heatmap limits are symmetric and specific to this evaluation; inspect the numeric legend when switching records.")])
    return


@app.cell
def _(go, mo, styled, tsam):
    if tsam and tsam.get("windows"):
        ts_window = tsam["windows"][0]
        logits_figure = styled(go.Figure(go.Bar(x=tsam["labels"], y=ts_window["logits"], marker_color=["#147a82" if value >= 0 else "#b75c45" for value in ts_window["logits"]])), "Actual TSAM CPU forward pass", "Upstream class order", "Uncalibrated logit")
        logits_figure.add_hline(y=0, line_color="#71818c", line_width=1)
        coverage_figure = styled(go.Figure([go.Bar(x=[sum(window["duration"] for window in tsam["windows"])], y=["Input coverage"], name="Evaluated complete window", orientation="h", marker_color="#147a82"), go.Bar(x=[tsam["omitted_tail_seconds"]], y=["Input coverage"], name="Omitted incomplete tail", orientation="h", marker_color="#b5bdc0")]), "Which part of the input was evaluated?", "Stimulus seconds", "")
        coverage_figure.update_layout(barmode="stack", height=280)
        ts_view = mo.vstack([mo.md(f"**Fresh Windows CPU check: {tsam['seconds']:.3f} seconds of processing.** {len(tsam['windows'])} complete five-second window(s); source duration {tsam['source_duration']:.1f} seconds."), mo.ui.tabs({"Class logits": mo.ui.plotly(logits_figure), "Input coverage": mo.ui.plotly(coverage_figure)}), mo.md("A positive logit is not a probability. The highest class does not establish what a viewer felt. No ground-truth labels or domain calibration were available for this technical check. The final incomplete second was not evaluated."), mo.accordion({"Model identity": mo.json({key:tsam[key] for key in ['profile','device','weights_sha256','interpretation']})})])
    else:
        ts_view = mo.md("No TSAM forward-pass evidence in this export.")
    mo.vstack([mo.md("## Does TSAM actually produce an output?"), ts_view])
    return


@app.cell
def _(mo):
    mo.md("""
    ## What the charts can establish
    - A saved numerical result and reproducible record are technical evidence.
    - A higher fixed-reference score can justify a local keep decision, but cannot establish human preference.
    - Policy self-improvement requires held-out briefs and equal-budget comparisons.
    - The current system is a bounded experimental search, not a scientifically validated emotion decoder or autonomously self-healing GPU runtime.

    **Local marimo** at port 2718 reads the local ledger. **Molab** hosts this portable notebook and only the data explicitly uploaded here. **W&B Models** stores experiment records; **Weave** records instrumented execution spans. This notebook does not contact either service.
    """)
    return


if __name__ == "__main__":
    app.run()
