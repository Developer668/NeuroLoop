"""Apply audited, reversible changes to the existing NeuroLoop implementation."""
from pathlib import Path
from datetime import datetime, timezone
import shutil
ROOT = Path(__file__).resolve().parents[1]
BACKUP = ROOT / 'data' / 'build-backups' / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')

def change(relative, old, new):
    path=ROOT/relative
    text=path.read_text(encoding='utf-8')
    if old not in text:
        if new in text: return
        raise RuntimeError(f'Expected source not found: {relative}: {old[:80]!r}')
    if text.count(old)!=1: raise RuntimeError(f'Ambiguous replacement: {relative}')
    backup=BACKUP/relative;backup.parent.mkdir(parents=True,exist_ok=True)
    if not backup.exists(): shutil.copy2(path,backup)
    temporary=path.with_name(path.name+'.new')
    temporary.write_text(text.replace(old,new),encoding='utf-8')
    temporary.replace(path)
    print('UPDATED',relative)

change('backend/neuroloop/config.py',"ROOT = Path(__file__).resolve().parents[2]", "ROOT = Path(__file__).resolve().parents[2]\nfrom dotenv import load_dotenv\nload_dotenv(ROOT / '.env', override=False)")
change('backend/neuroloop/config.py',"    research_url: str = 'http://localhost:2718'", "    research_url: str = 'http://localhost:2718'\n    research_enabled: bool = False\n    weave_enabled: bool = False\n    mcp_allowed_hosts: list[str] = ['localhost:*', '127.0.0.1:*', 'testserver']\n    mcp_allowed_origins: list[str] = ['http://localhost:*', 'http://127.0.0.1:*']")
change('backend/neuroloop/mcp_server.py',"from . import services", "from . import services\nfrom .config import settings")
change('backend/neuroloop/mcp_server.py',"allowed_hosts=['localhost:*','127.0.0.1:*','testserver'],allowed_origins=['http://localhost:*','http://127.0.0.1:*']", "allowed_hosts=settings().mcp_allowed_hosts,allowed_origins=settings().mcp_allowed_origins")
change('backend/neuroloop/media.py',"return {'characters':len(content),'preview':content[:200],'duration':None,'has_audio':False}","return {'characters':len(content),'preview_text':content[:200],'duration':None,'has_audio':False}")
change('backend/neuroloop/api.py',"    arrays=[np.load(x.prediction_path,allow_pickle=False,mmap_mode='r') for x in rows]", "    if any(not x.prediction_path or not Path(x.prediction_path).is_file() for x in rows):\n        raise HTTPException(409,'Comparison requires available cortical arrays for every selected evaluation')\n    arrays=[np.load(x.prediction_path,allow_pickle=False,mmap_mode='r') for x in rows]")
change('backend/neuroloop/api.py',"    result=services.get_run(identity);best_id=result['result'].get('best_asset_id')", "    result=services.get_run(identity)\n    if result['status'] in {'queued','running'}: raise HTTPException(409,'Wait for completion or cancel at a safe checkpoint before exporting')\n    best_id=result['result'].get('best_asset_id')")
change('backend/neuroloop/services.py',"    if body.asset_id in body.reference_ids: raise DomainError('The original cannot be its own reference')", "    if body.asset_id in body.reference_ids: raise DomainError('The original cannot be its own reference')") if False else None
change('backend/neuroloop/services.py',"        required=1+len(project.reference_ids)","        if len(set(project.reference_ids)) != len(project.reference_ids):\n            raise DomainError('Reference assets must be unique')\n        if body.mode=='optimize' and not body.operators:\n            raise DomainError('Select at least one permitted edit operator')\n        if body.mode=='optimize' and all(x.startswith('headline_') for x in body.operators) and not original.details.get('composition'):\n            raise DomainError('Headline timing requires an editable composition, not a flattened video')\n        if body.mode=='optimize' and project.constraints.get('preserve_duration', True) is not True:\n            raise DomainError('The current operators preserve duration; changing duration is unsupported')\n        supported_constraints={'preserve_duration','preserve_audio','locked_copy','max_filter_edits'}\n        if set(project.constraints)-supported_constraints:\n            raise DomainError('Unsupported constraints: '+', '.join(sorted(set(project.constraints)-supported_constraints)))\n        required=1+len(project.reference_ids)")
change('backend/neuroloop/services.py',"            if ref.sha256==original.sha256: raise DomainError('A reference cannot be a duplicate of the original')", "            if ref.sha256==original.sha256: raise DomainError('A reference cannot be a duplicate of the original')\n            if ref.kind != original.kind:\n                raise DomainError('Reference and original must use the same source modality for this comparison')\n            if ref.kind=='text':\n                raise DomainError('Cross-document timed-text comparison needs per-document timing; analyze documents individually first')\n        asr_ready=(settings().root/'models/preprocessing/faster-whisper-small/model.bin').is_file()\n        for media_id in [original.id]+project.reference_ids:\n            selected=db.get(Asset,media_id)\n            words=body.transcript if media_id==original.id else selected.details.get('transcript',[])\n            if selected.details.get('has_audio') and not body.no_speech and not words and not asr_ready:\n                raise DomainError('Speech preprocessing is unavailable. Supply timed words for each spoken asset, or explicitly confirm all inputs contain no speech.')")
change('backend/neuroloop/services.py',"ref.sha256==original.sha256", "ref.sha256==original.sha256") if False else None
change('backend/neuroloop/inference.py',"words=list(config.get('transcript') or [])", "words=list(config.get('transcript') or details.get('transcript') or [])")
change('backend/neuroloop/inference.py',"times=[float(x.start) for x in segments]", "times=[float(x.start) for x in segments]\n    (output/'segments.json').write_text(json.dumps([{'start':float(x.start),'duration':float(x.duration)} for x in segments]),encoding='utf8')")
change('backend/neuroloop/worker.py',"ref_config={**config,'transcript':[]}","ref_config={**config,'transcript':ref.details.get('transcript',[])}")
change('backend/neuroloop/worker.py',"    chain=list(best.details.get('edit_chain') or [])", "    chain=list(best.details.get('edit_chain') or [])\n    with Session() as db:\n        locked=db.get(Run,run_id).config['project_snapshot']['constraints']\n    if not operator.startswith('headline_') and len(chain)>=int(locked.get('max_filter_edits',2)):\n        raise ValueError('Bounded filter-edit limit reached; refusing cumulative proxy exploitation')")
change('backend/neuroloop/worker.py',"    extra={'source_asset_id':original.id", "    if original.details.get('has_audio') and locked.get('preserve_audio',True) and not details.get('has_audio'):\n        raise ValueError('Rendered candidate dropped the locked audio stream')\n    extra={'source_asset_id':original.id")
change('backend/neuroloop/worker.py',"    context_data={'profile':baseline.profile", "    context_data={'metric':METRIC,'min_gain':config['min_gain'],'operators':sorted(config['operators']),'profile':baseline.profile")
change('backend/neuroloop/worker.py',"    if run.mode!='optimize':", "    set_result(identity,result)\n    if run.mode!='optimize':")
change('backend/neuroloop/worker.py',"        if decision!='tradeoff': policy.record(context,operator,gain,time.monotonic()-beginning,config['min_gain'])", "        policy.record(context,operator,gain if keep else min(gain,0.0),time.monotonic()-beginning,config['min_gain'])")
change('backend/neuroloop/worker.py',"        if rejections>=2: raise StopRun('Two consecutive edits failed the minimum gain; stopped rather than generating indefinitely')", "        if rejections>=2:\n            emit(identity,'meta_stop','Plateau detected under the fixed acceptance contract. No more renders are justified.',consecutive_rejections=rejections,policy='bounded-plateau/v1')\n            raise StopRun('Two consecutive edits failed the minimum gain; stopped rather than generating indefinitely')")
# Experimental signatures remain disabled: downloaded scalar maps are not a verified registration.
print('Backups:',BACKUP)
