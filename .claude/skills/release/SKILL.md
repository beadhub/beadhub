---
name: release
description: Prepare a beadhub release for PyPI. Runs quality gates, bumps version, builds, verifies, commits, and pushes.
argument-hint: [version]
allowed-tools: Bash(uv run *), Bash(uv build *), Bash(git *), Bash(unzip *), Bash(ls *), Bash(rm -rf dist/*)
---

# Release beadhub to PyPI

## Steps

1. **Determine version.** If `$ARGUMENTS` is provided, use it. Otherwise read the current version from `pyproject.toml` and ask what the new version should be.

2. **Verify clean state:**
   ```bash
   git status
   git log origin/main..HEAD --oneline
   ```
   Working tree must be clean and up to date with origin. If there are unpushed commits, show them and ask whether to proceed.

3. **Run quality gates** (all must pass):
   ```bash
   uv run black src/ tests/
   uv run isort src/ tests/
   uv run ruff check src/ tests/
   uv run mypy
   uv run pytest --tb=short -q
   ```

4. **Bump version** in `pyproject.toml` to the target version.

5. **Clean old artifacts and build:**
   ```bash
   rm -rf dist/
   uv build
   ```

6. **Verify the package:**
   - Check that `dist/` contains exactly one `.tar.gz` and one `.whl`, both with the correct version in the filename.
   - List the wheel contents and verify the package looks right:
     ```bash
     unzip -l dist/beadhub-<VERSION>-py3-none-any.whl
     ```
   - Confirm no unexpected files (credentials, .env files, large binaries) are included.
   - Report the artifact filenames and sizes to the user.

7. **Commit and push:**
   ```bash
   git add pyproject.toml uv.lock
   git commit -m "release: Bump version to <VERSION>"
   git push
   ```

8. **Report ready.** Tell the user the build artifacts in `dist/` are verified and ready. They can publish with `uv publish`.

## Version Format

`MAJOR.MINOR.PATCH` (no `v` prefix — this is a Python package, not a git tag).
