# Contributing to SideGate

Thank you for your interest in contributing to SideGate. This project adheres to disciplined engineering standards.

---

## Code of Conduct

All contributors and maintainers are expected to maintain professional, constructive, and respectful conduct across all communication channels.

---

## Development Workflow

1. Fork the repository and create a feature branch off `main`:
   ```bash
   git checkout -b feat/your-feature-name
   ```
2. Set up the development virtual environment:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -e ".[dev]"
   ```
3. Run tests and static analysis:
   ```bash
   pytest -v
   ruff check src tests
   ```
4. Commit changes referencing relevant issues:
   ```bash
   git commit -m "feat(scope): concise description (fixes #123)"
   ```
5. Open a formal Pull Request with technical rationale and test verification proof.

---

## Engineering Standards

- **Strict Zero-Emoji Rule**: Never include raw emojis in documentation, headings, commits, or code comments.
- **Deterministic Hashing**: Ensure all new state models implement canonical JSON serialization and deterministic hashing.
- **Test Coverage**: All new features and bug fixes must include unit or integration tests with a 100% pass rate.
