"""Secrets loader for Rolodex.
Supports multiple sources for production readiness:
- Local secrets file at ROLODEX_SECRETS_PATH or ~/.rolodex/secrets.json
- HashiCorp Vault (OSS) via VAULT_ADDR/VAULT_TOKEN and ROLODEX_VAULT_PATH or VAULT_SECRET_PATH

In production, prefer Vault; local file is a fallback for dev/CI. AWS Secrets Manager is no longer the default path but can be added later if desired.
"""
import json
import os


def load_secrets():
    # 1) Try local file first
    secrets_path = os.environ.get('ROLODEX_SECRETS_PATH', os.path.expanduser('~/.rolodex/secrets.json'))
    if secrets_path and os.path.exists(secrets_path):
        try:
            with open(secrets_path, 'r') as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
        except Exception:
            # Fall back to Vault if configured
            pass

    # 2) Fall back to HashiCorp Vault if configured
    vault_addr = os.environ.get('VAULT_ADDR')
    vault_token = os.environ.get('VAULT_TOKEN')
    vault_path = os.environ.get('ROLODEX_VAULT_PATH') or os.environ.get('VAULT_SECRET_PATH') or 'secret/rolodex/config'
    if vault_addr and vault_token:
        try:
            # Lazy import so environments without hvac don't fail
            import hvac  # type: ignore
            client = hvac.Client(url=vault_addr, token=vault_token)
            # Attempt KV v2 path read
            try:
                read = client.secrets.kv.v2.read_secret_version(path=vault_path)
                data = read.get('data', {}).get('data', {})
                if isinstance(data, dict):
                    # Cache locally for faster subsequent boots
                    if secrets_path:
                        try:
                            os.makedirs(os.path.dirname(secrets_path), exist_ok=True)
                            with open(secrets_path, 'w') as f:
                                json.dump(data, f, indent=2)
                        except Exception:
                            pass
                    return data
            except Exception:
                pass
        except Exception:
            pass

    return {}
