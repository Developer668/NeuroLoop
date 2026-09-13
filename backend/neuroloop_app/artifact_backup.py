"""Durable W&B media and evidence export, separate from Weave call tracing."""
from __future__ import annotations
import hashlib
import json
import tempfile
from pathlib import Path
from sqlalchemy import select
from .db import ArtifactBackup, Asset, NotebookEvidence, Run, record
from .domain import digest, now


class ArtifactExporter:
    def __init__(self, store, objects, engine):
        self.store, self.objects, self.engine = store, objects, engine

    def drain(self):
        settings = self.store.settings
        if not settings.wandb_artifacts_enabled or not settings.wandb_project or not settings.wandb_api_key.get_secret_value():
            return
        with self.store.read() as session:
            assets = [record(a) for a in session.scalars(select(Asset))]
            evidence = [record(e) for e in session.scalars(select(NotebookEvidence))]
            runs = [r.id for r in session.scalars(select(Run))]
        entries = [("asset-"+a["id"], a["sha256"], a, None) for a in assets]
        entries += [("evidence-"+e["id"], digest(e), None, e) for e in evidence]
        for identity in runs:
            snapshot = self.engine.snapshot(identity)
            entries.append(("run-"+identity, digest(snapshot), None, snapshot))
        for identity, content_hash, asset, document in entries:
            with self.store.transaction() as session:
                row = session.get(ArtifactBackup, identity)
                if row and ((row.content_hash == content_hash and row.status == "VERIFIED") or row.next_attempt > now()):
                    continue
                if row is None:
                    row = ArtifactBackup(id=identity, content_hash=content_hash)
                    session.add(row)
                row.content_hash, row.status, row.next_attempt = content_hash, "UPLOADING", now()+120
            try:
                url = self._upload(identity, content_hash, asset, document)
                with self.store.transaction() as session:
                    row = session.get(ArtifactBackup, identity)
                    row.status, row.url, row.error, row.updated_at = "VERIFIED", url, None, now()
                    row.next_attempt = now()+30
            except Exception as exc:
                with self.store.transaction() as session:
                    row = session.get(ArtifactBackup, identity)
                    row.status, row.error, row.updated_at = "FAILED", type(exc).__name__ + ": artifact upload/readback failed; retry scheduled", now()
            return  # One upload per maintenance pass; model jobs never wait on W&B.

    def _upload(self, identity, content_hash, asset, document):
        import wandb
        settings = self.store.settings
        entity, project = settings.wandb_project.split("/", 1)
        api = wandb.Api(api_key=settings.wandb_api_key.get_secret_value())
        remote_name = f"{entity}/{project}/{identity}:{content_hash[:16]}"
        try:
            remote = api.artifact(remote_name)
            if remote.metadata.get("source_sha256") == content_hash:
                return remote.url
        except wandb.errors.CommError:
            pass
        with tempfile.TemporaryDirectory(dir=self.objects.temp) as folder:
            path = Path(folder) / (asset["name"] if asset else "receipt.json")
            if asset:
                with path.open("wb") as output:
                    for block in self.objects.stream(asset["object_key"]):
                        output.write(block)
                if hashlib.sha256(path.read_bytes()).hexdigest() != content_hash:
                    raise ValueError("Stored media checksum mismatch")
            else:
                path.write_text(json.dumps(document, indent=2), encoding="utf-8")
            artifact = wandb.Artifact(identity, type="neuroloop-media" if asset else "neuroloop-evidence",
                metadata={"source_sha256":content_hash,"application":"NeuroLoop","source_kind":asset["kind"] if asset else "receipt"})
            artifact.add_file(str(path), name=path.name)
            with wandb.init(entity=entity, project=project, id=identity.replace("-", ""), resume="allow", job_type="evidence-backup",
                    settings=wandb.Settings(api_key=settings.wandb_api_key.get_secret_value(), quiet=True, console="off", disable_git=True),
                    dir=str(self.store.settings.data_dir)) as run:
                if asset and asset["kind"] == "image":
                    run.log({"creative":wandb.Image(str(path),caption=asset["name"])})
                run.log_artifact(artifact, aliases=[content_hash[:16], "latest"]).wait(timeout=120)
            remote = api.artifact(remote_name)
            if remote.metadata.get("source_sha256") != content_hash or path.name not in remote.manifest.entries:
                raise ValueError("W&B readback did not confirm the artifact")
            return remote.url
