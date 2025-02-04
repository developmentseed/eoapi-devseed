"""AWS Lambda handler."""

import asyncio
import logging
import os

from eoapi.raster.app import app
from eoapi.raster.config import ApiSettings
from mangum import Mangum
from titiler.pgstac.db import connect_to_db

logging.getLogger("mangum.lifespan").setLevel(logging.ERROR)
logging.getLogger("mangum.http").setLevel(logging.ERROR)

settings = ApiSettings()


@app.on_event("startup")
async def startup_event() -> None:
    """Connect to database on startup."""
    await connect_to_db(
        app,
        settings=settings.load_postgres_settings(),
    )


handler = Mangum(app, lifespan="off")

if "AWS_EXECUTION_ENV" in os.environ:
    loop = asyncio.get_event_loop()
    loop.run_until_complete(app.router.startup())
