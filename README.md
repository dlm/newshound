# newshound

An autonomous agent that scrapes a set of personal news sites, extracts
articles with an LLM (no CSS selectors), scores them against a personal
interest profile with a second LLM, deduplicates them, and serves the result
as a personal RSS feed - deployed to a homelab k3s cluster.

See `CLAUDE.md` for the full architecture and the decisions behind it.

## Dev environment

```
nix develop
just dev-setup
just test
```

## Status

Project scaffolding only - no pipeline code yet. See `CLAUDE.md` for what's
decided vs. still open.
