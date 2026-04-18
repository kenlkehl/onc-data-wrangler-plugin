#!/usr/bin/env python3
"""
PMC Paper Search & Data Download CLI

Searches PMC for open-access oncology papers with publicly available data,
organized by research category. Designed to be called by the pull-papers
skill as individual subcommands that output JSON to stdout.

Subcommands:
    search    - Search PMC with category-specific queries
    metadata  - Fetch article metadata (title, abstract, data signals)
    filter    - Check OA status and score data availability
    download  - Download PDF + data for a specific paper
    validate  - Inspect data files for analyzability
"""

import argparse
import gzip
import io
import json
import logging
import os
import re
import sys
import tarfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

NCBI_ESEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
NCBI_EFETCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
PMC_OA_SERVICE = "https://www.ncbi.nlm.nih.gov/pmc/utils/oa/oa.fcgi"

XLINK_NS = "{http://www.w3.org/1999/xlink}"

USER_AGENT = (
    "Mozilla/5.0 (compatible; OncPaperPipeline/2.0; "
    "mailto:oncpipeline@example.com)"
)

SKIP_EXTENSIONS = {
    ".gif", ".jpg", ".jpeg", ".png", ".svg", ".tif", ".tiff", ".nxml", ".xml",
}

MAX_DATA_FILE_SIZE_MB = 100
MAX_RETRIES = 3

VALID_CATEGORIES = ["basic_science", "clinical", "computational_biology", "translational"]

# ---------------------------------------------------------------------------
# Category-specific PMC search queries
# ---------------------------------------------------------------------------

CATEGORY_QUERIES = {
    "basic_science": [
        # Cell lines, mouse models, molecular mechanisms, signaling
        '(cancer OR tumor OR neoplasm) AND ("cell line" OR "in vitro" OR "in vivo" '
        'OR "mouse model" OR "xenograft" OR "knockdown" OR "knockout" '
        'OR "signaling pathway" OR "gene expression" OR "Western blot") '
        'AND (has data avail[filter] OR has data citations[filter]) '
        'AND open access[filter]',
        # GEO-linked basic science
        '(cancer) AND ("GSE" OR "gene expression omnibus") '
        'AND ("cell line" OR "in vitro" OR "mechanism" OR "function") '
        'AND open access[filter]',
    ],
    "clinical": [
        # Clinical trials, survival, cohort studies, treatment outcomes
        '(cancer OR oncology) AND ("clinical trial" OR "overall survival" '
        'OR "progression-free survival" OR "hazard ratio" OR "cohort study" '
        'OR "randomized" OR "phase II" OR "phase III" OR "retrospective") '
        'AND (has data avail[filter] OR has data citations[filter]) '
        'AND open access[filter]',
        # Repository-linked clinical papers
        '(cancer) AND ("patient" OR "treatment" OR "outcome") '
        'AND (figshare OR zenodo OR dryad OR "supplementary data") '
        'AND open access[filter]',
    ],
    "computational_biology": [
        # Bioinformatics, ML, algorithms, multi-omics, single-cell methods
        '(cancer) AND ("machine learning" OR "deep learning" OR "bioinformatics" '
        'OR "computational" OR "algorithm" OR "network analysis" OR "multi-omics" '
        'OR "single-cell RNA" OR "scRNA-seq" OR "random forest" OR "neural network") '
        'AND (has data avail[filter] OR has data citations[filter]) '
        'AND open access[filter]',
        # Tool/pipeline papers with data
        '(cancer) AND ("pipeline" OR "tool" OR "software" OR "benchmark") '
        'AND ("GSE" OR "TCGA" OR "GEO") AND open access[filter]',
    ],
    "translational": [
        # Biomarkers, drug targets, PDX, organoids, bench-to-bedside
        '(cancer) AND ("biomarker" OR "translational" OR "therapeutic target" '
        'OR "drug response" OR "patient-derived" OR "organoid" '
        'OR "precision medicine" OR "companion diagnostic" OR "liquid biopsy") '
        'AND (has data avail[filter] OR has data citations[filter]) '
        'AND open access[filter]',
        # Preclinical with clinical relevance
        '(cancer) AND ("biomarker validation" OR "preclinical" OR "drug sensitivity") '
        'AND (figshare OR zenodo OR dryad OR "data availability") '
        'AND open access[filter]',
    ],
}

# ---------------------------------------------------------------------------
# Logging — to stderr so stdout stays clean for JSON
# ---------------------------------------------------------------------------

log = logging.getLogger("pmc_search")


def setup_logging(verbose: bool = False):
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        stream=sys.stderr,
    )


# ---------------------------------------------------------------------------
# Rate limiter
# ---------------------------------------------------------------------------


class RateLimiter:
    def __init__(self, calls_per_second: float = 2.8):
        self.min_interval = 1.0 / calls_per_second
        self.last_call = 0.0
        self.lock = threading.Lock()

    def wait(self):
        with self.lock:
            now = time.monotonic()
            elapsed = now - self.last_call
            if elapsed < self.min_interval:
                time.sleep(self.min_interval - elapsed)
            self.last_call = time.monotonic()


ncbi_limiter = RateLimiter(2.8)
other_limiter = RateLimiter(5.0)

# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------


def http_get(
    url: str,
    limiter: RateLimiter | None = None,
    timeout: int = 60,
    binary: bool = False,
    max_retries: int = MAX_RETRIES,
):
    """GET with retries, rate limiting, and User-Agent."""
    if limiter:
        limiter.wait()
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(max_retries):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = resp.read()
                return data if binary else data.decode("utf-8", errors="replace")
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as e:
            if attempt < max_retries - 1:
                wait = 2**attempt
                log.warning(
                    f"Retry {attempt + 1}/{max_retries} for {url}: {e} (waiting {wait}s)"
                )
                time.sleep(wait)
            else:
                raise
    return None  # unreachable


def download_file(
    url: str,
    dest: str,
    limiter: RateLimiter | None = None,
    timeout: int = 180,
    max_size_mb: int | None = None,
) -> bool:
    """Download a file to disk. Returns True on success."""
    if max_size_mb is None:
        max_size_mb = MAX_DATA_FILE_SIZE_MB

    if os.path.exists(dest) and os.path.getsize(dest) > 0:
        return True

    partial = dest + ".partial"
    if limiter:
        limiter.wait()
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(MAX_RETRIES):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                cl = resp.headers.get("Content-Length")
                if cl and int(cl) > max_size_mb * 1024 * 1024:
                    log.info(f"  Skipping (too large: {int(cl) / (1024 * 1024):.0f}MB): {url}")
                    return False

                os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
                total = 0
                with open(partial, "wb") as f:
                    while True:
                        chunk = resp.read(65536)
                        if not chunk:
                            break
                        total += len(chunk)
                        if total > max_size_mb * 1024 * 1024:
                            log.info(f"  Aborting (>{max_size_mb}MB): {url}")
                            os.remove(partial)
                            return False
                        f.write(chunk)

                os.rename(partial, dest)
                log.info(f"  Downloaded ({total / (1024 * 1024):.1f}MB): {os.path.basename(dest)}")
                return True
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as e:
            if os.path.exists(partial):
                os.remove(partial)
            if attempt < MAX_RETRIES - 1:
                log.warning(f"  Retry {attempt + 1} for {os.path.basename(dest)}: {e}")
                time.sleep(2**attempt)
            else:
                log.error(f"  Failed to download {url}: {e}")
                return False
    return False


def ftp_to_https(ftp_url: str) -> str:
    """Convert FTP URL from PMC OA service to HTTPS equivalent."""
    return ftp_url.replace(
        "ftp://ftp.ncbi.nlm.nih.gov/pub/pmc/",
        "https://ftp.ncbi.nlm.nih.gov/pub/pmc/deprecated/",
    )


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class DataSource:
    source_type: str  # "geo", "zenodo", "figshare", "dryad", "pmc_supp"
    identifier: str


@dataclass
class PaperMetadata:
    pmc_id: str = ""
    pmc_aid: str = ""
    pmid: str = ""
    doi: str = ""
    title: str = ""
    abstract: str = ""
    authors: list[str] = field(default_factory=list)
    journal: str = ""
    year: str = ""
    gse_ids: list[str] = field(default_factory=list)
    supp_files: list[str] = field(default_factory=list)
    data_availability: str = ""
    repository_urls: list[str] = field(default_factory=list)
    zenodo_ids: list[str] = field(default_factory=list)
    figshare_ids: list[str] = field(default_factory=list)
    dryad_dois: list[str] = field(default_factory=list)
    oa_tgz_url: str = ""
    oa_pdf_url: str = ""
    data_sources: list[DataSource] = field(default_factory=list)
    score: int = 0

    def to_dict(self) -> dict:
        d = asdict(self)
        d["data_sources"] = [
            {"source_type": s.source_type, "identifier": s.identifier}
            for s in self.data_sources
        ]
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "PaperMetadata":
        sources = d.pop("data_sources", [])
        p = cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})
        p.data_sources = [DataSource(**s) for s in sources]
        return p


# ---------------------------------------------------------------------------
# XML parsing helpers
# ---------------------------------------------------------------------------


def _get_text(el) -> str:
    """Get all text content from an element, including mixed content."""
    if el is None:
        return ""
    return "".join(el.itertext()).strip()


def _parse_article(article_el) -> PaperMetadata | None:
    """Parse a single <article> element into PaperMetadata."""
    p = PaperMetadata()

    # Article IDs
    for aid in article_el.findall(".//article-id"):
        pub_type = aid.get("pub-id-type", "")
        text = (aid.text or "").strip()
        if pub_type == "pmcid":
            p.pmc_id = text if text.startswith("PMC") else f"PMC{text}"
            p.pmc_aid = text.replace("PMC", "")
        elif pub_type == "pmcaid":
            if not p.pmc_aid:
                p.pmc_aid = text
                p.pmc_id = f"PMC{text}"
        elif pub_type == "pmid":
            p.pmid = text
        elif pub_type == "doi":
            p.doi = text

    if not p.pmc_aid:
        return None

    # Title
    p.title = _get_text(article_el.find(".//article-title"))

    # Abstract (NEW — needed for LLM classification)
    abstract_el = article_el.find(".//abstract")
    if abstract_el is not None:
        p.abstract = _get_text(abstract_el)

    # Authors
    for contrib in article_el.findall(".//contrib[@contrib-type='author']"):
        name_el = contrib.find("name")
        if name_el is not None:
            surname = _get_text(name_el.find("surname"))
            given = _get_text(name_el.find("given-names"))
            if surname:
                p.authors.append(f"{given} {surname}".strip())

    # Journal and year
    p.journal = _get_text(article_el.find(".//journal-title"))
    year_el = article_el.find(".//pub-date/year")
    if year_el is None:
        year_el = article_el.find(".//pub-date[@pub-type='epub']/year")
    p.year = _get_text(year_el)

    # Raw XML for regex fallback
    raw_xml = ET.tostring(article_el, encoding="unicode", method="xml")

    # GEO accessions from ext-link elements
    for ext_link in article_el.findall(".//ext-link"):
        link_type = ext_link.get("ext-link-type", "")
        href = ext_link.get(f"{XLINK_NS}href", "")
        text = _get_text(ext_link)
        if "geo" in link_type.lower() or "geo" in href.lower():
            for gse in re.findall(r"GSE\d{4,8}", text + " " + href):
                if gse not in p.gse_ids:
                    p.gse_ids.append(gse)

    # Regex fallback for GSE IDs
    for gse in re.findall(r"GSE\d{4,8}", raw_xml):
        if gse not in p.gse_ids:
            p.gse_ids.append(gse)

    # Supplementary files
    for supp in article_el.findall(".//supplementary-material"):
        for media in supp.findall(".//media"):
            href = media.get(f"{XLINK_NS}href", "")
            if href:
                p.supp_files.append(href)
        href = supp.get(f"{XLINK_NS}href", "")
        if href and href not in p.supp_files:
            p.supp_files.append(href)

    # Data availability statement
    for sec in article_el.findall(".//sec"):
        title_el = sec.find("title")
        sec_title = _get_text(title_el).lower()
        if "data avail" in sec_title or "data sharing" in sec_title:
            p.data_availability = _get_text(sec)
            break
    if not p.data_availability:
        for notes in article_el.findall(".//notes"):
            title_el = notes.find("title")
            notes_title = _get_text(title_el).lower()
            if "data" in notes_title and "avail" in notes_title:
                p.data_availability = _get_text(notes)
                break

    # Repository URLs
    search_text = p.data_availability + " " + raw_xml
    for ext_link in article_el.findall(".//ext-link"):
        href = ext_link.get(f"{XLINK_NS}href", "")
        if href and any(
            repo in href.lower()
            for repo in ["figshare", "zenodo", "dryad", "github.com"]
        ):
            if href not in p.repository_urls:
                p.repository_urls.append(href)

    # Zenodo IDs
    for m in re.findall(r"zenodo\.org/record[s]?/(\d+)", search_text):
        if m not in p.zenodo_ids:
            p.zenodo_ids.append(m)
    for m in re.findall(r"10\.5281/zenodo\.(\d+)", search_text):
        if m not in p.zenodo_ids:
            p.zenodo_ids.append(m)

    # Figshare IDs
    for m in re.findall(r"figshare\.com/articles?/[^/]+/(\d+)", search_text):
        if m not in p.figshare_ids:
            p.figshare_ids.append(m)
    for m in re.findall(r"10\.\d+/m9\.figshare\.(\d+)", search_text):
        if m not in p.figshare_ids:
            p.figshare_ids.append(m)

    # Dryad DOIs
    for m in re.findall(r"10\.5061/dryad\.\w+", search_text):
        if m not in p.dryad_dois:
            p.dryad_dois.append(m)

    return p


# ---------------------------------------------------------------------------
# Subcommand: search
# ---------------------------------------------------------------------------


def cmd_search(args):
    """Search PMC with category-specific queries."""
    category = args.category
    pool = args.pool

    if category == "all":
        categories = VALID_CATEGORIES
    else:
        categories = [category]

    results = {}
    for cat in categories:
        queries = CATEGORY_QUERIES[cat]
        all_ids: list[str] = []
        seen: set[str] = set()

        for i, query in enumerate(queries):
            log.info(f"[{cat}] Search query {i + 1}/{len(queries)}...")
            params = urllib.parse.urlencode(
                {
                    "db": "pmc",
                    "term": query,
                    "retmax": pool,
                    "retmode": "xml",
                    "sort": "relevance",
                }
            )
            url = f"{NCBI_ESEARCH}?{params}"

            try:
                xml_text = http_get(url, limiter=ncbi_limiter)
                root = ET.fromstring(xml_text)

                count_el = root.find(".//Count")
                total = count_el.text if count_el is not None else "?"
                log.info(f"  Query {i + 1} matched {total} articles")

                for id_el in root.findall(".//IdList/Id"):
                    aid = id_el.text.strip()
                    if aid not in seen:
                        seen.add(aid)
                        all_ids.append(aid)
            except Exception as e:
                log.error(f"  Search query {i + 1} failed: {e}")

            if len(all_ids) >= pool:
                break

        trimmed = all_ids[:pool]
        results[cat] = trimmed
        log.info(f"[{cat}] {len(trimmed)} unique candidate IDs")

    json.dump(results, sys.stdout, indent=2)
    print()


# ---------------------------------------------------------------------------
# Subcommand: metadata
# ---------------------------------------------------------------------------


def cmd_metadata(args):
    """Fetch article XML in batches and extract metadata."""
    pmc_aids = [aid.strip() for aid in args.ids.split(",") if aid.strip()]
    batch_size = 50
    papers: list[dict] = []

    for i in range(0, len(pmc_aids), batch_size):
        batch = pmc_aids[i : i + batch_size]
        log.info(f"Fetching metadata batch {i // batch_size + 1} ({len(batch)} articles)...")

        params = urllib.parse.urlencode(
            {"db": "pmc", "id": ",".join(batch), "rettype": "xml", "retmode": "xml"}
        )
        url = f"{NCBI_EFETCH}?{params}"

        try:
            xml_text = http_get(url, limiter=ncbi_limiter, timeout=120)

            # Strip DOCTYPE and XML declaration
            xml_text = re.sub(r'<\?xml[^>]*\?>', '', xml_text)
            xml_text = re.sub(r'<!DOCTYPE[^>]*>', '', xml_text)
            xml_text = xml_text.strip()

            try:
                root = ET.fromstring(xml_text)
            except ET.ParseError:
                xml_text = f"<wrapper>{xml_text}</wrapper>"
                root = ET.fromstring(xml_text)

            articles = root.findall(".//article")
            if not articles and root.tag == "article":
                articles = [root]

            for article_el in articles:
                paper = _parse_article(article_el)
                if paper:
                    papers.append(paper.to_dict())

            log.info(f"  Parsed {len(articles)} articles from batch")
        except Exception as e:
            log.error(f"  EFetch batch failed: {e}")

    log.info(f"Metadata complete: {len(papers)} papers parsed")
    json.dump(papers, sys.stdout, indent=2)
    print()


# ---------------------------------------------------------------------------
# Subcommand: filter
# ---------------------------------------------------------------------------


def _check_oa_status(paper: PaperMetadata) -> bool:
    """Check PMC OA service for download links. Returns True if OA with tgz."""
    url = f"{PMC_OA_SERVICE}?id={paper.pmc_id}"
    try:
        xml_text = http_get(url, limiter=ncbi_limiter, timeout=30)
        root = ET.fromstring(xml_text)

        error = root.find(".//error")
        if error is not None:
            return False

        for record in root.findall(".//record"):
            for link in record.findall("link"):
                fmt = link.get("format", "")
                href = link.get("href", "")
                if fmt == "tgz" and href:
                    paper.oa_tgz_url = ftp_to_https(href)
                elif fmt == "pdf" and href:
                    paper.oa_pdf_url = ftp_to_https(href)
        return bool(paper.oa_tgz_url)
    except Exception:
        return False


def _has_data_supp_files(paper: PaperMetadata) -> bool:
    for f in paper.supp_files:
        ext = os.path.splitext(f.lower())[1]
        if ext in {".xlsx", ".xls", ".csv", ".tsv"}:
            return True
        if ext == ".txt" and any(
            kw in f.lower() for kw in ["data", "table", "matrix"]
        ):
            return True
    return False


def cmd_filter(args):
    """Filter papers for OA status and data availability signals."""
    with open(args.metadata_file) as f:
        raw_papers = json.load(f)

    papers = [PaperMetadata.from_dict(d) for d in raw_papers]
    target = args.target
    candidates: list[dict] = []

    for i, paper in enumerate(papers):
        if i % 10 == 0:
            log.info(f"Filtering {i + 1}/{len(papers)}...")

        has_geo = bool(paper.gse_ids)
        has_supp = _has_data_supp_files(paper)
        has_zenodo = bool(paper.zenodo_ids)
        has_figshare = bool(paper.figshare_ids)
        has_dryad = bool(paper.dryad_dois)
        has_repo_url = bool(paper.repository_urls)

        if not (has_geo or has_supp or has_zenodo or has_figshare or has_dryad or has_repo_url):
            continue

        if not _check_oa_status(paper):
            continue

        # Build data sources
        for gse in paper.gse_ids:
            paper.data_sources.append(DataSource("geo", gse))
        for zid in paper.zenodo_ids:
            paper.data_sources.append(DataSource("zenodo", zid))
        for fid in paper.figshare_ids:
            paper.data_sources.append(DataSource("figshare", fid))
        for dd in paper.dryad_dois:
            paper.data_sources.append(DataSource("dryad", dd))
        if has_supp:
            paper.data_sources.append(DataSource("pmc_supp", paper.pmc_id))

        paper.score = (
            (2 if has_geo else 0)
            + (2 if has_zenodo or has_figshare or has_dryad else 0)
            + (1 if has_supp else 0)
            + (1 if has_repo_url else 0)
        )

        candidates.append(paper)
        log.info(
            f"  PASS: {paper.pmc_id} (score={paper.score}, "
            f"geo={len(paper.gse_ids)}, zenodo={len(paper.zenodo_ids)}, "
            f"figshare={len(paper.figshare_ids)}, dryad={len(paper.dryad_dois)}, "
            f"supp={has_supp})"
        )

        if len(candidates) >= target * 2:
            break

    candidates.sort(key=lambda p: p.score, reverse=True)
    selected = candidates[:target]
    log.info(f"Selected {len(selected)} papers (from {len(candidates)} candidates)")

    json.dump([p.to_dict() for p in selected], sys.stdout, indent=2)
    print()


# ---------------------------------------------------------------------------
# Subcommand: download
# ---------------------------------------------------------------------------


def _download_paper_tgz(paper: PaperMetadata, dest_dir: str) -> dict:
    """Download and extract the OA tar.gz package for a paper."""
    pdf_path = os.path.join(dest_dir, "paper.pdf")
    result = {"pdf": False, "data_files": [], "supplementary_files": []}

    if os.path.exists(pdf_path) and os.path.getsize(pdf_path) > 0:
        log.info(f"  PDF already exists for {paper.pmc_id}")
        result["pdf"] = True

    if not paper.oa_tgz_url:
        return result

    log.info(f"  Downloading tgz package...")
    try:
        tgz_data = http_get(
            paper.oa_tgz_url, limiter=ncbi_limiter, timeout=300, binary=True
        )
        if not tgz_data:
            return result

        os.makedirs(dest_dir, exist_ok=True)
        supp_dir = os.path.join(dest_dir, "supplementary")
        data_dir = os.path.join(dest_dir, "data")
        os.makedirs(supp_dir, exist_ok=True)
        os.makedirs(data_dir, exist_ok=True)

        found_pdf = False
        buf = io.BytesIO(tgz_data)

        with tarfile.open(fileobj=buf, mode="r:gz") as tar:
            for member in tar.getmembers():
                if not member.isfile():
                    continue
                basename = os.path.basename(member.name)
                ext = os.path.splitext(basename.lower())[1]

                if ext in SKIP_EXTENSIONS:
                    continue

                # Main PDF: first non-supplementary PDF
                if ext == ".pdf" and not found_pdf:
                    is_supp = any(
                        kw in basename.lower()
                        for kw in [
                            "moesm", "supp", "supplement", "appendix",
                            "additional", "table_s", "figure_s",
                        ]
                    )
                    if not is_supp:
                        f_obj = tar.extractfile(member)
                        if f_obj:
                            with open(pdf_path, "wb") as out_f:
                                out_f.write(f_obj.read())
                            found_pdf = True
                            result["pdf"] = True
                            log.info(f"  Extracted main PDF: {basename}")
                            continue

                if ext == ".pdf":
                    f_obj = tar.extractfile(member)
                    if f_obj:
                        out = os.path.join(supp_dir, basename)
                        with open(out, "wb") as out_f:
                            out_f.write(f_obj.read())
                        result["supplementary_files"].append(basename)
                elif ext in {".xlsx", ".xls", ".csv", ".tsv", ".parquet"}:
                    f_obj = tar.extractfile(member)
                    if f_obj:
                        out = os.path.join(data_dir, basename)
                        with open(out, "wb") as out_f:
                            out_f.write(f_obj.read())
                        result["data_files"].append(basename)
                        log.info(f"  Extracted data file: {basename}")
                elif ext == ".txt":
                    name_lower = basename.lower()
                    if any(
                        kw in name_lower
                        for kw in ["data", "table", "matrix", "result"]
                    ):
                        f_obj = tar.extractfile(member)
                        if f_obj:
                            out = os.path.join(data_dir, basename)
                            with open(out, "wb") as out_f:
                                out_f.write(f_obj.read())
                            result["data_files"].append(basename)
                elif ext in {".docx", ".doc"}:
                    f_obj = tar.extractfile(member)
                    if f_obj:
                        out = os.path.join(supp_dir, basename)
                        with open(out, "wb") as out_f:
                            out_f.write(f_obj.read())
                        result["supplementary_files"].append(basename)

        # Fallback: grab first PDF if main not found
        if not found_pdf:
            buf.seek(0)
            with tarfile.open(fileobj=buf, mode="r:gz") as tar:
                for member in tar.getmembers():
                    if member.isfile() and member.name.lower().endswith(".pdf"):
                        f_obj = tar.extractfile(member)
                        if f_obj:
                            with open(pdf_path, "wb") as out_f:
                                out_f.write(f_obj.read())
                            found_pdf = True
                            result["pdf"] = True
                            log.info(f"  Extracted PDF (fallback): {os.path.basename(member.name)}")
                            break

    except Exception as e:
        log.error(f"  tgz extraction failed: {e}")

    return result


def _download_geo_data(gse_id: str, data_dir: str) -> list[str]:
    """Download GEO series matrix files. Returns list of downloaded filenames."""
    log.info(f"  GEO: downloading {gse_id}...")
    downloaded = []

    numeric = gse_id[3:]
    if len(numeric) <= 3:
        prefix = gse_id[:3] + "nnn"
    else:
        prefix = gse_id[:-3] + "nnn"

    base_url = f"https://ftp.ncbi.nlm.nih.gov/geo/series/{prefix}/{gse_id}"

    # Matrix files
    matrix_url = f"{base_url}/matrix/"
    try:
        html = http_get(matrix_url, limiter=ncbi_limiter, timeout=30)
        files = re.findall(r'href="([^"]+\.txt\.gz)"', html)
        for fname in files:
            dest = os.path.join(data_dir, fname)
            if download_file(matrix_url + fname, dest, limiter=ncbi_limiter):
                downloaded.append(fname)
    except Exception as e:
        log.warning(f"  GEO matrix failed for {gse_id}: {e}")

    # Supplementary processed files (skip raw)
    suppl_url = f"{base_url}/suppl/"
    try:
        html = http_get(suppl_url, limiter=ncbi_limiter, timeout=30)
        files = re.findall(r'href="([^"]+)"', html)
        for fname in files:
            fl = fname.lower()
            if any(
                fl.endswith(ext)
                for ext in (".cel.gz", ".cel", ".bam", ".fastq", ".fastq.gz", ".sra")
            ):
                continue
            if "raw" in fl and fl.endswith(".tar"):
                continue
            ext = os.path.splitext(fl)[1]
            if ext in {".csv", ".tsv", ".xlsx", ".txt", ".gz", ".xls"}:
                dest = os.path.join(data_dir, fname)
                if download_file(suppl_url + fname, dest, limiter=ncbi_limiter):
                    downloaded.append(fname)
    except Exception:
        pass  # suppl often doesn't exist

    return downloaded


def _download_zenodo_data(zenodo_id: str, data_dir: str) -> list[str]:
    """Download data files from a Zenodo record."""
    log.info(f"  Zenodo: downloading record {zenodo_id}...")
    downloaded = []

    try:
        json_text = http_get(
            f"https://zenodo.org/api/records/{zenodo_id}",
            limiter=other_limiter, timeout=30,
        )
        record = json.loads(json_text)
        files = record.get("files", [])
        if not files:
            log.warning(f"  Zenodo {zenodo_id}: no files")
            return downloaded

        for fi in files:
            fname = fi.get("key", "")
            ext = os.path.splitext(fname.lower())[1]
            size = fi.get("size", 0)
            if ext not in {".csv", ".tsv", ".xlsx", ".xls", ".parquet", ".json", ".txt", ".gz", ".zip"}:
                continue
            if size > MAX_DATA_FILE_SIZE_MB * 1024 * 1024:
                log.info(f"  Skipping large: {fname} ({size / (1024 * 1024):.0f}MB)")
                continue
            dl_url = fi.get("links", {}).get("self", "")
            if dl_url:
                dest = os.path.join(data_dir, fname)
                if download_file(dl_url, dest, limiter=other_limiter):
                    downloaded.append(fname)
    except Exception as e:
        log.error(f"  Zenodo {zenodo_id} failed: {e}")

    return downloaded


def _download_figshare_data(figshare_id: str, data_dir: str) -> list[str]:
    """Download data files from a Figshare article."""
    log.info(f"  Figshare: downloading article {figshare_id}...")
    downloaded = []

    try:
        json_text = http_get(
            f"https://api.figshare.com/v2/articles/{figshare_id}",
            limiter=other_limiter, timeout=30,
        )
        article = json.loads(json_text)
        files = article.get("files", [])
        if not files:
            log.warning(f"  Figshare {figshare_id}: no files")
            return downloaded

        for fi in files:
            fname = fi.get("name", "")
            ext = os.path.splitext(fname.lower())[1]
            size = fi.get("size", 0)
            if ext not in {".csv", ".tsv", ".xlsx", ".xls", ".parquet", ".json",
                           ".txt", ".gz", ".zip", ".sav", ".rds", ".rdata"}:
                continue
            if size > MAX_DATA_FILE_SIZE_MB * 1024 * 1024:
                log.info(f"  Skipping large: {fname} ({size / (1024 * 1024):.0f}MB)")
                continue
            dl_url = fi.get("download_url", "")
            if dl_url:
                dest = os.path.join(data_dir, fname)
                if download_file(dl_url, dest, limiter=other_limiter):
                    downloaded.append(fname)
    except Exception as e:
        log.error(f"  Figshare {figshare_id} failed: {e}")

    return downloaded


def _download_dryad_data(dryad_doi: str, data_dir: str) -> list[str]:
    """Download data files from a Dryad dataset."""
    log.info(f"  Dryad: downloading {dryad_doi}...")
    downloaded = []
    encoded_doi = urllib.parse.quote(f"doi:{dryad_doi}", safe="")
    url = f"https://datadryad.org/api/v2/datasets/{encoded_doi}"

    try:
        json_text = http_get(url, limiter=other_limiter, timeout=30)
        dataset = json.loads(json_text)

        # Navigate to files: dataset -> version -> files
        version_url = dataset.get("_links", {}).get("stash:version", {}).get("href", "")
        if not version_url:
            versions_url = dataset.get("_links", {}).get("stash:versions", {}).get("href", "")
            if versions_url:
                if not versions_url.startswith("http"):
                    versions_url = f"https://datadryad.org{versions_url}"
                v_text = http_get(versions_url, limiter=other_limiter, timeout=30)
                versions = json.loads(v_text)
                v_list = versions.get("_embedded", {}).get("stash:versions", [])
                if v_list:
                    version_url = (
                        v_list[-1].get("_links", {}).get("self", {}).get("href", "")
                    )

        if not version_url:
            log.warning(f"  Dryad {dryad_doi}: no version found")
            return downloaded
        if not version_url.startswith("http"):
            version_url = f"https://datadryad.org{version_url}"

        v_text = http_get(version_url, limiter=other_limiter, timeout=30)
        version = json.loads(v_text)
        files_url = version.get("_links", {}).get("stash:files", {}).get("href", "")
        if not files_url:
            return downloaded
        if not files_url.startswith("http"):
            files_url = f"https://datadryad.org{files_url}"

        f_text = http_get(files_url, limiter=other_limiter, timeout=30)
        files_data = json.loads(f_text)

        for fi in files_data.get("_embedded", {}).get("stash:files", []):
            fname = fi.get("path", "")
            ext = os.path.splitext(fname.lower())[1]
            size = fi.get("size", 0)
            if ext not in {".csv", ".tsv", ".xlsx", ".xls", ".parquet", ".json", ".txt", ".gz", ".zip"}:
                continue
            if size > MAX_DATA_FILE_SIZE_MB * 1024 * 1024:
                continue
            dl_url = (
                fi.get("_links", {}).get("stash:file-download", {}).get("href", "")
            )
            if not dl_url:
                continue
            if not dl_url.startswith("http"):
                dl_url = f"https://datadryad.org{dl_url}"
            dest = os.path.join(data_dir, fname)
            if download_file(dl_url, dest, limiter=other_limiter):
                downloaded.append(fname)
    except Exception as e:
        log.error(f"  Dryad {dryad_doi} failed: {e}")

    return downloaded


def cmd_download(args):
    """Download PDF + data for a specific paper."""
    pmc_id = args.pmc_id
    if not pmc_id.startswith("PMC"):
        pmc_id = f"PMC{pmc_id}"
    dest_dir = args.dest

    # Load paper metadata from file or fetch it
    paper = None
    if args.metadata_file:
        with open(args.metadata_file) as f:
            papers_data = json.load(f)
        if isinstance(papers_data, list):
            for pd in papers_data:
                if pd.get("pmc_id") == pmc_id:
                    paper = PaperMetadata.from_dict(pd)
                    break
        elif isinstance(papers_data, dict) and papers_data.get("pmc_id") == pmc_id:
            paper = PaperMetadata.from_dict(papers_data)

    if paper is None:
        # Fetch metadata for this single paper
        pmc_aid = pmc_id.replace("PMC", "")
        params = urllib.parse.urlencode(
            {"db": "pmc", "id": pmc_aid, "rettype": "xml", "retmode": "xml"}
        )
        url = f"{NCBI_EFETCH}?{params}"
        xml_text = http_get(url, limiter=ncbi_limiter, timeout=120)
        xml_text = re.sub(r'<\?xml[^>]*\?>', '', xml_text)
        xml_text = re.sub(r'<!DOCTYPE[^>]*>', '', xml_text)
        xml_text = xml_text.strip()
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError:
            xml_text = f"<wrapper>{xml_text}</wrapper>"
            root = ET.fromstring(xml_text)
        articles = root.findall(".//article")
        if not articles and root.tag == "article":
            articles = [root]
        if articles:
            paper = _parse_article(articles[0])

    if paper is None:
        json.dump({"error": f"Could not find metadata for {pmc_id}"}, sys.stdout, indent=2)
        print()
        return

    # Check OA status if not already known
    if not paper.oa_tgz_url:
        _check_oa_status(paper)

    result = {
        "pmc_id": pmc_id,
        "dest": dest_dir,
        "pdf": False,
        "data_files": [],
        "supplementary_files": [],
        "external_downloads": {},
    }

    # Download tgz and extract
    tgz_result = _download_paper_tgz(paper, dest_dir)
    result["pdf"] = tgz_result["pdf"]
    result["data_files"].extend(tgz_result["data_files"])
    result["supplementary_files"].extend(tgz_result["supplementary_files"])

    # Download external data
    data_dir = os.path.join(dest_dir, "data")
    os.makedirs(data_dir, exist_ok=True)

    for source in paper.data_sources:
        if source.source_type == "pmc_supp":
            continue
        try:
            files = []
            if source.source_type == "geo":
                files = _download_geo_data(source.identifier, data_dir)
            elif source.source_type == "zenodo":
                files = _download_zenodo_data(source.identifier, data_dir)
            elif source.source_type == "figshare":
                files = _download_figshare_data(source.identifier, data_dir)
            elif source.source_type == "dryad":
                files = _download_dryad_data(source.identifier, data_dir)
            if files:
                key = f"{source.source_type}:{source.identifier}"
                result["external_downloads"][key] = files
                result["data_files"].extend(files)
        except Exception as e:
            log.error(f"  Data download error ({source.source_type}/{source.identifier}): {e}")

    # Write paper metadata
    metadata = {
        "pmc_id": paper.pmc_id,
        "pmid": paper.pmid,
        "doi": paper.doi,
        "title": paper.title,
        "abstract": paper.abstract[:3000],
        "authors": paper.authors,
        "journal": paper.journal,
        "year": paper.year,
        "data_availability": paper.data_availability[:2000],
        "data_sources": [
            {"type": s.source_type, "id": s.identifier} for s in paper.data_sources
        ],
        "files": {
            "paper_pdf": "paper.pdf" if result["pdf"] else None,
            "supplementary": result["supplementary_files"],
            "data": sorted(set(result["data_files"])),
        },
        "pipeline_timestamp": datetime.now(timezone.utc).isoformat(),
    }
    os.makedirs(dest_dir, exist_ok=True)
    with open(os.path.join(dest_dir, "paper_metadata.json"), "w") as f:
        json.dump(metadata, f, indent=2)

    json.dump(result, sys.stdout, indent=2)
    print()


# ---------------------------------------------------------------------------
# Subcommand: validate
# ---------------------------------------------------------------------------


def _inspect_file(fpath: str) -> dict:
    """Inspect a single data file and assess analyzability."""
    fname = os.path.basename(fpath)
    ext = os.path.splitext(fname.lower())[1]
    size = os.path.getsize(fpath)
    info = {
        "name": fname,
        "size_bytes": size,
        "format": ext,
        "analyzable": False,
        "rows": 0,
        "columns": 0,
        "column_names": [],
        "dtypes": {},
        "assessment": "",
    }

    if size == 0:
        info["assessment"] = "Empty file"
        return info

    try:
        import pandas as pd

        df = None

        if ext in {".csv"}:
            df = pd.read_csv(fpath, nrows=1000, on_bad_lines="skip")
        elif ext in {".tsv"}:
            df = pd.read_csv(fpath, sep="\t", nrows=1000, on_bad_lines="skip")
        elif ext in {".txt"}:
            # Try tab-separated first, then comma
            try:
                df = pd.read_csv(fpath, sep="\t", nrows=1000, comment="#", on_bad_lines="skip")
                if df.shape[1] < 2:
                    df = pd.read_csv(fpath, nrows=1000, comment="#", on_bad_lines="skip")
            except Exception:
                df = pd.read_csv(fpath, nrows=1000, comment="#", on_bad_lines="skip")
        elif ext in {".xlsx", ".xls"}:
            import openpyxl  # noqa: F401 — ensures it's available
            df = pd.read_excel(fpath, nrows=1000)
        elif ext in {".gz"}:
            # Try reading as gzipped text (tab or comma separated)
            try:
                df = pd.read_csv(fpath, sep="\t", nrows=1000, compression="gzip",
                                 comment="#", on_bad_lines="skip")
                if df.shape[1] < 2:
                    df = pd.read_csv(fpath, nrows=1000, compression="gzip",
                                     comment="#", on_bad_lines="skip")
            except Exception:
                try:
                    df = pd.read_csv(fpath, nrows=1000, compression="gzip",
                                     on_bad_lines="skip")
                except Exception:
                    info["assessment"] = "Could not parse gzipped file as tabular data"
                    return info
        elif ext in {".parquet"}:
            df = pd.read_parquet(fpath)
            if len(df) > 1000:
                df = df.head(1000)
        else:
            info["assessment"] = f"Unsupported format: {ext}"
            return info

        if df is None or df.empty:
            info["assessment"] = "Could not parse or empty content"
            return info

        # Get full row count for CSV/TSV (approximate from file)
        actual_rows = len(df)
        if ext in {".csv", ".tsv", ".txt", ".gz"} and actual_rows == 1000:
            # There are likely more rows; count lines for a better estimate
            try:
                if ext == ".gz":
                    with gzip.open(fpath, "rt", errors="replace") as gf:
                        actual_rows = sum(1 for _ in gf) - 1  # subtract header
                else:
                    with open(fpath, errors="replace") as rf:
                        actual_rows = sum(1 for _ in rf) - 1
            except Exception:
                pass  # keep the 1000 estimate

        info["rows"] = actual_rows
        info["columns"] = df.shape[1]
        info["column_names"] = list(df.columns[:20])
        info["dtypes"] = {str(k): str(v) for k, v in df.dtypes.items()}

        # Analyzability checks
        has_enough_columns = df.shape[1] >= 2
        has_enough_rows = actual_rows >= 5
        numeric_cols = df.select_dtypes(include=["number"]).shape[1]
        non_null_frac = df.notna().mean().mean() if not df.empty else 0

        if not has_enough_columns:
            info["assessment"] = f"Only {df.shape[1]} column(s) — not tabular"
        elif not has_enough_rows:
            info["assessment"] = f"Only {actual_rows} row(s) — insufficient data"
        elif numeric_cols == 0 and df.shape[1] <= 2:
            info["assessment"] = "No numeric columns and very few columns — likely metadata or IDs"
        elif non_null_frac < 0.1:
            info["assessment"] = "Over 90% null values — effectively empty"
        else:
            info["analyzable"] = True
            parts = []
            parts.append(f"{actual_rows} rows x {df.shape[1]} columns")
            if numeric_cols > 0:
                parts.append(f"{numeric_cols} numeric")
            cat_cols = df.select_dtypes(include=["object", "category"]).shape[1]
            if cat_cols > 0:
                parts.append(f"{cat_cols} categorical")
            info["assessment"] = "Analyzable: " + ", ".join(parts)

    except ImportError as e:
        info["assessment"] = f"Missing library: {e}"
    except Exception as e:
        info["assessment"] = f"Error inspecting file: {e}"

    return info


def cmd_validate(args):
    """Inspect data files in a directory and report analyzability."""
    data_dir = args.data_dir

    if not os.path.isdir(data_dir):
        json.dump({
            "data_dir": data_dir,
            "error": "Directory does not exist",
            "files": [],
            "analyzable_count": 0,
            "overall_analyzable": False,
        }, sys.stdout, indent=2)
        print()
        return

    files = sorted(
        f for f in os.listdir(data_dir)
        if os.path.isfile(os.path.join(data_dir, f))
        and not f.startswith(".")
    )

    results = []
    for fname in files:
        fpath = os.path.join(data_dir, fname)
        info = _inspect_file(fpath)
        results.append(info)

    analyzable = [r for r in results if r["analyzable"]]
    non_analyzable = [r for r in results if not r["analyzable"]]

    output = {
        "data_dir": data_dir,
        "files_inspected": len(results),
        "analyzable_count": len(analyzable),
        "overall_analyzable": len(analyzable) > 0,
        "analyzable_files": analyzable,
        "non_analyzable_files": non_analyzable,
    }

    if analyzable:
        total_rows = sum(f["rows"] for f in analyzable)
        total_cols = max(f["columns"] for f in analyzable)
        output["summary"] = (
            f"{len(analyzable)} analyzable file(s): "
            f"~{total_rows} total rows, up to {total_cols} columns"
        )
    else:
        output["summary"] = "No analyzable data files found"

    json.dump(output, sys.stdout, indent=2)
    print()


# ---------------------------------------------------------------------------
# Main CLI
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="PMC Paper Search & Data Download CLI for oncology research",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Verbose logging"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # -- search --
    sp_search = subparsers.add_parser(
        "search", help="Search PMC with category-specific queries"
    )
    sp_search.add_argument(
        "--category",
        choices=VALID_CATEGORIES + ["all"],
        required=True,
        help="Research category to search",
    )
    sp_search.add_argument(
        "--pool", type=int, default=100,
        help="Max candidate IDs per category (default: 100)",
    )

    # -- metadata --
    sp_meta = subparsers.add_parser(
        "metadata", help="Fetch article metadata from PMC"
    )
    sp_meta.add_argument(
        "--ids", required=True,
        help="Comma-separated PMC article IDs (numeric, without PMC prefix)",
    )

    # -- filter --
    sp_filter = subparsers.add_parser(
        "filter", help="Filter papers for OA status and data availability"
    )
    sp_filter.add_argument(
        "--metadata-file", required=True,
        help="JSON file with paper metadata array",
    )
    sp_filter.add_argument(
        "--target", type=int, default=20,
        help="Target number of papers (default: 20)",
    )

    # -- download --
    sp_dl = subparsers.add_parser(
        "download", help="Download PDF + data for a specific paper"
    )
    sp_dl.add_argument(
        "--pmc-id", required=True, help="PMC ID (e.g. PMC12345 or 12345)"
    )
    sp_dl.add_argument(
        "--dest", required=True, help="Destination directory for this paper"
    )
    sp_dl.add_argument(
        "--metadata-file",
        help="JSON file with paper metadata (avoids re-fetching)",
    )
    sp_dl.add_argument(
        "--max-file-size-mb", type=int, default=100,
        help="Max data file size in MB (default: 100)",
    )

    # -- validate --
    sp_val = subparsers.add_parser(
        "validate", help="Inspect data files for analyzability"
    )
    sp_val.add_argument(
        "--data-dir", required=True,
        help="Directory containing data files to inspect",
    )

    args = parser.parse_args()
    setup_logging(args.verbose)

    if hasattr(args, "max_file_size_mb"):
        global MAX_DATA_FILE_SIZE_MB  # noqa: PLW0603
        MAX_DATA_FILE_SIZE_MB = args.max_file_size_mb

    cmd_map = {
        "search": cmd_search,
        "metadata": cmd_metadata,
        "filter": cmd_filter,
        "download": cmd_download,
        "validate": cmd_validate,
    }
    cmd_map[args.command](args)


if __name__ == "__main__":
    main()
