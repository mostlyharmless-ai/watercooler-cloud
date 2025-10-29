# Contributing to Watercooler-Collab

Thank you for your interest in contributing to watercooler-collab! This document provides guidelines and information for contributors.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [How to Contribute](#how-to-contribute)
- [Pull Request Process](#pull-request-process)
- [Coding Standards](#coding-standards)
- [Testing Guidelines](#testing-guidelines)
- [Documentation](#documentation)
- [Community](#community)

---

## Code of Conduct

This project adheres to a code of conduct that all contributors are expected to follow:

- **Be respectful** - Value diverse perspectives and experiences
- **Be collaborative** - Work together constructively
- **Be professional** - Focus on technical merits
- **Be inclusive** - Welcome newcomers and help them succeed

Report any unacceptable behavior to the project maintainers.

---

## Getting Started

### Prerequisites

- **Python 3.10 or later** (required for watercooler-collab)
- **Git** for version control
- **GitHub account** for submitting pull requests

### Quick Start

1. **Fork the repository** on GitHub
2. **Clone your fork:**
   ```bash
   git clone https://github.com/YOUR_USERNAME/watercooler-collab.git
   cd watercooler-collab
   ```
3. **Add upstream remote:**
   ```bash
   git remote add upstream https://github.com/mostlyharmless-ai/watercooler-collab.git
   ```

---

## Development Setup

### Install in Development Mode

```bash
# Install with all development dependencies
pip install -e .[dev,mcp]

# Or if using conda/mamba
conda create -n watercooler python=3.10
conda activate watercooler
pip install -e .[dev,mcp]
```

**Development extras include:**
- `pytest` - Testing framework
- `pytest-cov` - Code coverage
- `black` - Code formatter
- `mypy` - Type checker
- `ruff` - Linter
- `fastmcp` - MCP server framework

### Verify Installation

```bash
# Test CLI
watercooler --help

# Test MCP server
python3 -m watercooler_mcp

# Run tests
pytest tests/
```

---

## How to Contribute

### Types of Contributions

We welcome various types of contributions:

#### 🐛 Bug Reports
- Search existing issues first
- Include minimal reproduction steps
- Provide environment details (OS, Python version)
- Include error messages and stack traces

#### ✨ Feature Requests
- Check [ROADMAP.md](../ROADMAP.md) for planned features
- Describe the use case and expected behavior
- Explain why this would be valuable
- Consider if it fits the project's goals

#### 📝 Documentation
- Fix typos and clarify confusing sections
- Add examples and use cases
- Improve API documentation
- Update outdated information

#### 🔧 Code Contributions
- Bug fixes
- New features (discuss first in an issue)
- Performance improvements
- Test coverage improvements

### Before Starting Work

1. **Check existing issues** - Someone may already be working on it
2. **Open an issue** - Discuss your approach before major changes
3. **Get feedback** - Especially for new features or breaking changes

---

## Pull Request Process

### 1. Create a Feature Branch

```bash
# Sync with upstream
git fetch upstream
git checkout main
git merge upstream/main

# Create feature branch
git checkout -b feature/your-feature-name
# or
git checkout -b fix/bug-description
```

**Branch naming conventions:**
- `feature/` - New features
- `fix/` - Bug fixes
- `docs/` - Documentation changes
- `refactor/` - Code refactoring
- `test/` - Test improvements

### 2. Make Your Changes

- **Write clear commit messages** (see [Commit Guidelines](#commit-guidelines))
- **Add tests** for new functionality
- **Update documentation** as needed
- **Run tests locally** before pushing

### 3. Commit Your Changes

```bash
# Stage your changes
git add .

# Commit with descriptive message
git commit -m "feat: add support for custom entry templates

- Allow users to override entry templates
- Add WATERCOOLER_ENTRY_TEMPLATE env var
- Update documentation with examples

Closes #123"
```

### 4. Push and Create Pull Request

```bash
# Push to your fork
git push origin feature/your-feature-name
```

Then open a pull request on GitHub:
1. Go to your fork on GitHub
2. Click "Pull Request"
3. Select `main` as the base branch
4. Fill in the PR template (see below)

### PR Template

```markdown
## Description
Brief description of what this PR does.

## Type of Change
- [ ] Bug fix (non-breaking change which fixes an issue)
- [ ] New feature (non-breaking change which adds functionality)
- [ ] Breaking change (fix or feature that would cause existing functionality to not work as expected)
- [ ] Documentation update

## Testing
- [ ] Tests pass locally
- [ ] New tests added for new functionality
- [ ] Documentation updated

## Related Issues
Closes #(issue number)

## Screenshots (if applicable)
```

### 5. Code Review Process

- **Maintainers will review** your PR
- **Address feedback** - Make requested changes
- **Keep PR focused** - One feature/fix per PR
- **Be patient** - Reviews may take time

---

## Coding Standards

### Python Style

We follow **PEP 8** with these tools:

```bash
# Format code
black src/ tests/

# Lint code
ruff check src/ tests/

# Type check
mypy src/
```

### Code Guidelines

#### 1. Type Hints

Always use type hints for function signatures:

```python
def say(
    topic: str,
    threads_dir: Path,
    agent: str,
    title: str,
    body: str,
    role: str = "implementer",
    entry_type: str = "Note"
) -> None:
    """Add an entry to a thread."""
    ...
```

#### 2. Docstrings

Use Google-style docstrings:

```python
def read_thread(topic: str, threads_dir: Path) -> str:
    """Read the content of a thread.

    Args:
        topic: The thread topic identifier
        threads_dir: Path to threads directory

    Returns:
        The full thread content as markdown

    Raises:
        FileNotFoundError: If thread doesn't exist
    """
    ...
```

#### 3. Error Handling

- Use specific exception types
- Provide helpful error messages
- Include context in exceptions

```python
try:
    content = thread_path.read_text()
except FileNotFoundError:
    raise FileNotFoundError(
        f"Thread '{topic}' not found at {thread_path}"
    )
```

#### 4. Naming Conventions

- **Functions/methods**: `snake_case`
- **Classes**: `PascalCase`
- **Constants**: `UPPER_SNAKE_CASE`
- **Private**: `_leading_underscore`

---

## Testing Guidelines

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=watercooler --cov-report=html

# Run specific test file
pytest tests/test_commands.py

# Run specific test
pytest tests/test_commands.py::test_say_command
```

### Writing Tests

#### Test Structure

```python
def test_feature_name():
    """Test description of what this validates."""
    # Arrange
    threads_dir = tmp_path / "threads"
    threads_dir.mkdir()

    # Act
    result = say("test-topic", threads_dir, ...)

    # Assert
    assert result is None
    thread_path = threads_dir / "test-topic.md"
    assert thread_path.exists()
```

#### Test Coverage Goals

- **Core functionality**: 90%+ coverage
- **Edge cases**: Test error conditions
- **Integration**: Test CLI commands end-to-end

#### Test Fixtures

Use pytest fixtures for common setup:

```python
@pytest.fixture
def temp_threads_dir(tmp_path: Path) -> Path:
    """Create temporary threads directory."""
    threads_dir = tmp_path / "threads"
    threads_dir.mkdir()
    return threads_dir
```

---

## Documentation

### Documentation Standards

- **Clear and concise** - Avoid jargon
- **Examples** - Show don't just tell
- **Up-to-date** - Update docs with code changes
- **Cross-references** - Link to related docs

### Documentation Types

#### 1. Code Documentation

- **Docstrings** - All public functions/classes
- **Type hints** - All function signatures
- **Comments** - For complex logic only

#### 2. User Documentation

Update these files as needed:
- `docs/QUICKSTART.md` - Getting started guide
- `docs/integration.md` - Integration patterns
- `docs/mcp-server.md` - MCP tool reference
- `docs/TROUBLESHOOTING.md` - Common issues

#### 3. API Documentation

- `docs/integration.md#python-api-reference` - Python API reference
- Keep examples current
- Document all public APIs

### Documentation Workflow

1. **Make code changes**
2. **Update relevant docs** in the same PR
3. **Add examples** if introducing new features
4. **Update ROADMAP.md** if changing project status

---

## Commit Guidelines

### Commit Message Format

```
<type>(<scope>): <subject>

<body>

<footer>
```

**Types:**
- `feat` - New feature
- `fix` - Bug fix
- `docs` - Documentation only
- `style` - Formatting, missing semicolons, etc.
- `refactor` - Code restructuring
- `test` - Adding tests
- `chore` - Maintenance tasks

**Examples:**

```
feat(mcp): add support for custom entry templates

- Allow users to override entry templates
- Add WATERCOOLER_ENTRY_TEMPLATE env var
- Update documentation with examples

Closes #123
```

```
fix(cli): handle missing threads directory gracefully

Previously the CLI would crash with FileNotFoundError.
Now it creates the directory automatically if missing.

Fixes #456
```

---

## Release Process

For maintainers:

### Version Numbering

We follow **Semantic Versioning** (SemVer):
- **MAJOR** - Breaking changes
- **MINOR** - New features (backward compatible)
- **PATCH** - Bug fixes

### Release Checklist

1. Update `__version__` in `src/watercooler/__init__.py`
2. Update `ROADMAP.md` with release notes
3. Tag release: `git tag v0.3.0`
4. Push tags: `git push --tags`
5. Create GitHub release
6. Publish to PyPI (when ready)

---

## Community

### Getting Help

- **Documentation**: Start with [README.md](../README.md) and [docs/](.)
- **Issues**: Search existing issues on GitHub
- **Discussions**: Use GitHub Discussions for questions

### Reporting Issues

**Bug reports should include:**
1. **Description** - What happened vs. what you expected
2. **Reproduction** - Minimal steps to reproduce
3. **Environment** - OS, Python version, watercooler version
4. **Logs** - Error messages and stack traces

**Use the issue template:**

```markdown
## Bug Description
Clear description of the bug

## Steps to Reproduce
1. Step one
2. Step two
3. See error

## Expected Behavior
What you expected to happen

## Environment
- OS: macOS 14.0
- Python: 3.11.5
- Watercooler: 0.2.0
- MCP Client: Claude Code

## Additional Context
Any other relevant information
```

### Feature Requests

**Feature requests should include:**
1. **Use case** - What problem does this solve?
2. **Expected behavior** - How should it work?
3. **Alternatives** - Other solutions considered
4. **Scope** - Is this a core feature or extension?

---

## Project Structure

Understanding the codebase:

```
watercooler-collab/
├── src/
│   ├── watercooler/          # Core library
│   │   ├── __init__.py
│   │   ├── agents.py         # Agent registry and canonicalization
│   │   ├── cli.py            # CLI entry point
│   │   ├── commands.py       # High-level command implementations
│   │   ├── config.py         # Configuration resolution
│   │   ├── entry.py          # Entry formatting
│   │   ├── fs.py             # File system operations
│   │   ├── header.py         # Header parsing/updating
│   │   ├── locking.py        # Advisory file locking
│   │   ├── metadata.py       # Thread metadata parsing
│   │   └── templates/        # Built-in templates
│   └── watercooler_mcp/      # MCP server
│       ├── __init__.py
│       ├── server.py         # FastMCP server implementation
│       ├── config.py         # MCP-specific configuration
│       └── git_sync.py       # Git synchronization (Phase 2A)
├── tests/                     # Test suite
│   ├── test_commands.py
│   ├── test_git_sync.py
│   └── ...
├── docs/                      # Documentation
│   ├── README.md
│   ├── QUICKSTART.md
│   ├── integration.md
│   └── ...
└── ROADMAP.md                 # Project status and roadmap
```

---

## License

By contributing, you agree that your contributions will be licensed under the same license as the project.

---

## Questions?

- **Documentation**: Check [docs/](.)
- **Issues**: [GitHub Issues](https://github.com/mostlyharmless-ai/watercooler-collab/issues)
- **Discussions**: [GitHub Discussions](https://github.com/mostlyharmless-ai/watercooler-collab/discussions)

Thank you for contributing to watercooler-collab! 🎉
