# GitHub Actions Setup Checklist

Quick checklist to get your GitHub workflows up and running.

## ✅ Immediate Setup (Required for Publishing)

### 1. Create PyPI Accounts
- [ ] Sign up at [PyPI.org](https://pypi.org/account/register/)
- [ ] Sign up at [Test PyPI](https://test.pypi.org/account/register/)
- [ ] Verify email addresses

### 2. Generate API Tokens
- [ ] PyPI: [Account Settings → API Tokens](https://pypi.org/manage/account/token/)
  - Create token with "Upload packages" scope
  - Save token securely
- [ ] Test PyPI: [Account Settings → API Tokens](https://test.pypi.org/manage/account/token/)
  - Create token with "Upload packages" scope
  - Save token securely

### 3. Add GitHub Secrets
Go to: Repository → Settings → Secrets and variables → Actions

- [ ] Add `PYPI_API_TOKEN`
  - Click "New repository secret"
  - Name: `PYPI_API_TOKEN`
  - Value: Your PyPI token (starts with `pypi-`)
  - Click "Add secret"

- [ ] Add `TEST_PYPI_API_TOKEN`
  - Click "New repository secret"
  - Name: `TEST_PYPI_API_TOKEN`
  - Value: Your Test PyPI token (starts with `pypi-`)
  - Click "Add secret"

## ✅ Optional Setup (Recommended)

### 4. Configure Branch Protection
Go to: Repository → Settings → Branches → Add rule

- [ ] Branch name pattern: `main` (or `master`)
- [ ] Require status checks to pass before merging
  - [ ] Select "Tests" workflow
- [ ] Require pull request reviews before merging
- [ ] Enable "Automatically delete head branches"

### 5. Add Repository Labels
Go to: Repository → Issues → Labels

Add these labels for Release Drafter:
- [ ] `feature` (color: #0e8a16) - New features
- [ ] `enhancement` (color: #84b6eb) - Improvements
- [ ] `bug` (color: #d73a4a) - Bug reports
- [ ] `fix` (color: #d73a4a) - Bug fixes
- [ ] `documentation` (color: #0075ca) - Documentation
- [ ] `docs` (color: #0075ca) - Docs alias
- [ ] `chore` (color: #fef2c0) - Maintenance
- [ ] `maintenance` (color: #fef2c0) - Maintenance alias
- [ ] `major` (color: #b60205) - Major version bump
- [ ] `minor` (color: #fbca04) - Minor version bump
- [ ] `patch` (color: #c2e0c6) - Patch version bump

### 6. Enable GitHub Actions
Go to: Repository → Settings → Actions → General

- [ ] "Allow all actions and reusable workflows" (or select allowed)
- [ ] Workflow permissions: "Read and write permissions"
- [ ] Enable "Allow GitHub Actions to create and approve pull requests"

### 7. Configure Release Drafter Permissions
Go to: Repository → Settings → Actions → General → Workflow permissions

- [ ] Select "Read and write permissions"

## ✅ Testing Workflows

### 8. Test Installation
- [ ] Push code to `main` branch
- [ ] Check Actions tab - "Tests" workflow should run
- [ ] Verify all jobs pass (Ubuntu, macOS, Windows)
- [ ] Check "Lint" workflow runs successfully

### 9. Test Publishing (Test PyPI)
- [ ] Go to Actions → "Publish to PyPI"
- [ ] Click "Run workflow"
- [ ] Select branch: `main`
- [ ] Choose: `testpypi`
- [ ] Click "Run workflow"
- [ ] Wait for completion
- [ ] Test installation:
  ```bash
  pip install --index-url https://test.pypi.org/simple/ \
      --extra-index-url https://pypi.org/simple/ \
      easy-drone
  ```

### 10. Test Release Drafter
- [ ] Create a test branch
- [ ] Make a small change
- [ ] Create a Pull Request
- [ ] Add a label (e.g., `feature`)
- [ ] Merge the PR
- [ ] Go to Releases → Check for draft release
- [ ] Verify release notes are generated

## ✅ Production Release

### 11. First Production Release
- [ ] Update version in `setup.py`: `version="0.1.0"`
- [ ] Update version in `pyproject.toml`: `version = "0.1.0"`
- [ ] Update `CHANGES.md` with release notes
- [ ] Commit and push:
  ```bash
  git add setup.py pyproject.toml CHANGES.md
  git commit -m "Prepare release 0.1.0"
  git push origin main
  ```
- [ ] Create GitHub Release:
  - Go to Releases → "Draft a new release"
  - Tag: `v0.1.0` (create new)
  - Title: `v0.1.0` or `Release 0.1.0`
  - Description: Copy from CHANGES.md
  - Click "Publish release"
- [ ] Wait for "Publish to PyPI" workflow to complete
- [ ] Verify on PyPI: https://pypi.org/project/easy-drone/
- [ ] Test installation:
  ```bash
  pip install easy-drone
  python -c "from gz_transport import Node; print('Success!')"
  ```

## 📝 Quick Reference

### View Workflow Runs
Repository → Actions tab

### Check Workflow Logs
Actions → Select workflow → Click on run → Expand job

### Manually Trigger Workflow
Actions → Select workflow → "Run workflow" button

### Update Secrets
Settings → Secrets and variables → Actions → Edit secret

### Check Package on PyPI
- Production: https://pypi.org/project/easy-drone/
- Test: https://test.pypi.org/project/easy-drone/

## 🆘 Troubleshooting

### Workflow fails with "Invalid token"
➡️ Check that secrets are set correctly in Settings → Secrets

### Workflow fails with "Resource not accessible"
➡️ Check workflow permissions in Settings → Actions → General

### Package not found after publishing
➡️ Wait 5-10 minutes for PyPI to index, then check PyPI project page

### Tests fail on specific platform
➡️ Check workflow logs, may need platform-specific fixes

### Release Drafter not creating releases
➡️ Check workflow permissions include "contents: write"

## 📚 Documentation

- [RELEASE_GUIDE.md](.github/RELEASE_GUIDE.md) - Detailed release process
- [WORKFLOWS_SUMMARY.md](.github/WORKFLOWS_SUMMARY.md) - Workflow details
- [GitHub Actions Docs](https://docs.github.com/en/actions)
- [PyPI Publishing Guide](https://packaging.python.org/tutorials/packaging-projects/)

## ✨ Ready to Release!

Once you've completed this checklist, you're ready to:
1. ✅ Run tests automatically on every push
2. ✅ Maintain code quality with linting
3. ✅ Publish to PyPI with one click
4. ✅ Auto-generate release notes

**Happy Releasing!** 🚀

