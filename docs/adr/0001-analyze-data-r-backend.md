# ADR 0001: R/Bioconductor backend for `analyze-data` — system install + `renv`

**Status:** Accepted
**Date:** 2026-04-17

## Context

The `analyze-data` skill is Python-only. Many oncology paper reproductions (most visibly **PMC10172395** — MPNST multi-omic profiling) require R/Bioconductor tooling: `minfi`/`conumee` for MethylationEPIC CNV calls, `limma`/`edgeR`/`DESeq2` for moderated differential expression, `fgsea` for MSigDB gene-set enrichment, and `ConsensusClusterPlus` for methylation-class discovery. Without these, ~60% of the paper's 197 quantitative results come back DISCREPANT on reproduction. We need a way to run R code from the skill.

Candidate approaches considered:

1. **System-installed R + `renv` lockfile** — users install R via their OS package manager (`brew`, `apt`, `dnf`, CRAN installer) or user-space `rig`; Bioconductor packages pinned via a committed `renv.lock` and restored with `Rscript -e 'renv::restore()'`.
2. **Conda/mamba environment** — `environment.yml` ships R + Bioconductor via conda-forge / bioconda.
3. **Docker image** — plugin ships `oncwrangler/analyze-data:latest` with R, Bioconductor, and the scanpy stack pre-baked; skill invokes each code block via `docker run`.
4. **`uv` + conda-forge `r-base`** — lightweight variant of (2).

## Decision

**Adopt (1): system-installed R + `renv` for package pinning.** scanpy goes into the existing project venv via `pip`; no new Python env manager.

## Rationale

- **Conda is blocked or restricted at many user sites** the plugin needs to run in (hospital networks, enterprise-managed laptops, airgapped research clusters). Making conda the primary path would make the R backend unavailable to a large fraction of intended users.
- **Docker has real overhead** — a second runtime to maintain, ~3 s cold-start per invocation × hundreds of questions per reproduction, and sysadmin requirements many users lack. It is acceptable as a fallback for users who prefer it, but not as the default path.
- **System R + `renv` is the lightest-weight portable option.** R is available from every major OS package manager; `renv` is the de-facto Bioconductor pinning tool and handles user-local package libraries without elevated privileges.
- The ~4 GB, ~10–20 minute one-time Bioconductor install is acceptable — it amortizes over every subsequent reproduction and is cached per-package by `renv`.

## Consequences

- Users must install R themselves; `docs/R_INSTALL.md` documents the OS-specific commands.
- The skill probes for R at startup and gracefully falls back to Python-only with a clear error pointing at `R_INSTALL.md` when R is missing. No silent degradation.
- CI builds `renv.lock` smoke-tests weekly on Ubuntu + macOS runners using system R to catch Bioconductor upstream drift.
- Docker and conda can be documented as optional alternative install paths but are not required and not maintained as first-class.
- Plugin's `pyproject.toml` is unchanged — R lives entirely outside Python dependency management.

## Alternatives rejected

- **Conda (2, 4):** blocked at too many target sites; makes the primary capability unavailable to many users.
- **Docker (3):** cold-start latency × high invocation count, and mandating Docker excludes users without sysadmin rights. Reintroducible later as an optional path.
