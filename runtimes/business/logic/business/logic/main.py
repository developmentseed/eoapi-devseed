from contextlib import asynccontextmanager
from typing import Annotated, List, Union

from geojson_pydantic import Feature, FeatureCollection
from fastapi import Depends, FastAPI, HTTPException
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from business.logic import __version__ as version
from business.logic import models
from business.logic.session import get_session, engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    yield

    # shutdown


Session = Annotated[AsyncSession, Depends(get_session)]

app = FastAPI(
    title="Business Logic",
    version=version,
    lifespan=lifespan,
)


@app.post("/properties")
async def create_property(
    session: Session, geojson: Union[Feature, FeatureCollection]
) -> List[int]:
    if isinstance(geojson, Feature):
        geojson = FeatureCollection(
            type="FeatureCollection",
            features=[geojson],
        )

    ids = []
    for feature in geojson.features:
        property = models.Property(geometry=feature.geometry.wkt)
        session.add(property)
        await session.flush()
        ids.append(property.id)

    await session.commit()

    return ids


@app.get("/properties/{id}", response_model=models.Property)
async def get_property(session: Session, id: int):
    property = await session.get(models.Property, id)

    if not property:
        raise HTTPException(
            status_code=404, detail=f"No properties with id {id} found!"
        )

    return property
