# Releasing

Releases are automated with [release-please](https://github.com/googleapis/release-please), using the same `DS_RELEASE_BOT_*` GitHub App secrets as [eoapi-k8s](https://github.com/developmentseed/eoapi-k8s).

## How it works

1. Merge pull requests to `main` using [Conventional Commits](https://www.conventionalcommits.org/):
   - `feat:` for new features (minor bump)
   - `fix:` for bug fixes (patch bump)
   - `feat!:` or `BREAKING CHANGE:` for breaking changes (major bump)

2. Release Please opens a release PR that updates:
   - `CHANGELOG.md`
   - `pyproject.toml`
   - runtime `__version__` strings in `runtimes/eoapi/*/eoapi/*/__init__.py`

3. Merge the release PR. Release Please tags the release (for example `0.4.0`) and publishes a GitHub release.

4. The tag push triggers [CI](.github/workflows/ci.yml). After tests pass and version consistency checks succeed, the `publish-containers` job builds and pushes the local Docker Compose images to `ghcr.io/developmentseed/eoapi-devseed/{stac,raster,vector,stac-browser}` tagged with the release version and `latest`. Images that already exist in the registry are skipped.

5. The same CI run also triggers the `deploy` job for the AWS dev stack.

## Manual overrides

- To release a specific version, add `Release-As: x.y.z` to a commit message on `main`.
- To deploy without a release, use the `workflow_dispatch` trigger on the CI workflow.
- To republish container images for an existing release tag without moving `latest`, use the `workflow_dispatch` trigger on [Publish containers](.github/workflows/publish-containers.yml).

## Container registry

Published images are private by default in GitHub Packages. To make them public, change package visibility under **Settings → Packages** for each image.
