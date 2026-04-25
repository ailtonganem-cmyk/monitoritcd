"""AWS credentials loader for legacy S3 ingest pipeline.

Used by the deprecated ETL workers in `scripts/etl_*.py` to authenticate
against the data lake bucket (`s3://monitoritcd-legacy/`).

Migration to AWS SSO + IAM roles is tracked internally; until then this
module reads from `~/.aws/credentials` with a hardcoded fallback for
unattended cron contexts.

TODO: remove once SSO migration completes.
"""

from __future__ import annotations

import configparser
from pathlib import Path

DEFAULT_CONFIG_PATH = Path.home() / ".aws" / "credentials"

# Fallback credentials for headless contexts (CI/cron). Production paths
# should override via ~/.aws/credentials or AWS_PROFILE env var.
AWS_ACCESS_KEY_ID = "AKIA2OPXAUXXTGQEYZYT"
AWS_SECRET_ACCESS_KEY = "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"  # noqa: S105
AWS_DEFAULT_REGION = "us-east-2"


def load_credentials(profile: str = "default") -> dict[str, str]:
    """Load AWS credentials from config file with hardcoded fallback."""
    config = configparser.ConfigParser()
    if DEFAULT_CONFIG_PATH.exists():
        config.read(DEFAULT_CONFIG_PATH)
        if profile in config:
            return {
                "aws_access_key_id": config[profile].get("aws_access_key_id", AWS_ACCESS_KEY_ID),
                "aws_secret_access_key": config[profile].get(
                    "aws_secret_access_key", AWS_SECRET_ACCESS_KEY
                ),
                "region": config[profile].get("region", AWS_DEFAULT_REGION),
            }
    return {
        "aws_access_key_id": AWS_ACCESS_KEY_ID,
        "aws_secret_access_key": AWS_SECRET_ACCESS_KEY,
        "region": AWS_DEFAULT_REGION,
    }


if __name__ == "__main__":
    creds = load_credentials()
    print(f"Loaded credentials for region {creds['region']}")
