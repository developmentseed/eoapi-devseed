#!/bin/sh
# Inject buildTileUrlTemplate into runtime-config.js when EOAPI_TILE_SERVER_BASE_URL is set.
# Runs after upstream 40-stac-browser-entrypoint.sh (SB_* env vars cannot carry functions).
set -e

config_file=/usr/share/nginx/html/runtime-config.js

if [ -z "${EOAPI_TILE_SERVER_BASE_URL}" ]; then
  exit 0
fi

base_url="${EOAPI_TILE_SERVER_BASE_URL%/}"

tmp_file="${config_file}.tmp"
head -n -1 "${config_file}" > "${tmp_file}"
cat >> "${tmp_file}" <<'EOF'
  buildTileUrlTemplate: ({ href, asset, key, stac }) => {
    const base = window.location.origin + "/raster";
    return (stac?.collection && stac?.id)
      ? base + "/collections/" + stac.collection + "/items/" + stac.id + "/tiles/WebMercatorQuad/{z}/{x}/{y}@1x?assets=" + key
      : base + "/external/tiles/WebMercatorQuad/{z}/{x}/{y}@2x?url=" +
        encodeURIComponent((asset?.href || href || "").startsWith("/vsi") ? asset.href : href);
  },
}
EOF
mv "${tmp_file}" "${config_file}"
