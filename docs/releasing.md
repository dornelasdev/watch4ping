# Release Checklist

This checklist matches the project's package version and short-tag convention:
package `0.9.0` corresponds to Git tag `v0.9`.

## Prepare

1. Update `src/watch4ping/_version.py` with the release version.
2. Move the release notes into a dated section in `CHANGELOG.md`.
3. Confirm the README and schema notes match the implemented behavior.
4. Ensure `dist/` does not contain artifacts from an older version.

## Verify

Run from an activated development environment:

```bash
python -m pip install -e ".[dev]"
pytest
python -m build
python -m twine check dist/*
```

Install the wheel in a separate temporary environment:

```bash
PACKAGE_TEST_ENV="$(mktemp -d)/venv"
python -m venv "$PACKAGE_TEST_ENV"
"$PACKAGE_TEST_ENV/bin/python" -m pip install dist/watch4ping-0.9.0-py3-none-any.whl
(cd /tmp && "$PACKAGE_TEST_ENV/bin/watch4ping" --version)
```

Confirm the command reports the intended package version.

## Publish Repository Release

1. Commit the release changes using the established version-oriented message.
2. Push `main` and wait for every GitHub Actions test and packaging job to pass.
3. Create the short release tag, for example `git tag v0.9`.
4. Push the tag, for example `git push origin v0.9`.
5. Create a GitHub Release from that tag and use the matching changelog section
   as its notes.
6. Attach the wheel and source distribution if distributing binaries through
   GitHub Releases.

Publishing to a package index is intentionally separate from this checklist and
should only be added when the project is ready for public package distribution.
