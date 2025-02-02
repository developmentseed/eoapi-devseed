
<p align="center">
  <img width="500" alt="eoapi-devseed" src="https://github.com/developmentseed/eoapi-devseed/assets/10407788/fc69e5ae-4ab7-491f-8c20-6b9e1372b4c6">
  <p align="center">Example of eoAPI customization.</p>
</p>

---

**Documentation**: <a href="https://eoapi.dev/customization/" target="_blank">https://eoapi.dev/customization/</a>

**Source Code**: <a href="https://github.com/developmentseed/eoapi-devseed" target="_blank">https://github.com/developmentseed/eoapi-devseed</a>

---

This repository shows an example of how users can customize and deploy their own version of eoAPI starting from [eoapi-template](https://github.com/developmentseed/eoapi-template).

## Custom

### Runtimes

#### eoapi.stac

Built on [stac-fastapi.pgstac](https://github.com/stac-utils/stac-fastapi-pgstac) application, adding a **`TiTilerExtension`** and a simple **`Search Viewer`**.

When the `EOAPI_STAC_TITILER_ENDPOINT` environment variable is set (pointing to the `raster` application) and `titiler` extension is enabled, additional endpoints will be added to the stac-fastapi application (see: [stac/extension.py](https://github.com/developmentseed/eoapi-devseed/blob/main/runtimes/eoapi/stac/eoapi/stac/extension.py)):

- `/collections/{collectionId}/items/{itemId}/tilejson.json`: Return the `raster` tilejson for an item
- `/collections/{collectionId}/items/{itemId}/viewer`: Redirect to the `raster` viewer

#### eoapi.raster

The dynamic tiler deployed within `eoapi-devseed` is built on top of [titiler-pgstac](https://github.com/stac-utils/titiler-pgstac) and [pgstac](https://github.com/stac-utils/pgstac). It enables large-scale mosaic based on the results of STAC search queries.

The service includes all the default endpoints from **titiler-pgstac** application and:

- `/`: a custom landing page with links to the different endpoints
- `/searches/builder`: a virtual mosaic builder UI that helps create and register STAC Search queries
- `/collections`: a secret (not in OpenAPI documentation) endpoint used in the mosaic-builder page
- `/collections/{collection_id}/items/{item_id}/viewer`: a simple STAC Item viewer

#### eoapi.vector

OGC Features and Tiles API built on top of [tipg](https://github.com/developmentseed/tipg).

The API will look for tables in the database's `public` schema by default. We've also added three functions that connect to the pgSTAC schema:

- **pg_temp.pgstac_collections_view**: Simple function which returns PgSTAC Collections
- **pg_temp.pgstac_hash**: Return features for a specific `searchId` (hash)
- **pg_temp.pgstac_hash_count**: Return the number of items per geometry for a specific `searchId` (hash)

### Infrastructure

The CDK code is almost similar to the one found in [eoapi-template](https://github.com/developmentseed/eoapi-template). We just added some configurations for our custom runtimes.

### Local testing

Before deploying the application on the cloud, you can start by exploring it with a local *Docker* deployment

```
docker compose up
```

Once the applications are *up*, you'll need to add STAC **Collections** and **Items** to the PgSTAC database. If you don't have, you can use the follow the [MAXAR open data demo](https://github.com/vincentsarago/MAXAR_opendata_to_pgstac) (or get inspired by the other [demos](https://github.com/developmentseed/eoAPI/tree/main/demo)).

Then you can start exploring your dataset with:

- the STAC Metadata service [http://localhost:8081](http://localhost:8081)
- the Raster service [http://localhost:8082](http://localhost:8082)
- the browser UI [http://localhost:8085](http://localhost:8085)

If you've added a vector dataset to the `public` schema in the Postgres database, they will be available through the **Vector** service at [http://localhost:8083](http://localhost:8083).

## Deployment

### Requirements

- python >=3.9
- docker
- node >=14
- AWS credentials environment variables configured to point to an account.
- **Optional** a `config.yaml` file to override the default deployment settings defined in `config.py`.

### Installation

Install python dependencies with

```
uv sync --group deploy
```

And node dependencies with

```
uv run npm install
```

Verify that the `cdk` CLI is available. Since `aws-cdk` is installed as a local dependency, you can use the `npx` node package runner tool, that comes with `npm`.

```
uv run npx cdk --version
```

First, synthesize the app

```
uv run npx cdk synth --all
```

Then, deploy

```
uv run npx cdk deploy --all --require-approval never
```
