"""Tests use an isolated workspace, never the user's live project database."""
import os,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
TEST_PARENT=ROOT/'data/tmp'
TEST_PARENT.mkdir(parents=True,exist_ok=True)
TEST_ROOT=Path(tempfile.mkdtemp(prefix='neuroloop-tests-',dir=TEST_PARENT))
os.environ['NEUROLOOP_ROOT']=str(TEST_ROOT)
os.environ['NEUROLOOP_AUTH_TOKEN']='unit-test-authorization-token-not-for-deployment'
os.environ['NEUROLOOP_DATABASE_URL']='sqlite:///'+(TEST_ROOT/'tests.sqlite').as_posix()
os.environ['NEUROLOOP_WEAVE_ENABLED']='false'
os.environ['NEUROLOOP_PLANNER_ENABLED']='false'
sys.path.insert(0,str(ROOT/'backend'))
import pytest
from fastapi.testclient import TestClient
from neuroloop.api import app
from neuroloop.db import initialize

@pytest.fixture(scope='session')
def client():
    initialize()
    with TestClient(app) as value:
        yield value

@pytest.fixture
def headers():
    return {'Authorization':'Bearer '+os.environ['NEUROLOOP_AUTH_TOKEN']}

@pytest.fixture
def authed(headers):
    return headers
