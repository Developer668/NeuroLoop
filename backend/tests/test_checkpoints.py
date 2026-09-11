import json
import pytest
from neuroloop.checkpoints import validate_shards

@pytest.mark.parametrize('shard', ['../outside.safetensors', '..\\outside.safetensors', 'C:\\outside.safetensors', '/tmp/outside', 'shard:stream', 'missing.safetensors'])
def test_checkpoint_index_cannot_escape_or_name_missing_files(tmp_path,shard):
    (tmp_path/'model.safetensors.index.json').write_text(json.dumps({'weight_map':{'weight':shard}}))
    with pytest.raises(ValueError):validate_shards(tmp_path)

def test_checkpoint_only_regular_local_shards(tmp_path):
    (tmp_path/'weights.safetensors').write_bytes(b'index-validation-only')
    index=tmp_path/'model.safetensors.index.json'
    index.write_text(json.dumps({'weight_map':{'weight':'weights.safetensors'}}))
    assert validate_shards(tmp_path)==[index.name]
    (tmp_path/'directory').mkdir()
    index.write_text(json.dumps({'weight_map':{'weight':'directory'}}))
    with pytest.raises(ValueError):validate_shards(tmp_path)
