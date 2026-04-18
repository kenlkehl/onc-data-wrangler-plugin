# Installing R + Bioconductor for `analyze-data`

The `analyze-data` skill uses R/Bioconductor for a subset of analyses that Python can't cover (methylation IDAT preprocessing, CONUMEE CNV calls, `limma`/`edgeR` moderated DE, `fgsea` enrichment, `ConsensusClusterPlus`). This guide covers the one-time setup.

If R is not installed, `analyze-data` still works in Python-only mode with reduced capability — it will report `BACKENDS_AVAILABLE` at startup and emit a clear error for R-specific recipes, pointing back at this document.

## 1. Install R (system runtime)

Pick the path that matches your machine. All paths install R ≥ 4.3.

### macOS

```bash
brew install r
```

Or, if you don't have Homebrew, download the official installer from <https://cran.r-project.org/bin/macosx/> and run it.

### Debian / Ubuntu

```bash
sudo apt update
sudo apt install -y r-base r-base-dev
```

The distro-packaged R is often a release or two behind. For the current release:

```bash
# Add CRAN's apt repo (one-time)
sudo apt install -y --no-install-recommends software-properties-common dirmngr
wget -qO- https://cloud.r-project.org/bin/linux/ubuntu/marutter_pubkey.asc | sudo tee /etc/apt/trusted.gpg.d/cran_ubuntu_key.asc
sudo add-apt-repository "deb https://cloud.r-project.org/bin/linux/ubuntu $(lsb_release -cs)-cran40/"
sudo apt update
sudo apt install -y r-base
```

### RHEL / Fedora / Rocky / Alma

```bash
sudo dnf install -y R
```

### Windows

Download and run the installer at <https://cran.r-project.org/bin/windows/base/>. Add R to your `PATH` during install (the installer offers this as a checkbox).

### User-space install (no sudo)

If you can't install system-wide, use [`rig`](https://github.com/r-lib/rig) — it manages multiple R versions under `~/.local/`:

```bash
# macOS / Linux
curl -Ls https://github.com/r-lib/rig/releases/latest/download/rig-linux-latest.tar.gz | \
  tar xz -C ~/.local
~/.local/bin/rig add release
```

Then add `~/.local/bin` to your `PATH`.

## 2. Verify R is on your `PATH`

```bash
Rscript --version
# R scripting front-end version 4.3.2 (2023-10-31)
```

## 3. Install Bioconductor packages

From the repo root, the first invocation of an R-backed recipe will do this automatically via `renv::restore()`. To run it ahead of time:

```bash
cd /path/to/onc-data-wrangler-plugin
Rscript -e 'install.packages("renv", repos="https://cloud.r-project.org")'
Rscript -e 'renv::restore(project="skills/analyze-data/recipes/R", prompt=FALSE)'
```

**Expect this to take 10–20 minutes and ~4 GB of disk** on a fresh machine. `renv` caches per-package under `~/.cache/R/renv/` so subsequent projects restore instantly.

### If `renv::restore()` fails

Bioconductor sometimes needs OS-level build dependencies:

- **macOS:** `brew install openssl libxml2 curl gdal proj geos`
- **Debian/Ubuntu:** `sudo apt install -y libxml2-dev libssl-dev libcurl4-openssl-dev libgdal-dev libproj-dev libgeos-dev libharfbuzz-dev libfribidi-dev`
- **RHEL/Fedora:** `sudo dnf install -y libxml2-devel openssl-devel libcurl-devel gdal-devel proj-devel geos-devel`

Rerun `renv::restore()` after.

## 4. Install the scanpy stack (for snRNA-seq recipes)

scanpy lives in the existing project venv — no separate env manager:

```bash
cd /path/to/onc-data-wrangler-plugin
pip install -r skills/analyze-data/recipes/scanpy/requirements.txt
```

This installs `scanpy`, `anndata`, `infercnvpy`, `celltypist`, `scrublet`, and their deps (~1 GB).

## 5. Confirm backends are discovered

Start the `analyze-data` skill interactively and you should see:

```
BACKENDS_AVAILABLE = {
  python:  true,
  R:       {installed: true, packages: [minfi, conumee, limma, edgeR, fgsea, DESeq2, ConsensusClusterPlus, ...]},
  scanpy:  true
}
```

If any entry is `false`, the skill prints an actionable error pointing back at the section above.

## 6. Uninstalling

- R: reverse your OS package-manager install.
- `renv` cache: `rm -rf ~/.cache/R/renv/`
- scanpy: `pip uninstall -r skills/analyze-data/recipes/scanpy/requirements.txt -y`
