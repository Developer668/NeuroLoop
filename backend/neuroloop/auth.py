"""Local browser session exchange; external MCP still uses the configured bearer token.

Local session issuance is restricted to a loopback-bound deployment and same-origin
requests. Public deployments must disable this route and supply real identity.
"""
import hashlib,secrets,time,threading
from .config import settings

_sessions: dict[str,float]={}
_lock=threading.Lock()

def revoke_session(value: str) -> bool:
    with _lock:
        return _sessions.pop(hashlib.sha256(value.encode()).hexdigest(), None) is not None

def verify_token(value: str) -> bool:
    if secrets.compare_digest(value,settings().auth_token): return True
    key=hashlib.sha256(value.encode()).hexdigest()
    with _lock:
        expiration=_sessions.get(key,0)
        if expiration<time.time():
            _sessions.pop(key,None);return False
    return True

def issue_local_session() -> str:
    token=secrets.token_urlsafe(40)
    with _lock:
        for key,expiry in list(_sessions.items()):
            if expiry<time.time():_sessions.pop(key,None)
        _sessions[hashlib.sha256(token.encode()).hexdigest()]=time.time()+8*3600
    return token
