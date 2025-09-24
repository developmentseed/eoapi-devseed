"""AWS Lambda handler."""

import asyncio
import logging
import os

from eoapi.stac.app import app
from eoapi.stac.config import PostgresSettings, Settings
from mangum import Mangum
from stac_fastapi.pgstac.db import connect_to_db

logging.getLogger("mangum.lifespan").setLevel(logging.ERROR)
logging.getLogger("mangum.http").setLevel(logging.ERROR)

settings = Settings()


@app.on_event("startup")
async def startup_event() -> None:
    """Connect to database on startup."""
    await connect_to_db(
        app,
        postgres_settings=PostgresSettings(),
        add_write_connection_pool=settings.enable_transaction,
    )


handler = Mangum(app, lifespan="off")

if "AWS_EXECUTION_ENV" in os.environ:
    loop = asyncio.get_event_loop()
    loop.run_until_complete(app.router.startup())
