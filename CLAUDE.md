# CLAUDE.md — agent working agreement for ATLAS-phd

This file is auto-loaded by Claude Code at session start. It defines repository-specific working conventions agreed with the user.

## Hard rules (do not violate)

1. **No disposable worktrees.** Never spawn agents with `isolation: "worktree"`. Never run `git worktree add`. Always edit files directly in `/Users/georgijmamarin/Desktop/ATLAS-phd` on `main` or a long-lived branch that is pushed to `origin` immediately after creation.
   - **Why:** On 2026-05-02, ~12 hours of M3 roadmap and eval-harness work in a worktree was lost when the worktree directory was deleted before any commit. Recovery was only possible by replaying tool calls from the session transcript.

2. **Commit + push every meaningful step.** After completing a logical chunk (new section, new module, fix), `git add` + `git commit` + `git push origin <branch>` immediately. No accumulating uncommitted state.
   - Use `wip:` or `chore: checkpoint` prefixes for in-progress saves rather than nothing.

3. **Commit messages without `Co-Authored-By: Claude`.** The user does not want Claude listed as a contributor in git history.

4. **Never push `--force` to `main`.** Prefer new commits over rewrites.

## Defaults

- **Language:** Russian for prose, code identifiers in English.
- **Branch:** `main`. The `develop-code` branch is the historical M2 line; new work lands on `main`.
- **Hardware target:** MacBook Pro M1, 8 GB RAM. LLM via OpenRouter API; embeddings local in Docker.
- **Stack:** FastAPI + Postgres+pgvector + sentence-transformers (embeddings sidecar) + Jinja2 UI. See `docs/system-design.md`.

## Live planning artifacts

- [`docs/roadmap.md`](docs/roadmap.md) — milestones M3–M6 with detailed sub-plans (M3.A–E, M4.A–D, M4.5.A–E, M5.A–D, M6.A–E).
- [`docs/bdd-scenarios.md`](docs/bdd-scenarios.md) — 53 Gherkin scenarios across 8 features, mapped to milestones.

Both documents are **authoritative for scope and priorities**. When the user requests a change to scope, update the roadmap version + add a changelog entry; do not just discuss verbally.

## OpenRouter free-tier reality (2026-05-02)

Model availability changes. As of last verification (2026-05-02), working free-tier models include:
- `meta-llama/llama-3.3-70b-instruct:free`
- `nvidia/nemotron-3-super-120b-a12b:free`
- `google/gemma-3-27b-it:free`
- `openai/gpt-oss-120b:free`

Models that **404** on OpenRouter (do not use): `qwen/qwen3-8b:free`, `qwen/qwen3.6-plus:free`.

Before any real LLM run: `curl -H "Authorization: Bearer $LLM_API_KEY" https://openrouter.ai/api/v1/models | jq '.data[] | select(.id | endswith(":free"))'` to confirm current list.

## Known gaps to address before M3 first end-to-end

- **M2 verifier hard-gate** does NOT block flow when `enough_evidence=False` — it goes to LLM-call anyway and returns `api_status="error"` (`TECHNICAL_ERROR`) on failure, not `REFUSAL_SENT` (BDD 1.3). This is recorded in `docs/roadmap.md` M3 risks. Fix in M3.A.0 before first end-to-end run, otherwise `refusal_correctness` (BDD 6.1) is unmeasurable.
