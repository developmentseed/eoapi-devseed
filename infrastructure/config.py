from typing import Dict, List, Optional, Tuple, Type, Union

from aws_cdk import aws_ec2
from pydantic import Field, ValidationInfo, field_validator, model_validator
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)
from typing_extensions import Self


class AppConfig(BaseSettings):
    project_id: str = Field(description="Project ID", default="eoapi-template-demo")
    stage: str = Field(description="Stage of deployment", default="test")
    # because of its validator, `tags` should always come after `project_id` and `stage`
    tags: Optional[Dict[str, str]] = Field(
        description="""Tags to apply to resources. If none provided,
        will default to the defaults defined in `default_tags`.
        Note that if tags are passed to the CDK CLI via `--tags`,
        they will override any tags defined here.""",
        default=None,
    )
    auth_provider_jwks_url: Optional[str] = Field(
        description="""Auth Provider JSON Web Key Set URL for
        ingestion authentication. If not provided,
        no authentication will be required.""",
        default=None,
    )
    data_access_role_arn: Optional[str] = Field(
        description="""Role ARN for data access, that will be
        used by the STAC ingestor for validation of assets
        located in S3 and for the tiler application to access
        assets located in S3. If none, the role will be
        created at runtime with full S3 read access. If
        provided, the existing role must be configured to
        allow the tiler and STAC ingestor lambda roles to
        assume it. See https://github.com/developmentseed/eoapi-cdk""",
        default=None,
    )
    db_instance_type: str = Field(
        description="Database instance type", default="t3.micro"
    )
    db_allocated_storage: int = Field(
        description="Allocated storage for the database", default=5
    )
    public_db_subnet: bool = Field(
        description="Whether to put the database in a public subnet", default=True
    )
    nat_gateway_count: int = Field(
        description="Number of NAT gateways to create",
        default=0,
    )
    bastion_host: bool = Field(
        description="""Whether to create a bastion host. It can typically
        be used to make administrative connections to the database if
        `public_db_subnet` is False""",
        default=False,
    )
    bastion_host_create_elastic_ip: bool = Field(
        description="""Whether to create an elastic IP for the bastion host.
        Ignored if `bastion_host` equals `False`""",
        default=False,
    )
    bastion_host_allow_ip_list: List[str] = Field(
        description="""YAML file containing list of IP addresses to
        allow SSH access to the bastion host. Ignored if `bastion_host`
        equals `False`.""",
        default=[],
    )
    bastion_host_user_data: Union[str, aws_ec2.UserData] = Field(
        description="""Path to file containing user data for the bastion host.
        Ignored if `bastion_host` equals `False`.""",
        default=aws_ec2.UserData.for_linux(),
    )
    raster_buckets: List[str] = Field(
        description="""Path to YAML file containing list of
        buckets to grant access to the Raster API""",
        default=[],
    )
    stac_ingestor: bool = Field(
        description="Whether to add STAC Ingestor services, Default is False",
        default=False,
    )
    acm_certificate_arn: Optional[str] = Field(
        description="""ARN of ACM certificate to use for
        custom domain names. If provided,
        CDNs are created for all the APIs""",
        default=None,
    )
    stac_api_custom_domain: Optional[str] = Field(
        description="""Custom domain name for the STAC API.
        Must provide `acm_certificate_arn`""",
        default=None,
    )
    raster_api_custom_domain: Optional[str] = Field(
        description="""Custom domain name for the Raster API.
        Must provide `acm_certificate_arn`""",
        default=None,
    )
    vector_api_custom_domain: Optional[str] = Field(
        description="""Custom domain name for the Vector API.
        Must provide `acm_certificate_arn`""",
        default=None,
    )
    stac_ingestor_api_custom_domain: Optional[str] = Field(
        description="""Custom domain name for the STAC ingestor API.
        Must provide `acm_certificate_arn`""",
        default=None,
    )
    stac_browser_version: Optional[str] = Field(
        description="""Version of the Radiant Earth STAC browser to deploy.
        If none provided, no STAC browser will be deployed.
        If provided, `stac_api_custom_domain` must be provided
        as it will be used as a backend.""",
        default=None,
    )

    model_config = SettingsConfigDict(
        env_file=".env-cdk", yaml_file="config.yaml", extra="allow"
    )

    @field_validator("tags")
    def default_tags(cls, v, info: ValidationInfo):
        return v or {"project_id": info.data["project_id"], "stage": info.data["stage"]}

    @model_validator(mode="after")
    def validate_model(self) -> Self:
        if not self.public_db_subnet and (
            self.nat_gateway_count is not None and self.nat_gateway_count <= 0
        ):
            raise ValueError(
                """if the database and its associated services instances
                             are to be located in the private subnet of the VPC, NAT
                             gateways are needed to allow egress from the services
                             and therefore `nat_gateway_count` has to be > 0."""
            )

        if (
            self.stac_browser_version is not None
            and self.stac_api_custom_domain is None
        ):
            raise ValueError(
                """If a STAC browser version is provided,
                a custom domain must be provided for the STAC API"""
            )

        if self.acm_certificate_arn is None and any(
            [
                self.stac_api_custom_domain,
                self.raster_api_custom_domain,
                self.vector_api_custom_domain,
                self.stac_ingestor_api_custom_domain,
            ]
        ):
            raise ValueError(
                """If any custom domain is provided,
                an ACM certificate ARN must be provided"""
            )

        return self

    def build_service_name(self, service_id: str) -> str:
        return f"{self.project_id}-{self.stage}-{service_id}"

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: Type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> Tuple[PydanticBaseSettingsSource, ...]:
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            file_secret_settings,
            YamlConfigSettingsSource(settings_cls),
        )
