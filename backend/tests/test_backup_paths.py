import importlib.util,json,sqlite3
from pathlib import Path
import pytest

spec=importlib.util.spec_from_file_location('backup_workspace',Path(__file__).resolve().parents[2]/'scripts/backup_workspace.py')
backup=importlib.util.module_from_spec(spec);spec.loader.exec_module(backup)

@pytest.mark.parametrize('name',['/absolute/data/file','data/../data/file','data\\file','C:/data/file',''])
def test_rejects_noncanonical_manifest_paths(tmp_path,name):
    source=tmp_path/'source';source.mkdir()
    (source/'manifest.json').write_text(json.dumps({'version':1,'files':{name:'bad'},'source_root':'old'}))
    with pytest.raises(ValueError):backup.restore(source,tmp_path/'target')
    assert not (tmp_path/'target').exists()

def test_old_backup_restore_holds_execution_and_exports(tmp_path,monkeypatch):
    source=tmp_path/'source';(source/'data').mkdir(parents=True)
    database=source/'data/neuroloop.db'
    with sqlite3.connect(database) as db:
        db.execute('CREATE TABLE external_receipts (status TEXT)')
        db.execute("INSERT INTO external_receipts VALUES ('pending')")
    (source/'manifest.json').write_text(json.dumps({'version':1,'files':{'data/neuroloop.db':backup.digest(database)},'source_root':'old'}))
    # This test isolates restore behavior; full consistency is exercised in the real rehearsal.
    monkeypatch.setattr(backup,'check_database',lambda root:{'integrity':'test-fixture'})
    target=tmp_path/'target';backup.restore(source,target)
    assert json.loads((target/'data/inference-quarantine.json').read_text())['active']
    with sqlite3.connect(target/'data/neuroloop.db') as db:
        assert db.execute('SELECT status FROM external_receipts').fetchone()[0]=='held_after_restore'
