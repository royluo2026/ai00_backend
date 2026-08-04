"""Sign a detached release envelope with a publisher Ed25519 private PEM key."""
import argparse, base64, json
from pathlib import Path
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

parser = argparse.ArgumentParser()
parser.add_argument("release_json", type=Path)
parser.add_argument("private_key_pem", type=Path)
args = parser.parse_args()
manifest = json.loads(args.release_json.read_text(encoding="utf-8"))
digest = manifest["artifact"]["sha256"]
message = json.dumps({"artifact_sha256": digest, "manifest": manifest}, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
key = serialization.load_pem_private_key(args.private_key_pem.read_bytes(), password=None)
if not isinstance(key, Ed25519PrivateKey): raise SystemExit("private key must be Ed25519")
print(base64.b64encode(key.sign(message)).decode("ascii"))
