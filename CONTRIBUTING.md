# Contributing to SovereignDot

Thank you for your interest in contributing to **SovereignDot**!

---

## 🛠️ How to Contribute

1. **Fork the repository** and create your feature branch from `master`:
   ```bash
   git checkout -b feat/my-voice-skill
   ```
2. **Set up your local development environment**:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```
3. **Write or update unit tests** in `tests/` to cover your changes.
4. **Verify all tests and documentation build strictly**:
   ```bash
   python -m unittest discover tests
   mkdocs build --strict
   ```
5. **Follow Conventional Commits** (`feat:`, `fix:`, `docs:`, `refactor:`, `test:`).
6. **Open a Pull Request** with a clear description of your changes.

---

## 🧩 Adding a New Voice Skill (`@intent`)

To add a new voice skill without modifying the core engine, create a new module inside `core_server/intents/` and decorate your class with `@intent`:

- Read the complete step-by-step tutorial in [`docs/contributing/writing-intents.md`](docs/contributing/writing-intents.md).

---

## ⚖️ Clean-Room Policy

- **Never commit proprietary Amazon firmware binaries**, cryptographic keys, or copyrighted blobs.
- Always keep `.env` files, personal IP addresses, and API keys out of commits.
