# Releasing

This is a checklist for releasing a new version of **eoapi-devsee**.

1. Make sure the [Changelog](CHANGES.md) is up to date with latest changes and release date set

2. Run [`bump-my-version`](https://callowayproject.github.io/bump-my-version/) to update all eoapi's module versions: `uv run bump-my-version bump minor --new-version 0.4.0`

3. Push your change and tag `git push origin main --tags`

4. Create a [new release](https://github.com/developmentseed/eoapi-devseed/releases/new) targeting the new tag, and use the "Generate release notes" feature to populate the description. Publish the release and mark it as the latest

5. The `release` will trigger a new deployement
