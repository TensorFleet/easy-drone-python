# Release Guide for easy-drone

This guide explains how to publish the easy-drone package to PyPI using GitHub Actions.

## Prerequisites

### 1. PyPI Account Setup

1. Create accounts on:
   - [PyPI](https://pypi.org/account/register/) (for production releases)
   - [Test PyPI](https://test.pypi.org/account/register/) (for testing)

2. Create API tokens:
   - **PyPI**: Go to [Account Settings → API Tokens](https://pypi.org/manage/account/token/)
   - **Test PyPI**: Go to [Account Settings → API Tokens](https://test.pypi.org/manage/account/token/)
   - Create a token with "Upload packages" scope
   - Save the tokens securely (they're only shown once!)

### 2. GitHub Secrets Setup

Add the following secrets to your GitHub repository:

1. Go to your repository → Settings → Secrets and variables → Actions
2. Add two secrets:
   - `PYPI_API_TOKEN`: Your PyPI API token
   - `TEST_PYPI_API_TOKEN`: Your Test PyPI API token

**How to add:**
- Click "New repository secret"
- Name: `PYPI_API_TOKEN`
- Value: `pypi-...` (your full token starting with `pypi-`)
- Click "Add secret"

## Workflows

The project includes three GitHub Actions workflows:

### 1. Test Workflow (`test.yml`)
**Trigger**: Push or PR to main/master/develop branches

**What it does**:
- Tests installation on Ubuntu, macOS, and Windows
- Tests Python versions 3.8, 3.9, 3.10, 3.11, 3.12
- Verifies imports work correctly
- Runs verification script
- Builds package and checks it with twine

### 2. Lint Workflow (`lint.yml`)
**Trigger**: Push or PR to main/master/develop branches

**What it does**:
- Checks code formatting with black
- Checks import sorting with isort
- Runs flake8 linting
- All checks continue on error (non-blocking)

### 3. Publish Workflow (`publish.yml`)
**Trigger**: 
- Automatically on GitHub Release
- Manually via workflow_dispatch

**What it does**:
- Builds the package (wheel and source distribution)
- Checks package with twine
- Publishes to PyPI or Test PyPI

## Release Process

### Option 1: Automatic Release (Recommended)

#### Step 1: Update Version
Edit `setup.py` and `pyproject.toml`:
```python
version="0.1.1"  # Increment version
```

#### Step 2: Commit and Push
```bash
git add setup.py pyproject.toml
git commit -m "Bump version to 0.1.1"
git push origin main
```

#### Step 3: Create GitHub Release
1. Go to your repository → Releases → "Draft a new release"
2. Click "Choose a tag" → Type new tag (e.g., `v0.1.1`) → "Create new tag"
3. Release title: `v0.1.1` or `Release 0.1.1`
4. Description: List changes, new features, bug fixes
5. Click "Publish release"

**The workflow will automatically**:
- Build the package
- Publish to PyPI
- Make it available via `pip install easy-drone`

### Option 2: Manual Testing with Test PyPI

Use this to test the release process before publishing to production PyPI.

#### Step 1: Manual Workflow Trigger
1. Go to Actions → "Publish to PyPI" workflow
2. Click "Run workflow"
3. Select branch (usually `main`)
4. Choose "testpypi" from dropdown
5. Click "Run workflow"

#### Step 2: Test Installation
```bash
# Install from Test PyPI
pip install --index-url https://test.pypi.org/simple/ \
    --extra-index-url https://pypi.org/simple/ \
    easy-drone

# Test it works
python -c "from gz_transport import Node; print('Success!')"
```

#### Step 3: If successful, publish to PyPI
1. Run workflow again
2. Choose "pypi" from dropdown
3. Or create a GitHub Release (automatic)

## Version Numbering

Follow [Semantic Versioning](https://semver.org/):
- `MAJOR.MINOR.PATCH` (e.g., `1.2.3`)
- **MAJOR**: Incompatible API changes
- **MINOR**: New features, backward compatible
- **PATCH**: Bug fixes, backward compatible

Examples:
- `0.1.0` → `0.1.1`: Bug fix
- `0.1.0` → `0.2.0`: New feature
- `0.9.0` → `1.0.0`: First stable release

## Checklist Before Release

- [ ] Version updated in `setup.py` and `pyproject.toml`
- [ ] `CHANGES.md` or changelog updated
- [ ] All tests passing (check Actions tab)
- [ ] Documentation updated if needed
- [ ] Committed and pushed to main branch
- [ ] Created GitHub release with tag

## Common Issues

### Issue: "Invalid or expired token"
**Solution**: Generate a new API token on PyPI and update GitHub secret

### Issue: "File already exists"
**Solution**: You've already published this version. Increment version number.

### Issue: "Workflow fails to publish"
**Solution**: 
- Check GitHub Actions logs
- Verify secrets are set correctly
- Ensure version in setup.py matches tag (without 'v' prefix)

### Issue: "Package not found after publishing"
**Solution**: 
- Wait 5-10 minutes for PyPI to index
- Check [https://pypi.org/project/easy-drone/](https://pypi.org/project/easy-drone/)

## After Publishing

### Update Installation Instructions
Users can now install with:
```bash
pip install easy-drone

# With optional features
pip install easy-drone[zenoh]
pip install easy-drone[yolo]
pip install easy-drone[all]
```

### Announce Release
- Update README badges (if any)
- Post announcement (social media, forums, etc.)
- Notify users of changes

## Workflow Files

The workflows are located in `.github/workflows/`:
- `publish.yml` - Publishing to PyPI
- `test.yml` - Testing and verification
- `lint.yml` - Code quality checks

## Security Notes

- **Never** commit API tokens to the repository
- Use GitHub Secrets for all sensitive data
- Tokens should have minimal required permissions
- Rotate tokens periodically
- Use trusted publishing when possible (PyPI supports this)

## Trusted Publishing (Advanced)

For even more security, you can set up [Trusted Publishing](https://docs.pypi.org/trusted-publishers/) which doesn't require API tokens. The workflow already supports this with the `id-token: write` permission.

## Support

For issues with:
- **GitHub Actions**: Check the Actions tab for logs
- **PyPI Publishing**: See [PyPI Help](https://pypi.org/help/)
- **Package Issues**: Open an issue on GitHub

---

**Happy Releasing!** 🚀

