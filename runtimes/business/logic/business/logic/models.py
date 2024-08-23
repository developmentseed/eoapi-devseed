from typing import Optional
from geoalchemy2 import Geometry
from pydantic import BaseModel
from sqlmodel import Column, Field, SQLModel


class PropertyCreate(BaseModel):
    geometry: str = Field(
        default=None, sa_column=Column(Geometry("MULTIPOLYGON", srid=4326))
    )


class Property(PropertyCreate, SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
