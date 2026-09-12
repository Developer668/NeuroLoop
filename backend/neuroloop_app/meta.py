"""Real Meta Marketing API handoff: durable, approved, PAUSED-only creations.

No activation/budget-edit API exists. Each remote mutation has a persisted intent;
a missing acknowledgement stops for reconciliation instead of creating duplicates.
Reference: Meta's official facebook-python-business-sdk adobject contracts,
retrieved 2026-09-12 under docs/vendor/meta-*.py.txt.
"""
from __future__ import annotations
import base64
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile
import httpx
from sqlalchemy import select
from .db import Asset, Deployment, Intervention, Run, record
from .domain import digest, now
from .engine import DomainError, required, emit


class MetaFailure(RuntimeError):
    def __init__(self, code: str, detail: str, uncertain: bool = False):
        self.code, self.uncertain = code, uncertain
        super().__init__(detail)


class MetaClient:
    def __init__(self, settings, client=None):
        self.settings = settings
        self.client = client or httpx.Client(timeout=120, follow_redirects=False)

    def request(self, method, node, fields=None, files=None):
        version = self.settings.meta_graph_version
        token = self.settings.meta_access_token.get_secret_value()
        if not token or not re.fullmatch(r'v[0-9]+\.[0-9]+', version):
            raise MetaFailure('NOT_CONFIGURED', 'Set a supported Meta Graph version and server-side access token.')
        if not re.fullmatch(r'(?:act_)?[0-9]+(?:/[a-z_]+)?', node):
            raise MetaFailure('INVALID_REQUEST', 'Invalid Meta object path')
        data = {k: json.dumps(v, separators=(',', ':')) if isinstance(v, (dict, list, bool)) else str(v) for k, v in (fields or {}).items()}
        try:
            r = self.client.request(method, f'https://graph.facebook.com/{version}/{node}',
                    headers={'Authorization': 'Bearer ' + token},
                    **({'params': data} if method == 'GET' else {'data': data, 'files': files}))
        except httpx.TransportError as exc:
            raise MetaFailure('TRANSPORT_FAILURE', 'Meta request acknowledgement was lost.', method == 'POST') from exc
        try:
            body = r.json()
        except ValueError as exc:
            raise MetaFailure('INVALID_RESPONSE', 'Meta returned an unreadable response.', method == 'POST') from exc
        if r.status_code >= 400 or 'error' in body:
            error = body.get('error', {})
            # No raw request, response or access token is placed in logs/UI.
            code = str(error.get('code', r.status_code))
            raise MetaFailure('META_' + code, f'Meta rejected request (code {code}; HTTP {r.status_code}).', method == 'POST' and r.status_code >= 500)
        return body

    def create(self, account, edge, fields=None, files=None):
        if edge in {'campaigns', 'adsets', 'ads'} and (fields or {}).get('status') != 'PAUSED':
            raise MetaFailure('POLICY_DENIED', 'Only PAUSED ad objects may be created.')
        return self.request('POST', account + '/' + edge, fields, files)


class MetaService:
    def __init__(self, store, objects, client=None):
        self.store, self.objects = store, objects
        self.client = client or MetaClient(store.settings)

    def enqueue(self, identity, review_digest):
        if not self.store.settings.meta_access_token.get_secret_value() or not re.fullmatch(r'v[0-9]+\.[0-9]+', self.store.settings.meta_graph_version):
            raise DomainError('NOT_CONFIGURED: Meta token and supported Graph version are required.', 503)
        with self.store.transaction() as s:
            row = required(s, Deployment, identity, lock=True)
            if row.state not in {'APPROVED', 'FAILED', 'QUEUED', 'DEPLOYED'} or not row.approved_at:
                raise DomainError('A matching human approval is required; uncertain mutations require manual reconciliation.')
            if row.review_digest != review_digest or digest(row.spec) != row.review_digest:
                raise DomainError('Deployment review does not match the approved immutable specification.')
            if row.state not in {'QUEUED', 'DEPLOYED'}:
                row.state, row.error = 'QUEUED', None
                emit(s, required(s, Run, row.run_id), 'META_QUEUED', experiment_id=row.id)
            return record(row)

    def _step(self, identity, key, callback):
        with self.store.transaction() as s:
            row = required(s, Deployment, identity, lock=True)
            if row.state != 'DEPLOYING':
                raise MetaFailure('STATE_CONFLICT', 'Deployment is no longer owned by this worker.')
            entities = dict(row.entities)
            if key in entities:
                return entities[key]
            if entities.get('_inflight'):
                raise MetaFailure('UNCERTAIN', 'A prior mutation must be reconciled before continuation.', True)
            entities['_inflight'] = key
            row.entities = entities
        value = callback()
        if not isinstance(value, str) or not value:
            raise MetaFailure('MISSING_RECEIPT', 'Meta did not return an immutable object identifier.', True)
        with self.store.transaction() as s:
            row = required(s, Deployment, identity, lock=True)
            row.entities = {**{k:v for k,v in row.entities.items() if k != '_inflight'}, key: value}
            emit(s, required(s, Run, row.run_id), 'META_OBJECT_CREATED', experiment_id=identity, object_type=key, remote_id=value)
        return value

    def _identifier(self, response):
        value = response.get('id')
        if not isinstance(value, str) or not value.isdigit():
            raise MetaFailure('MISSING_RECEIPT', 'Meta creation receipt has no valid object ID.', True)
        return value

    def _image(self, account, path):
        if path.stat().st_size > 20 * 1024 * 1024:
            raise MetaFailure('MEDIA_LIMIT', 'Meta image upload adapter is limited to 20 MB.')
        response = self.client.create(account, 'adimages', {'bytes': base64.b64encode(path.read_bytes()).decode()})
        images = list(response.get('images', {}).values())
        value = images[0].get('hash') if len(images) == 1 else None
        if not isinstance(value, str) or not value:
            raise MetaFailure('MISSING_RECEIPT', 'Meta image hash was not returned.', True)
        return value

    def drain(self):
        # The local lock covers one process. PostgreSQL row locks protect cross-host claims.
        with self.store.transaction() as s:
            row = s.scalar(select(Deployment).where(Deployment.state == 'QUEUED').order_by(Deployment.created_at).with_for_update(skip_locked=True).limit(1))
            if row is None:
                return {'status':'IDLE'}
            row.state = 'DEPLOYING'
            row.entities = {**row.entities, '_started_at': now()}
            data = record(row)
            asset = record(required(s, Asset, row.spec['asset_id']))
        identity, spec = data['id'], data['spec']
        try:
            if digest(spec) != data['review_digest'] or spec['status'] != 'PAUSED' or not data['approved_at'] or not spec['research_license_approved_for_commercial_use']:
                raise MetaFailure('POLICY_DENIED', 'Immutable human approval or licensing gate is invalid.')
            account = 'act_' + spec['ad_account_id'].removeprefix('act_')
            account_data = self.client.request('GET', account, {'fields':'id,currency'})
            if account_data.get('currency') != spec['currency']:
                raise MetaFailure('CURRENCY_MISMATCH', 'Ad account currency differs from the reviewed budget currency.')
            with tempfile.TemporaryDirectory(prefix='meta-', dir=self.objects.temp) as folder:
                path = Path(folder) / ('creative.mp4' if asset['kind']=='video' else 'creative.png')
                with path.open('xb') as f:
                    for chunk in self.objects.stream(asset['object_key']):
                        f.write(chunk)
                if hashlib.sha256(path.read_bytes()).hexdigest() != spec['asset_sha256']:
                    raise MetaFailure('ASSET_MISMATCH', 'Reviewed media hash differs from storage.')
                if asset['kind'] == 'video':
                    def upload_video():
                        with path.open('rb') as f:
                            return self._identifier(self.client.create(account, 'advideos', {'title':'NeuroLoop '+identity}, {'source':(path.name, f, asset['mime'])}))
                    media_id = self._step(identity, 'video_id', upload_video)
                    thumb = Path(folder) / 'thumbnail.jpg'
                    try:
                        subprocess.run([self.store.settings.ffmpeg, '-v','error','-i',str(path),'-frames:v','1','-q:v','2',str(thumb)],check=True,timeout=45,capture_output=True)
                    except (OSError, subprocess.SubprocessError) as exc:
                        raise MetaFailure('UNAVAILABLE', 'ffmpeg could not derive the real video thumbnail.') from exc
                    image_hash = self._step(identity, 'image_hash', lambda:self._image(account, thumb))
                elif asset['kind'] == 'image':
                    image_hash = self._step(identity, 'image_hash', lambda:self._image(account, path))
                    media_id = None
                else:
                    raise MetaFailure('INVALID_MEDIA','Only validated images and videos may be deployed.')
            name = 'NeuroLoop ' + identity
            campaign_id = self._step(identity,'campaign_id',lambda:self._identifier(self.client.create(account,'campaigns',{
                'name':name,'objective':'OUTCOME_TRAFFIC','special_ad_categories':spec.get('special_ad_categories',[]),'status':'PAUSED'})))
            adset_id = self._step(identity,'adset_id',lambda:self._identifier(self.client.create(account,'adsets',{
                'name':name,'campaign_id':campaign_id,'daily_budget':spec['daily_budget_minor'], 'billing_event':'IMPRESSIONS',
                'optimization_goal':'LINK_CLICKS','bid_strategy':'LOWEST_COST_WITHOUT_CAP','destination_type':'WEBSITE',
                'targeting':spec['audience'],'status':'PAUSED'})))
            cta={'type':'LEARN_MORE','value':{'link':spec['destination']}}
            story={'page_id':spec['page_id']}
            if media_id:
                story['video_data']={'video_id':media_id,'image_hash':image_hash,'message':spec['message'],'title':spec['headline'],'call_to_action':cta}
            else:
                story['link_data']={'image_hash':image_hash,'message':spec['message'],'name':spec['headline'],'link':spec['destination'],'call_to_action':cta}
            creative_id=self._step(identity,'creative_id',lambda:self._identifier(self.client.create(account,'adcreatives',{'name':name,'object_story_spec':story})))
            ad_id=self._step(identity,'ad_id',lambda:self._identifier(self.client.create(account,'ads',{'name':name,'adset_id':adset_id,'creative':{'creative_id':creative_id},'status':'PAUSED'})))
            receipts={}
            for kind, remote_id in [('campaign',campaign_id),('adset',adset_id),('ad',ad_id)]:
                receipt=self.client.request('GET',remote_id,{'fields':'id,status'})
                if receipt.get('id') != remote_id or receipt.get('status') != 'PAUSED':
                    raise MetaFailure('READBACK_FAILED', 'Meta did not confirm every object is PAUSED. Inspect Ads Manager.', True)
                receipts[kind]=receipt
            with self.store.transaction() as s:
                row=required(s,Deployment,identity,lock=True)
                row.state='DEPLOYED'; row.error=None; row.entities={**row.entities,'_verified_at':now(),'_receipts':receipts}
                emit(s,required(s,Run,row.run_id),'META_PAUSED_VERIFIED',experiment_id=identity,ad_id=ad_id)
            return {'status':'DEPLOYED','experiment_id':identity,'ad_id':ad_id,'delivery_status':'PAUSED'}
        except Exception as exc:
            uncertain = not isinstance(exc,MetaFailure) or exc.uncertain
            with self.store.transaction() as s:
                row=required(s,Deployment,identity,lock=True)
                row.state='NEEDS_RECONCILIATION' if uncertain else 'FAILED'
                row.error=f'{getattr(exc,"code",type(exc).__name__)}: '+ (str(exc) if isinstance(exc,MetaFailure) else 'Unexpected processing failure; inspect the persisted remote receipts.')
                if not uncertain:
                    row.entities={k:v for k,v in row.entities.items() if k!='_inflight'}
                emit(s,required(s,Run,row.run_id),'META_FAILED',experiment_id=identity,state=row.state,error=row.error)
            return {'status':row.state,'experiment_id':identity}

    def recover_stale(self):
        # Never reissue a remote POST after a process crash. A human reconciles IDs.
        with self.store.transaction() as s:
            rows=s.scalars(select(Deployment).where(Deployment.state=='DEPLOYING').with_for_update(skip_locked=True))
            for row in rows:
                if now()-row.entities.get('_started_at',now())>1800:
                    row.state='NEEDS_RECONCILIATION'
                    row.error='Deployment worker lease expired. Reconcile persisted remote IDs in Ads Manager; automatic retries are disabled.'

    def insights(self, identity, since: str, until: str):
        from datetime import date
        start,end=date.fromisoformat(since),date.fromisoformat(until)
        if not 0 <= (end-start).days <= 90:
            raise DomainError('Choose a reporting interval of 0–90 days.',422)
        with self.store.read() as s:
            row=required(s,Deployment,identity)
            if row.state not in {'DEPLOYED','COLLECTING','INCONCLUSIVE'} or not row.entities.get('ad_id'):
                raise DomainError('No verified remote ad is available.')
            ad_id=row.entities['ad_id']
        results=[]; cursor=None
        for _ in range(10):
            params={'fields':'ad_id,impressions,reach,spend,clicks,ctr,actions,action_values','time_range':{'since':since,'until':until},'limit':100}
            if cursor:params['after']=cursor
            response=self.client.request('GET',ad_id+'/insights',params)
            results.extend(response.get('data',[]))
            if not response.get('paging',{}).get('next'):break
            cursor=response.get('paging',{}).get('cursors',{}).get('after')
            if not cursor:raise MetaFailure('PAGINATION','Meta pagination could not be completed.')
        else:raise MetaFailure('PAGINATION','Reporting limit exceeded; narrow the time interval.')
        receipt={'source':'Meta Marketing API','fetched_at':now(),'since':since,'until':until,'rows':results,'conclusion':'INCONCLUSIVE','attribution_quality':'variant_level'}
        with self.store.transaction() as s:
            row=required(s,Deployment,identity,lock=True)
            row.metrics=[*row.metrics,receipt]; row.state='INCONCLUSIVE'
            ledger=s.scalar(select(Intervention).where(Intervention.creative_id==row.spec['creative_id']))
            if ledger:
                ledger.observation={**ledger.observation,'real_campaign_metrics':[*ledger.observation.get('real_campaign_metrics',[]),receipt]}
            emit(s,required(s,Run,row.run_id),'META_INSIGHTS_INGESTED',experiment_id=identity,report_rows=len(results),conclusion='INCONCLUSIVE')
        return receipt
