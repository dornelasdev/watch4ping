# Release Checklist

This checklist matches the project's package version and short-tag convention:
package `1.0.0` corresponds to Git tag `v1.0`.

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
python scripts/verify_release.py
```

Install the wheel in a separate temporary environment:

```bash
PACKAGE_TEST_ENV="$(mktemp -d)/venv"
python -m venv "$PACKAGE_TEST_ENV"
"$PACKAGE_TEST_ENV/bin/python" -m pip install dist/watch4ping-1.0.0-py3-none-any.whl
(cd /tmp && "$PACKAGE_TEST_ENV/bin/watch4ping" --version)
```

Confirm the command reports the intended package version.

## Manual Smoke Test

Run the installed wheel through the primary user flows. These commands keep the
generated reports in a temporary directory:

```bash
WATCH4PING="$PACKAGE_TEST_ENV/bin/watch4ping"
RELEASE_REPORT_DIR="$(mktemp -d)"

"$WATCH4PING" doctor --config watch4ping.toml --output-dir "$RELEASE_REPORT_DIR"
"$WATCH4PING" config validate --config watch4ping.toml
"$WATCH4PING" -t cloudflare=1.1.1.1 --duration 3s --format all --quiet \
  --output-dir "$RELEASE_REPORT_DIR"
"$WATCH4PING" -t cloudflare=1.1.1.1 --duration 3s --format html --quiet \
  --output-dir "$RELEASE_REPORT_DIR"
"$WATCH4PING" history --output-dir "$RELEASE_REPORT_DIR"
"$WATCH4PING" compare --output-dir "$RELEASE_REPORT_DIR"
"$WATCH4PING" cleanup --dry-run --keep 1 --output-dir "$RELEASE_REPORT_DIR"
```

Exercise alert exit behavior separately:

```bash
"$WATCH4PING" -t cloudflare=1.1.1.1 --duration 3s --alert-loss 0.1 \
  --alert-latency 0.1 --fail-on-alert --no-report --quiet
echo $?
```

A responding target should exceed the deliberately tiny latency threshold; a
nonresponding target should exceed the loss threshold. The expected exit code is
`1` in either case.

Finally, open the dashboard and inspect both generated sessions and one HTML
report, then stop it with `Ctrl-C`:

```bash
"$WATCH4PING" dashboard --output-dir "$RELEASE_REPORT_DIR" --port 8876 --open
```

Confirm the dashboard lists two sessions, comparison works, and the HTML report
opens without missing content.

After stopping the dashboard, verify actual retention cleanup in the temporary
directory:

```bash
"$WATCH4PING" cleanup --keep 1 --output-dir "$RELEASE_REPORT_DIR"
"$WATCH4PING" history --output-dir "$RELEASE_REPORT_DIR"
```

The final history should contain one session.

## Publish Repository Release

1. Commit the release changes using the established version-oriented message.
2. Push `main` and wait for every GitHub Actions test and packaging job to pass.
3. Create an annotated release tag, for example
   `git tag -a v1.0 -m "watch4ping v1.0"`.
4. Push the tag, for example `git push origin v1.0`.
5. Create a GitHub Release from that tag and use the matching changelog section
   as its notes.
6. Attach the wheel and source distribution if distributing binaries through
   GitHub Releases.

Publishing to a package index is intentionally separate from this checklist and
should only be added when the project is ready for public package distribution.
