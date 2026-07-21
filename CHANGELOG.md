# Release Notes

All notable changes to this project will be documented in this file.

## [0.5.0](https://github.com/developmentseed/eoapi-devseed/compare/0.4.0...0.5.0) (2026-07-21)


### Added

* added landing page. ([57373dd](https://github.com/developmentseed/eoapi-devseed/commit/57373dd5c0be6583eeab85d05cfcd535a0d6d104))


### Fixed

* aws deployment. ([8661745](https://github.com/developmentseed/eoapi-devseed/commit/8661745f9f48ef2c19e867ebe302e6cc888e9c0c))


### Maintenance

* **ci:** deploy docker-compose. ([#72](https://github.com/developmentseed/eoapi-devseed/issues/72)) ([4ea08f5](https://github.com/developmentseed/eoapi-devseed/commit/4ea08f5b88e08b7dd68293721e645e333b0a45ba))
* **ci:** ingest data for hetzner deploy. ([73cd5d5](https://github.com/developmentseed/eoapi-devseed/commit/73cd5d5d6ab1ee5fe989f5b6d676eda5d6efc006))
* **ci:** ingest data for hetzner deploy. ([fcfc5a3](https://github.com/developmentseed/eoapi-devseed/commit/fcfc5a36232d0fe4ce484d86398ca50a1c5d19fd))
* **deps:** bump aws-cdk from 2.1131.0 to 2.1132.0 ([#74](https://github.com/developmentseed/eoapi-devseed/issues/74)) ([6fefacd](https://github.com/developmentseed/eoapi-devseed/commit/6fefacdccea8a2b21df5109a0cc58285c381401f))
* **deps:** bump the github-actions group with 4 updates ([#75](https://github.com/developmentseed/eoapi-devseed/issues/75)) ([52aece4](https://github.com/developmentseed/eoapi-devseed/commit/52aece4fcf80c236b3c1c3ef2ce6d2d6af3a5263))
* improve some wording on landing page. ([ce0e71e](https://github.com/developmentseed/eoapi-devseed/commit/ce0e71e95a52c18ef36d610d43c89446b6fd92dc))

## [0.4.0](https://github.com/developmentseed/eoapi-devseed/compare/0.3.4...0.4.0) (2026-07-14)


### Added

* added stac transactions with stac-auth-proxy. ([80fb41a](https://github.com/developmentseed/eoapi-devseed/commit/80fb41abd8707733feabb90e9361de80b686b7bd))


### Fixed

* publication of containers. ([fc4a571](https://github.com/developmentseed/eoapi-devseed/commit/fc4a5714efea7a15298ac4778bc79c49fadcc022))
* stac viewer and raster mosaik builder. ([c9b455a](https://github.com/developmentseed/eoapi-devseed/commit/c9b455ad6017ffe314185a56e8ee5b237643fe5c))
* tile preview in stac browser. ([8a899c3](https://github.com/developmentseed/eoapi-devseed/commit/8a899c347187826313de0c93b4e1b3d10b4a4d78))


### Maintenance

* use conventional semver for release-please ([ba28065](https://github.com/developmentseed/eoapi-devseed/commit/ba2806547c84ab5e9e9a12cb6873fefaaedcdb04))

## [0.3.4](https://github.com/developmentseed/eoapi-devseed/compare/0.3.3...0.3.4) (2026-07-14)


### Added

* added traefik reverse proxy. ([#65](https://github.com/developmentseed/eoapi-devseed/issues/65)) ([2c86c02](https://github.com/developmentseed/eoapi-devseed/commit/2c86c021c25405484cd2574e307beb971d8674f1))
* rely on release-please for release management. ([#66](https://github.com/developmentseed/eoapi-devseed/issues/66)) ([4eccc05](https://github.com/developmentseed/eoapi-devseed/commit/4eccc05aae0518497286ebe9d96e13b846fbe4e3))
* swagger-ui landing pages for apis. ([73a2631](https://github.com/developmentseed/eoapi-devseed/commit/73a2631a6ae97afdaf4d29d664af58d1ada32060))


### Fixed

* dependency version mismatch. ([8fbf1ce](https://github.com/developmentseed/eoapi-devseed/commit/8fbf1ceec72aa83f244164c89377c1ee5710e94c))
* upstream stac browser adjustments. ([2171b75](https://github.com/developmentseed/eoapi-devseed/commit/2171b755931f9ddc17dd8a7535b37847b85015f2))


### Maintenance

* add Docker Compose to dependabot. ([b8bbbed](https://github.com/developmentseed/eoapi-devseed/commit/b8bbbeda0cdff1c5d06400504ef919317ef413b6))
* adjust release-please sections. ([cd31ea3](https://github.com/developmentseed/eoapi-devseed/commit/cd31ea3815955d41862bb5bfc489cad93cd3c8b2))
* **ci:** Added dependabot. ([5fa03b0](https://github.com/developmentseed/eoapi-devseed/commit/5fa03b02518a6fbc47945bad51ee5eb612de417f))
* **deps:** bump aws-cdk from 2.1130.0 to 2.1131.0 ([#68](https://github.com/developmentseed/eoapi-devseed/issues/68)) ([d0c80d7](https://github.com/developmentseed/eoapi-devseed/commit/d0c80d72865891dd1f6bef726b53149d17b00350))
* **deps:** bump stac-utils/pgstac from v0.9.9 to v0.9.11 ([#69](https://github.com/developmentseed/eoapi-devseed/issues/69)) ([3ced714](https://github.com/developmentseed/eoapi-devseed/commit/3ced71419d02a2e63f0603539874967e0e68c830))
* **deps:** bump titiler-extensions ([#61](https://github.com/developmentseed/eoapi-devseed/issues/61)) ([77d1fb1](https://github.com/developmentseed/eoapi-devseed/commit/77d1fb1436de00237bf437a8417b1604e896540c))
* publish containers. ([59063d7](https://github.com/developmentseed/eoapi-devseed/commit/59063d78a92ddfedbcd52b26da7183d1b33603d9))


### Other

* pin GitHub Actions to SHA digests ([#58](https://github.com/developmentseed/eoapi-devseed/issues/58)) ([46ab703](https://github.com/developmentseed/eoapi-devseed/commit/46ab70341832a3be0631b97fdceb9634834c3cc1))

## [unreleased]

## [0.3.3] - 2026-1-23

* update pgstac to 0.9.9
* update eoapi-cdk version to `10.4.2`

## [0.3.2] - 2025-10-30

* enable SnapStart on lambda functions 

## [0.3.1] - 2025-09-26

* fix titiler tilejson endpoints 

## [0.3.0] - 2025-09-25

* update eoapi-cdk version to `10.2.5`

## [0.2.0] - 2025-09-24

* update pgstac to 0.9.8
* update eoapi.raster to use titiler-pgstac==1.9.0
    * add `/conformance` for eoapi-raster endpoints 
* update eoapi.vector to use tipg==1.2.1
* update eoapi.stac to use stac_fastapi.pgstac>=6.0,<7.0
* align HTML template styles
* update lambda handlers to python 3.12

## [0.1.0] - 2025-09-24

* first tagged release

[unreleased]: https://github.com/developmentseed/eoapi-devseed/compare/0.3.2...HEAD
[0.3.2]: https://github.com/developmentseed/eoapi-devseed/compare/0.3.1...0.3.2
[0.3.1]: https://github.com/developmentseed/eoapi-devseed/compare/0.3.0...0.3.1
[0.3.0]: https://github.com/developmentseed/eoapi-devseed/compare/0.2.0...0.3.0
[0.2.0]: https://github.com/developmentseed/eoapi-devseed/compare/0.1.0...0.2.0
[0.1.0]: https://github.com/developmentseed/eoapi-devseed/compare/49ec34d33b6d21bfb51cf37bfa167ffcb5f09938...0.1.0
