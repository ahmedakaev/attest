# Contributing to Attest

Thank you for your interest in contributing to Attest! 🛡️

## Development Setup

```bash
git clone https://github.com/ahmedakaev/attest.git
cd attest
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Running Tests

```bash
python -m pytest tests/ -v
```

All tests must pass before submitting a pull request.

## Code Style

We use [ruff](https://docs.astral.sh/ruff/) for linting:

```bash
ruff check attest/ tests/
```

Ensure zero lint errors before committing.

## Pull Request Guidelines

1. **Fork** the repository and create your branch from `main`.
2. **Add tests** for any new functionality.
3. **Update documentation** if you change public APIs or behaviors.
4. **Keep PRs focused** — one feature or fix per pull request.
5. **Describe your changes** clearly in the PR description.

## Reporting Issues

- Use GitHub Issues to report bugs or suggest features.
- Include reproduction steps, expected vs actual behavior, and your Python version.

## License

By contributing, you agree that your contributions will be licensed under the [PolyForm Noncommercial License 1.0.0](LICENSE).
