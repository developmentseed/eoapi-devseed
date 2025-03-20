"""API settings."""

import base64
import json
from typing import Any, Dict, Optional

import boto3
from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings
from titiler.pgstac.settings import PostgresSettings as _PostgresSettings


def get_secret_dict(secret_name: str) -> Dict:
    """Retrieve secrets from AWS Secrets Manager

    Args:
        secret_name (str): name of aws secrets manager secret containing database connection secrets
        profile_name (str, optional): optional name of aws profile for use in debugger only

    Returns:
        secrets (dict): decrypted secrets in dict
    """

    # Create a Secrets Manager client
    session = boto3.session.Session()
    client = session.client(service_name="secretsmanager")

    get_secret_value_response = client.get_secret_value(SecretId=secret_name)

    if "SecretString" in get_secret_value_response:
        return json.loads(get_secret_value_response["SecretString"])
    else:
        return json.loads(base64.b64decode(get_secret_value_response["SecretBinary"]))


class ApiSettings(BaseSettings):
    """API settings"""

    name: str = "eoAPI-raster"
    cors_origins: str = "*"
    cors_methods: str = "GET,POST,OPTIONS"
    cachecontrol: str = "public, max-age=3600"
    debug: bool = False
    root_path: str = ""

    model_config = {
        "env_file": ".env",
        "extra": "allow",
    }

    @field_validator("cors_origins")
    def parse_cors_origin(cls, v):
        """Parse CORS origins."""
        return [origin.strip() for origin in v.split(",")]

    @field_validator("cors_methods")
    def parse_cors_methods(cls, v):
        """Parse CORS methods."""
        return [method.strip() for method in v.split(",")]


class PostgresSettings(_PostgresSettings):
    """Extent titiler-pgstac PostgresSettings settings"""

    pgstac_secret_arn: Optional[str] = None

    @model_validator(mode="before")
    def get_postgres_setting(cls, data: Any) -> Any:
        if arn := data.get("pgstac_secret_arn"):
            secret = get_secret_dict(arn)
            data.update(
                {
                    "postgres_host": secret["host"],
                    "postgres_dbname": secret["dbname"],
                    "postgres_user": secret["username"],
                    "postgres_pass": secret["password"],
                    "postgres_port": secret["port"],
                }
            )

        return data
