# NeuroLab

`python -m marimo edit notebooks/NeuroLab.py` opens the single model/research notebook. The registry cell owns all real models; start/stop controls own the shared worker. Status views show registrations and actual worker status separately from execution evidence.

Research reads require a separate restricted agent token and a real run UUID. The notebook displays real candidate lineage, run budgets, evidence, remote experiment receipts and raw export JSON. Nothing is populated with made-up emotion curves, scores or sales. Additional scientific plots can be built from actual returned time series; no placeholder charts are drawn.

Changing/re-executing notebook cells while a worker is active can replace registry objects. Stop the worker before changing model registrations and retain its receipt directory. A running notebook session is not a permanent production backend.
