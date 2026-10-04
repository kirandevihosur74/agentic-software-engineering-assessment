"""Create a local reviewer key and worker trust file outside the project."""
import argparse
import base64
import json
import os
from pathlib import Path
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--directory', required=True)
    parser.add_argument('--reviewer', default='local-user')
    args = parser.parse_args()
    root = Path(args.directory).resolve()
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    if (root/'reviewer.pem').exists() or (root/'trusted-reviewers.json').exists():
        raise ValueError('Refusing to overwrite existing approval keys')
    key = Ed25519PrivateKey.generate()
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    with os.fdopen(os.open(root/'reviewer.pem', os.O_WRONLY|os.O_CREAT|os.O_EXCL, 0o600), 'wb') as f:
        f.write(pem)
    public = base64.b64encode(key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)).decode()
    with os.fdopen(os.open(root/'trusted-reviewers.json', os.O_WRONLY|os.O_CREAT|os.O_EXCL, 0o600), 'w') as f:
        json.dump({args.reviewer: {'public_key': public, 'gates': ['apply', 'review']}}, f, indent=2)
    print('Created approval key and trust file in ' + str(root))


if __name__ == '__main__':
    main()
