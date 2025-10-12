# GitHub Workflows Summary

This document provides an overview of all GitHub Actions workflows configured for the easy-drone project.

## Workflows Overview

| Workflow | Trigger | Purpose | Status |
|----------|---------|---------|--------|
| **Test** | Push/PR to main | Run tests across platforms | Required |
| **Lint** | Push/PR to main | Code quality checks | Optional |
| **Publish** | Release or Manual | Publish to PyPI | Manual/Release |
| **Release Drafter** | Push to main | Auto-generate release notes | Automatic |

## 1. Test Workflow (`test.yml`)

### Purpose
Ensures the package installs and works correctly across different platforms and Python versions.

### Triggers
- Push to `main`, `master`, or `develop` branches
- Pull requests to these branches
- Manual trigger via workflow_dispatch

### What it does
**Test Job:**
- Runs on Ubuntu, macOS, and Windows
- Tests Python 3.8, 3.9, 3.10, 3.11, 3.12
- Installs the package
- Verifies imports work
- Runs verification script

**Build Job:**
- Builds the package (wheel + source dist)
- Checks package with twine
- Uploads build artifacts for 7 days

### Matrix Strategy
```yaml
os: [ubuntu-latest, macos-latest, windows-latest]
python-version: ['3.8', '3.9', '3.10', '3.11', '3.12']
```

Some combinations are excluded to reduce CI time.

## 2. Lint Workflow (`lint.yml`)

### Purpose
Maintains code quality and consistent formatting.

### Triggers
- Push to `main`, `master`, or `develop` branches
- Pull requests to these branches
- Manual trigger via workflow_dispatch

### What it does
- **Black**: Checks code formatting (continues on error)
- **isort**: Checks import sorting (continues on error)
- **flake8**: Lints code for syntax errors and style issues

All checks are non-blocking (continue-on-error: true) to avoid breaking builds on style issues.

### Customization
Edit lint settings in:
- `pyproject.toml` for black/isort config
- `.flake8` file (create if needed) for flake8 config

## 3. Publish Workflow (`publish.yml`)

### Purpose
Builds and publishes the package to PyPI or Test PyPI.

### Triggers
1. **Automatic**: When a GitHub Release is published
2. **Manual**: Via workflow_dispatch with choice of PyPI or Test PyPI

### What it does
1. Checks out the repository
2. Sets up Python 3.11
3. Installs build tools (build, twine)
4. Builds the package
5. Checks package integrity with twine
6. Publishes to selected destination

### Required Secrets
- `PYPI_API_TOKEN`: For publishing to PyPI
- `TEST_PYPI_API_TOKEN`: For publishing to Test PyPI

### Usage Scenarios

**Scenario 1: Test Release**
```
1. Go to Actions → "Publish to PyPI"
2. Click "Run workflow"
3. Select "testpypi"
4. Click "Run workflow"
```

**Scenario 2: Production Release**
```
1. Create a GitHub Release
2. Workflow runs automatically
3. Package published to PyPI
```

**Scenario 3: Manual Production**
```
1. Go to Actions → "Publish to PyPI"
2. Click "Run workflow"
3. Select "pypi"
4. Click "Run workflow"
```

## 4. Release Drafter Workflow (`release-drafter.yml`)

### Purpose
Automatically generates and maintains draft release notes from merged pull requests.

### Triggers
- Push to `main` or `master` branches
- Pull request events (opened, reopened, synchronize)

### What it does
- Categorizes changes by labels:
  - 🚀 Features (feature, enhancement)
  - 🐛 Bug Fixes (fix, bugfix, bug)
  - 📚 Documentation (documentation, docs)
  - 🧰 Maintenance (chore, maintenance)
- Auto-increments version based on labels
- Generates draft release notes

### Configuration
Configured in `.github/release-drafter.yml`

### Version Resolution
- `major` label → Increments major version (1.0.0 → 2.0.0)
- `minor` or `feature` label → Increments minor version (1.0.0 → 1.1.0)
- `patch` or `fix` label → Increments patch version (1.0.0 → 1.0.1)

## Setting Up

### 1. PyPI Tokens

**Get tokens:**
1. Go to [PyPI Account Settings](https://pypi.org/manage/account/token/)
2. Create "Upload packages" token
3. Save the token (shown only once!)
4. Repeat for [Test PyPI](https://test.pypi.org/manage/account/token/)

**Add to GitHub:**
1. Repository → Settings → Secrets and variables → Actions
2. New repository secret:
   - Name: `PYPI_API_TOKEN`
   - Value: Your PyPI token
3. Repeat for `TEST_PYPI_API_TOKEN`

### 2. Branch Protection (Optional)

Recommended settings for `main` branch:
- Require status checks to pass (Test workflow)
- Require pull request reviews
- Enable automatic deletion of head branches

### 3. PR Labels (Optional)

Add these labels to your repository for Release Drafter:
- `feature`, `enhancement` → 🚀 Features
- `fix`, `bugfix`, `bug` → 🐛 Bug Fixes
- `documentation`, `docs` → 📚 Documentation
- `chore`, `maintenance` → 🧰 Maintenance
- `major`, `minor`, `patch` → Version control

## Workflow Files

```
.github/
├── workflows/
│   ├── test.yml           # Testing across platforms
│   ├── lint.yml           # Code quality checks
│   ├── publish.yml        # PyPI publishing
│   └── release-drafter.yml # Release notes automation
├── release-drafter.yml    # Release drafter config
└── RELEASE_GUIDE.md       # Detailed release guide
```

## Monitoring Workflows

### View Workflow Runs
1. Go to repository → Actions tab
2. Select workflow from left sidebar
3. View run history and logs

### Troubleshooting Failed Runs
1. Click on failed run
2. Expand failed job
3. Review logs for errors
4. Common issues:
   - Missing secrets
   - Version conflicts
   - Network timeouts
   - Import errors

## Best Practices

### For Contributors
1. **Always create PRs** instead of pushing directly
2. **Add appropriate labels** to PRs for Release Drafter
3. **Wait for tests** to pass before merging
4. **Follow commit conventions** for clear history

### For Maintainers
1. **Review draft releases** before publishing
2. **Test on Test PyPI** before production release
3. **Update version numbers** in sync with releases
4. **Monitor workflow runs** regularly
5. **Keep secrets updated** and secure

## Security

### Secrets Management
- ✅ Use GitHub Secrets for all tokens
- ✅ Never commit tokens to repository
- ✅ Rotate tokens periodically
- ✅ Use minimal required permissions

### Workflow Permissions
All workflows use minimal required permissions:
- `contents: read` - Read repository files
- `contents: write` - Create releases (Release Drafter only)
- `id-token: write` - Trusted publishing to PyPI

## Customization

### Adding New Tests
Edit `test.yml`:
```yaml
- name: Run custom tests
  run: pytest tests/
```

### Changing Python Versions
Edit matrix in `test.yml`:
```yaml
python-version: ['3.9', '3.10', '3.11', '3.12']
```

### Additional Linters
Edit `lint.yml`:
```yaml
- name: Run pylint
  run: pylint gz_transport
```

## Status Badges

Add to README.md:

```markdown
![Tests](https://github.com/TensorFleet/easy-drone-python/workflows/Tests/badge.svg)
![Linting](https://github.com/TensorFleet/easy-drone-python/workflows/Linting/badge.svg)
![PyPI](https://img.shields.io/pypi/v/easy-drone)
![Python](https://img.shields.io/pypi/pyversions/easy-drone)
```

## Support

For issues with workflows:
1. Check workflow logs in Actions tab
2. Review [GitHub Actions Documentation](https://docs.github.com/en/actions)
3. Check [PyPI Publishing Guide](https://packaging.python.org/guides/publishing-package-distribution-releases-using-github-actions-ci-cd-workflows/)
4. Open an issue with workflow logs attached

---

**Automated Excellence!** 🤖✨

