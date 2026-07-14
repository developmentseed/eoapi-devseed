"""test EOapi."""

from uuid import uuid4

import httpx

stac_endpoint = "http://0.0.0.0:8080/stac"
mock_oidc_endpoint = "http://127.0.0.1:8085"


def test_stac_api():
    """test stac."""
    # Ping
    assert httpx.get(f"{stac_endpoint}/_mgmt/ping").status_code == 200

    # viewer
    assert httpx.get(f"{stac_endpoint}/viewer").status_code == 200

    # Collections
    resp = httpx.get(f"{stac_endpoint}/collections")
    assert resp.status_code == 200
    collections = resp.json()["collections"]
    assert len(collections) > 0
    ids = [c["id"] for c in collections]
    assert "noaa-emergency-response" in ids

    # items
    resp = httpx.get(f"{stac_endpoint}/collections/noaa-emergency-response/items")
    assert resp.status_code == 200
    items = resp.json()["features"]
    assert len(items) == 10

    # item
    resp = httpx.get(
        f"{stac_endpoint}/collections/noaa-emergency-response/items/20200307aC0853300w361200"
    )
    assert resp.status_code == 200
    item = resp.json()
    assert item["id"] == "20200307aC0853300w361200"


def test_stac_write_auth():
    """Test that writes require a valid bearer token."""
    collection_id = f"auth-test-{uuid4()}"
    collection = {
        "type": "Collection",
        "stac_version": "1.0.0",
        "id": collection_id,
        "description": "Temporary collection for authentication testing",
        "license": "proprietary",
        "extent": {
            "spatial": {"bbox": [[-180, -90, 180, 90]]},
            "temporal": {"interval": [[None, None]]},
        },
        "links": [],
    }

    response = httpx.post(f"{stac_endpoint}/collections", json=collection)
    assert response.status_code in {401, 403}

    token_response = httpx.post(
        mock_oidc_endpoint,
        data={"username": "ci-user", "scopes": "openid profile"},
        headers={"Accept": "application/json"},
    )
    token_response.raise_for_status()
    headers = {"Authorization": f"Bearer {token_response.json()['token']}"}

    created = False
    try:
        response = httpx.post(
            f"{stac_endpoint}/collections",
            json=collection,
            headers=headers,
        )
        assert response.status_code == 201, response.text
        created = True
        assert (
            httpx.get(f"{stac_endpoint}/collections/{collection_id}").status_code == 200
        )
    finally:
        if created:
            response = httpx.delete(
                f"{stac_endpoint}/collections/{collection_id}",
                headers=headers,
            )
            assert response.is_success, response.text


def test_stac_to_raster():
    """test link to raster api."""
    # tilejson
    resp = httpx.get(
        f"{stac_endpoint}/collections/noaa-emergency-response/items/20200307aC0853300w361200/WebMercatorQuad/tilejson.json",
        params={"assets": "cog"},
    )
    assert resp.status_code == 307

    # viewer
    resp = httpx.get(
        f"{stac_endpoint}/collections/noaa-emergency-response/items/20200307aC0853300w361200/viewer",
        params={"assets": "cog"},
    )
    assert resp.status_code == 307
