"""AWS Lambda handler."""

import asyncio
import logging
import os

from eoapi.stac.app import app
from eoapi.stac.config import PostgresSettings, Settings
from mangum import Mangum
from snapshot_restore_py import register_after_restore, register_before_snapshot
from stac_fastapi.pgstac.db import connect_to_db

logging.getLogger("mangum.lifespan").setLevel(logging.ERROR)
logging.getLogger("mangum.http").setLevel(logging.ERROR)

settings = Settings()
postgres_settings = PostgresSettings()

_connection_initialized = False


@register_before_snapshot
def on_snapshot():
    """
    Runtime hook called by Lambda before taking a snapshot.
    We close database connections that shouldn't be in the snapshot.
    """

    if hasattr(app, "state") and hasattr(app.state, "readpool") and app.state.readpool:
        try:
            app.state.readpool.close()
            app.state.readpool = None
        except Exception as e:
            print(f"SnapStart: Error closing database readpool: {e}")

    if (
        hasattr(app, "state")
        and hasattr(app.state, "writepool")
        and app.state.writepool
    ):
        try:
            app.state.writepool.close()
            app.state.writepool = None
        except Exception as e:
            print(f"SnapStart: Error closing database writepool: {e}")

    return {"statusCode": 200}


@register_after_restore
def on_snap_restore():
    """
    Runtime hook called by Lambda after restoring from a snapshot.
    We recreate database connections that were closed before the snapshot.
    """
    global _connection_initialized

    try:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        if hasattr(app.state, "readpool") and app.state.readpool:
            try:
                app.state.readpool.close()
            except Exception as e:
                print(f"SnapStart: Error closing stale readpool: {e}")
            app.state.readpool = None

        if hasattr(app.state, "writepool") and app.state.writepool:
            try:
                app.state.writepool.close()
            except Exception as e:
                print(f"SnapStart: Error closing stale writepool: {e}")
            app.state.writepool = None

        loop.run_until_complete(
            connect_to_db(
                app,
                postgres_settings=postgres_settings,
                add_write_connection_pool=settings.enable_transaction,
            )
        )

        _connection_initialized = True

    except Exception as e:
        print(f"SnapStart: Failed to initialize database connection: {e}")
        raise

    return {"statusCode": 200}


@app.on_event("startup")
async def startup_event() -> None:
    """Connect to database on startup."""
    await connect_to_db(
        app,
        postgres_settings=postgres_settings,
        add_write_connection_pool=settings.enable_transaction,
    )


handler = Mangum(app, lifespan="off")

if "AWS_EXECUTION_ENV" in os.environ:
    loop = asyncio.get_event_loop()
    loop.run_until_complete(app.router.startup())
