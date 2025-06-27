# CI/CD Plan: Add Pyright Type Checking with Reporting

## Current State Analysis

- **Existing CI**: Only `docker-build.yml` workflow (no tests/linting CI)
- **Type Checker**: Pyright available as optional dependency in dev extras
- **Configuration**: No existing pyright configuration file
- **Type Errors**: 24+ type errors currently in `mcp_manager.py` alone
- **Issue**: Missing ToolType import caused runtime MCP auto-discovery failure

## Implementation Plan

### 1. Create New CI Workflow: `.github/workflows/ci.yml`

**Design Principles:**
- **Separate from Docker build** to ensure Docker image still builds regardless of type errors
- **Run on PR and push** to main/dev branches  
- **Continue-on-error strategy** for type checking initially (non-blocking)
- **Comprehensive reporting** with JSON output and artifact storage

### 2. Workflow Jobs Structure

#### Job 1: Type Checking
```yaml
type-check:
  runs-on: ubuntu-latest
  continue-on-error: true  # Initially non-blocking
  steps:
    - uses: actions/checkout@v4
    - name: Setup Python 3.12
      uses: actions/setup-python@v4
      with:
        python-version: '3.12'
    - name: Install Poetry
      uses: snok/install-poetry@v1
    - name: Install dependencies
      run: poetry install -E dev
    - name: Run Pyright
      run: poetry run pyright --outputjson > pyright-results.json
    - name: Upload results
      uses: actions/upload-artifact@v4
      with:
        name: pyright-results
        path: pyright-results.json
```

#### Job 2: Generate Type Report
```yaml
type-report:
  runs-on: ubuntu-latest
  needs: type-check
  if: always()  # Run even if type-check "fails"
  steps:
    - name: Download results
      uses: actions/download-artifact@v4
      with:
        name: pyright-results
    - name: Generate markdown report
      run: |
        # Convert JSON to readable markdown
        # Post as PR comment using GitHub API
    - name: Comment on PR
      if: github.event_name == 'pull_request'
      uses: actions/github-script@v7
      # Post type checking summary
```

### 3. Pyright Configuration: `pyrightconfig.json`

```json
{
  "include": [
    "letta"
  ],
  "exclude": [
    "tests",
    "examples", 
    "**/node_modules",
    "**/__pycache__"
  ],
  "pythonVersion": "3.12",
  "typeCheckingMode": "basic",
  "useLibraryCodeForTypes": true,
  "reportMissingImports": "error",
  "reportMissingTypeStubs": "warning",
  "reportUndefinedVariable": "error",
  "reportUnusedImport": "warning",
  "reportUnusedClass": "warning",
  "reportUnusedFunction": "warning"
}
```

### 4. Implementation Strategy

#### Phase 1: Non-blocking Type Checking (Immediate)
- ✅ Set up CI workflow with `continue-on-error: true`
- ✅ Generate JSON reports and PR comments
- ✅ Provide visibility without blocking development
- ✅ Start collecting baseline metrics

#### Phase 2: Incremental Improvements (Future)
- 🔄 Fix critical type errors (like missing imports)
- 🔄 Tighten pyright configuration gradually
- 🔄 Add specific module-level type checking gates
- 🔄 Eventually make type checking blocking

#### Phase 3: Full Type Safety (Long-term)
- 🎯 Remove `continue-on-error` flag
- 🎯 Enable strict type checking mode
- 🎯 Add type coverage metrics
- 🎯 Integrate with pre-commit hooks

### 5. Expected Benefits

**Immediate:**
- **Visibility**: Developers see type errors in PRs
- **Tracking**: Monitor type safety improvements over time
- **Non-disruptive**: Docker builds continue working
- **Early detection**: Catch import errors like the ToolType issue

**Long-term:**
- **Code Quality**: Better IDE support and fewer runtime errors
- **Refactoring Safety**: Confident large-scale changes
- **Documentation**: Types serve as inline documentation
- **Performance**: Better optimization opportunities

### 6. Files to Create/Modify

**New Files:**
- `.github/workflows/ci.yml` - Main CI workflow
- `pyrightconfig.json` - Type checker configuration
- `docs/CI.md` - This documentation (✅ Done)

**No Changes Required:**
- `.github/workflows/docker-build.yml` - Keep separate and unchanged
- `pyproject.toml` - Pyright already available in dev extras

### 7. Risk Mitigation

**Concern**: Type checking might break builds
- **Mitigation**: Use `continue-on-error: true` initially

**Concern**: Too many false positives  
- **Mitigation**: Start with basic mode, exclude problematic areas

**Concern**: Performance impact on CI
- **Mitigation**: Run in parallel with other jobs, cache dependencies

**Concern**: Developer adoption resistance
- **Mitigation**: Make non-blocking initially, provide helpful reports

## Example Type Error Report Format

```markdown
## 🔍 Type Checking Report

**Summary:** 24 errors, 15 warnings found in 8 files

### Critical Issues (Blocking)
- ❌ `letta/services/mcp_manager.py:164` - NameError: 'ToolType' is not defined
- ❌ `letta/services/mcp_manager.py:289` - NameError: 'HTTPException' is not defined

### Files with Most Issues
1. `letta/services/mcp_manager.py` - 24 errors
2. `letta/schemas/tool.py` - 8 warnings  
3. `letta/orm/tool.py` - 5 warnings

### Trend
- ⬆️ +3 new errors since last PR
- ⬇️ -1 warnings resolved
```

## Implementation Commands

When ready to implement:

```bash
# 1. Create the CI workflow
touch .github/workflows/ci.yml

# 2. Create pyright config  
touch pyrightconfig.json

# 3. Test locally
poetry install -E dev
poetry run pyright --outputjson

# 4. Commit and create PR
git add .github/workflows/ci.yml pyrightconfig.json docs/CI.md
git commit -m "feat: Add pyright type checking CI with reporting"
```

## Related Issues

- **Root Cause**: Missing ToolType import in mcp_manager.py (✅ Fixed)
- **Broader Issue**: No systematic type checking in CI pipeline
- **Future Work**: Fix the 24+ existing type errors gradually

---

*Plan created: 2025-06-27*  
*Status: Ready for implementation*