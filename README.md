<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/brand/otis-mark-mono-white.svg">
  <img src="docs/brand/otis-mark.svg" alt="Otis" width="48">
</picture>

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/brand/otis-lockup-dark.svg">
    <img src="docs/brand/otis-lockup.svg" alt="Otis" width="360">
  </picture>
</p>

# Otis: AI Security Advisor

Otis answers questions about real software vulnerabilities from public advisory data (NVD, GitHub advisories, CISA KEV). Every answer cites what it relied on, says "I don't know" when the sources do not cover the question, and shows where the sources disagree.

Work in progress. The phases, decisions and state of play are in [PROGRESS.md](PROGRESS.md); the main design decision is in [ADR 0001](docs/adr/0001-retrieval-answers-code-checks.md).

## Development

```
uv sync
uv run pytest
uv run ruff check .
```

## Why the name Otis?

Otis is my RAGdoll cat. It felt like the perfect name for a RAG project.
