import hashlib
import hmac
import json

from app.config import settings


def canonicalize_payload(payload: dict) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def sign_manifest(scope_type: str, scope_id: str, payload: dict) -> str:
    secret = settings.secret_key.encode("utf-8")
    canonical_payload = canonicalize_payload(payload)
    signing_input = f"{scope_type}|{scope_id}|{canonical_payload}".encode("utf-8")
    return hmac.new(secret, signing_input, hashlib.sha256).hexdigest()


def verify_manifest(scope_type: str, scope_id: str, payload: dict, signature: str) -> bool:
    expected = sign_manifest(scope_type, scope_id, payload)
    return hmac.compare_digest(expected, signature)
