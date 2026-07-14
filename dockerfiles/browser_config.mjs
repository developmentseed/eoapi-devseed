// Build-time config overlay for stac-browser (see SB_CONFIG in Dockerfile.browser).
// Options that require JavaScript functions must live here; everything else can be
// overridden at container startup via SB_* environment variables.
export default {
  useTileLayerAsFallback: true,
  buildTileUrlTemplate: ({ href, asset }) =>
    "http://127.0.0.1:8082/external/tiles/WebMercatorQuad/{z}/{x}/{y}@2x?url=" +
    encodeURIComponent(asset.href.startsWith("/vsi") ? asset.href : href),
};
