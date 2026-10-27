"""Build a reproducible, record-level audit ledger for the exact 146-country input."""

from __future__ import annotations

import argparse
import concurrent.futures
import io
import json
import re
from collections import Counter, defaultdict
from datetime import date
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "research/20261026_global_depth/TEST_INPUTS.json"
OUT = ROOT / "research/20261027_remediation/audit"
AUDIT_DATE = date.today().isoformat()
MAX_SOURCE_BYTES = 6_000_000
ACCESS_LOG = OUT / "source_access.log"
NUMBER = re.compile(r"(?:\b\d[\d,.]*\s*(?:%|percent|million|billion|thousand|people|households|household|communities|districts|years|year|km|ha|\b))", re.I)
FORECAST = re.compile(r"\b(project(?:ed|ion|ions)?|forecast|scenario|by 20\d\d|will |expected|expects|may |could |likely|potentially|future)\b", re.I)
PROGRAMME = re.compile(r"\b(plan(?:ned|s|ning)?|target(?:s|ed)?|intend(?:s|ed)?|will benefit|aim(?:s|ed)?|designed to|scheduled|commitment|proposed|underway)\b", re.I)
OUTCOME = re.compile(r"\b(reduced|improved|increased|strengthened|prevented|achieved|benefit(?:ed|s)?|impact|effective|successful)\b", re.I)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


class VisibleText(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.hidden = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript"}:
            self.hidden += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"} and self.hidden:
            self.hidden -= 1

    def handle_data(self, data: str) -> None:
        if not self.hidden and data.strip():
            self.parts.append(data.strip())


def locator_pages(locator: str) -> list[int]:
    pdf_part = re.search(r"\bPDF\b(.{0,45})", locator, re.I)
    if not pdf_part:
        return []
    text = pdf_part.group(1)
    page = re.search(r"\bpp?\.?\s*(\d+)(?:\s*[-–]\s*(\d+))?", text, re.I)
    if not page:
        return []
    first = int(page.group(1))
    last = int(page.group(2) or first)
    return list(range(first, min(last, first + 2) + 1))


def choose_country_target(base: str) -> dict[str, Any]:
    candidate = ROOT / base
    evidence = read_json(candidate / "evidence.json")
    pathways = read_json(candidate / "pathways.json")
    sources = {x["source_id"]: x for x in read_json(candidate / "sources.json")}
    linked = {eid for p in pathways for eid in p.get("supporting_evidence_ids", [])}
    def rank(record: dict[str, Any]) -> tuple[int, str]:
        direct = record.get("analytical_role") == "direct-climate-fcv" or record.get("evidence_class") == "direct-climate-fcv"
        reverse = record.get("interaction_direction") in {"fcv-to-climate", "bidirectional"}
        score = (60 if direct else 0) + (30 if reverse else 0) + (20 if record["evidence_id"] in linked else 0)
        if record.get("evidence_class") == "resilience-peace-capacity":
            score += 8
        sid = record.get("source_refs", [{}])[0].get("source_id")
        pubdate = str(sources.get(sid, {}).get("publication_date") or "0000")
        return score, pubdate
    for record in sorted(evidence, key=rank, reverse=True):
        refs = record.get("source_refs", [])
        if refs and refs[0].get("source_id") in sources:
            sid = refs[0]["source_id"]
            return {"iso3": candidate.parts[-3], "candidate_path": base, "record_id": record["evidence_id"], "record_text": record.get("statement") or record.get("compact_statement", ""), "source_id": sid, "source": sources[sid], "locator": refs[0].get("locator", "")}
    return {"iso3": candidate.parts[-3], "candidate_path": base, "record_id": None, "source_id": None, "error": "No source-referenced evidence record to select."}


def fetch_source(url: str) -> dict[str, Any]:
    try:
        request = Request(url, headers={"User-Agent": "Climate-FCV-Bank-Audit/1.0", "Accept": "application/pdf,text/html,text/plain,*/*"})
        with urlopen(request, timeout=12) as response:
            content_type = response.headers.get_content_type()
            declared_size = response.headers.get("Content-Length")
            if declared_size and int(declared_size) > MAX_SOURCE_BYTES:
                return {"access": "metadata-only", "http_status": response.status, "content_type": content_type, "declared_bytes": int(declared_size), "error": "source exceeds the in-memory size cap"}
            body = response.read(MAX_SOURCE_BYTES + 1)
            if len(body) > MAX_SOURCE_BYTES:
                return {"access": "metadata-only", "http_status": response.status, "content_type": content_type, "bytes_read": MAX_SOURCE_BYTES + 1, "error": "source exceeds the in-memory size cap"}
            return {"access": "document-fetched", "http_status": response.status, "content_type": content_type, "bytes_read": len(body), "body": body}
    except HTTPError as exc:
        return {"access": "unresolved", "http_status": exc.code, "error": f"HTTP {exc.code}"}
    except (URLError, TimeoutError, OSError, ValueError) as exc:
        return {"access": "unresolved", "error": f"{type(exc).__name__}: {str(exc)[:180]}"}


def extract_locator_text(fetched: dict[str, Any], locator: str) -> tuple[list[int], str, str]:
    body = fetched.get("body")
    if body is None:
        return [], "", ""
    content_type = fetched.get("content_type", "")
    if "pdf" in content_type or body[:5] == b"%PDF-":
        try:
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(body), strict=False)
            pages = locator_pages(locator)
            text = "\n".join(reader.pages[p - 1].extract_text() or "" for p in pages if 1 <= p <= len(reader.pages))
            return pages, text, "HTTPS GET; in-memory PDF page extraction with pypdf"
        except Exception as exc:
            return locator_pages(locator), "", f"HTTPS GET; PDF page extraction failed: {type(exc).__name__}"
    parser = VisibleText()
    try:
        parser.feed(body.decode("utf-8", errors="replace"))
    except Exception:
        return [], "", "HTTPS GET; HTML/text extraction failed"
    return [], "\n".join(parser.parts), "HTTPS GET; HTML visible-text extraction"


def compact_excerpt(text: str, claim: str) -> str:
    stop = {"the", "and", "for", "that", "with", "from", "were", "was", "are", "this", "their", "which", "into", "over", "during", "after", "when", "than", "about", "across"}
    terms = {w.lower() for w in re.findall(r"[A-Za-z]{5,}", claim) if w.lower() not in stop}
    lines = [line.strip() for line in re.split(r"[\r\n]+", text) if len(line.strip()) > 30]
    best = max(lines, key=lambda line: sum(term in line.lower() for term in terms), default="")
    return " ".join(best.split()[:20])


def claim_window(text: str, claim: str, minimum: int = 200, maximum: int = 350) -> str:
    """Return a bounded word window centered on the most claim-relevant sentence."""
    words = text.split()
    if len(words) <= maximum:
        return " ".join(words)
    stop = {"the", "and", "for", "that", "with", "from", "were", "was", "are", "this", "their", "which", "into", "over", "during", "after", "when", "than", "about", "across", "between", "these", "those", "there", "where", "while", "because", "through", "within", "also", "such", "have", "has", "had", "will", "would", "could", "should", "they", "them", "then", "than", "been", "being", "more", "most", "some", "many", "each", "both", "other", "which", "what", "when", "were", "were", "country", "countries"}
    terms = {w.lower() for w in re.findall(r"[A-Za-z]{4,}", claim) if w.lower() not in stop}
    if not terms:
        return " ".join(words[:maximum])
    starts = [m.start() for m in re.finditer(r"\S+", text)]
    best_pos = 0
    best_score = -1
    for match in re.finditer(r"[^.!?\n]+(?:[.!?]|$)", text):
        sentence = match.group(0).lower()
        score = sum(sentence.count(term) for term in terms)
        if score > best_score:
            best_score = score
            best_pos = match.start()
    center = next((i for i, pos in enumerate(starts) if pos >= best_pos), 0)
    width = min(maximum, max(minimum, len(words)))
    begin = max(0, center - width // 2)
    end = min(len(words), begin + width)
    begin = max(0, end - width)
    return " ".join(words[begin:end])


def fetch_review_excerpts(manifest: list[str]) -> None:
    """Fetch only previously extracted locator pages for review-sized local excerpts."""
    targets = []
    for base in manifest:
        iso = Path(base).parts[1]
        audit = read_json(OUT / f"{iso}.json")
        access = audit.get("source_access_review", {})
        if not access.get("cited_passage_text_extracted"):
            continue
        candidate = ROOT / base
        records = {x["evidence_id"]: x for x in read_json(candidate / "evidence.json")}
        rec_id = access.get("selected_record_id")
        record = records.get(rec_id)
        if not record or not access.get("url"):
            continue
        targets.append({
            "iso3": iso,
            "record_id": rec_id,
            "source_id": access.get("selected_source_id"),
            "url": access["url"],
            "locator": access.get("locator", ""),
            "claim": record.get("statement") or record.get("compact_statement", ""),
            "prior_access_date": access.get("accessed_on"),
        })
    by_url = {t["url"]: t for t in targets}
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        fetched = dict(zip(by_url, pool.map(fetch_source, by_url)))
    excerpt_dir = OUT / "source_documents"
    excerpt_dir.mkdir(parents=True, exist_ok=True)
    outcomes = Counter()
    for target in targets:
        result = fetched[target["url"]]
        pages, text, method = extract_locator_text(result, target["locator"])
        excerpt = claim_window(text, target["claim"]) if text else ""
        outcomes["locator-text-extracted" if text else result.get("access", "unresolved")] += 1
        path = excerpt_dir / f"{target['iso3']}_{target['record_id']}.txt"
        header = (
            f"ISO3: {target['iso3']}\nRecord ID: {target['record_id']}\nSource ID: {target['source_id']}\n"
            f"Candidate claim (for comparison): {target['claim']}\nLocator: {target['locator']}\nURL: {target['url']}\n"
            f"Access date: {AUDIT_DATE}; prior successful locator extraction: {target['prior_access_date']}\n"
            f"Review access method: {method or 'HTTPS GET with normal TLS verification'}\n"
            f"HTTP status: {result.get('http_status')}\nContent type: {result.get('content_type')}\n"
            f"Bytes read: {result.get('bytes_read') or result.get('declared_bytes')}\nPDF pages extracted: {pages}\n"
            f"Review status: excerpt only; semantic claim match has not been completed.\n"
        )
        if result.get("error"):
            header += f"Retrieval or extraction limit: {result['error']}\n"
        if excerpt:
            header += f"\nBounded locator-page excerpt ({len(excerpt.split())} words; max 350; for internal review):\n{excerpt}\n"
        else:
            header += "\nNo text excerpt available on this follow-up attempt; prior access result remains recorded in the public audit JSON.\n"
        path.write_text(header, encoding="utf-8", newline="\n")
    print(f"saved review-sized excerpts for {len(targets)} prior locator-text records; outcomes={dict(outcomes)}; files are ignored under source_documents/")


def reopen_selected_sources(manifest: list[str], run_date: str) -> None:
    targets = [choose_country_target(base) for base in manifest]
    by_url: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for target in targets:
        source = target.get("source", {})
        if target.get("record_id") and source.get("url"):
            by_url[source["url"]].append(target)
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        fetched = dict(zip(by_url, pool.map(fetch_source, by_url)))

    log_lines = ["HTTPS source-access attempts; one concise page excerpt per URL (max 20 words). HTTP success is not claim verification."]
    country_results: dict[str, dict[str, Any]] = {}
    for url, group in by_url.items():
        result = fetched[url]
        for target in group:
            pages, page_text, method = extract_locator_text(result, target.get("locator", ""))
            has_passage_text = bool(page_text.strip())
            source_access = "access-only" if has_passage_text else result.get("access", "unresolved")
            claim_status = "access-only" if has_passage_text else "unresolved"
            attempt = {
                "selected_record_id": target["record_id"],
                "selected_source_id": target["source_id"],
                "url": url,
                "locator": target.get("locator"),
                "accessed_on": run_date,
                "access_method": method or "HTTPS GET with normal TLS verification",
                "source_access_status": source_access,
                "claim_verification": claim_status,
                "http_status": result.get("http_status"),
                "content_type": result.get("content_type"),
                "bytes_read": result.get("bytes_read"),
                "declared_bytes": result.get("declared_bytes"),
                "pdf_pages_extracted": pages,
                "cited_passage_text_extracted": has_passage_text,
                "semantic_claim_match_completed": False,
                "error_or_limit": result.get("error"),
            }
            path = OUT / f"{target['iso3']}.json"
            audit = read_json(path)
            audit["selected_record_id"] = target["record_id"]
            audit["source_access_review"] = attempt
            audit["record_ids"] = [x["record_id"] for x in audit["evidence"] + audit["pathways"]]
            audit["checks"] = [{
                "record_id": target["record_id"],
                "source_id": target["source_id"],
                "locator": target.get("locator"),
                "verification_status": claim_status,
                "verification_method": attempt["access_method"],
                "access_date": run_date,
                "source_access_status": source_access,
                "cited_passage_text_extracted": has_passage_text,
                "semantic_claim_match_completed": False,
            }]
            aid = next((x for x in audit["evidence"] if x["record_id"] == target["record_id"]), None)
            if aid and aid.get("claim_verification") != "verified":
                aid.update({
                    "claim_verification": claim_status,
                    "reopened_on": run_date,
                    "verification_method": attempt["access_method"],
                    "verification_attempt": attempt,
                    "verification_note": "The selected source URL and cited page were accessed/extracted when available; the extracted passage was not yet semantically matched to the claim. This is not source verification.",
                })
            sid = next((x for x in audit["sources"] if x["source_id"] == target["source_id"]), None)
            if sid:
                sid["audit_access_attempt"] = attempt
                if sid.get("this_audit_verification") != "verified-for-listed-claims":
                    sid["this_audit_verification"] = "access-only" if has_passage_text else "unresolved"
                    sid["audit_accessed_on"] = run_date
            count = Counter(x["claim_verification"] for x in audit["evidence"])
            audit["verification_summary"]["evidence_claims"] = dict(count)
            audit["verification_summary"]["source_passages_reopened_by_this_audit"] = sum(bool(s.get("audit_access_attempt", {}).get("cited_passage_text_extracted")) for s in audit["sources"])
            audit["verification_summary"]["source_claims_verified_by_this_audit"] = count.get("verified", 0)
            audit["verification_summary"]["limitation"] = "One selected source per country was attempted. A fetched document or extracted locator page is access-only until its passage is semantically matched; all other claims remain unverified unless individually marked verified."
            audit["limitations"] = [f"{target['record_id']}: selected passage status is {claim_status}; semantic claim match remains outstanding."]
            audit["findings"] = [x for x in audit["findings"] if "No source passage is certified" not in x]
            audit["findings"].append("Selected source passage was accessed for one record only; this is not whole-country source verification.")
            path.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
            country_results[target["iso3"]] = {"selected_record_id": target["record_id"], "selected_source_id": target["source_id"], "source_access_status": source_access, "claim_verification": claim_status, "cited_passage_text_extracted": has_passage_text}
        excerpt = compact_excerpt("\n".join(extract_locator_text(result, target.get("locator", ""))[1] for target in group), group[0].get("record_text", "")) if result.get("body") else ""
        ids = ",".join(f"{t['iso3']}:{t['record_id']}" for t in group)
        log_lines.append(f"{ids} | {url} | {result.get('http_status')} | {result.get('content_type')} | {result.get('bytes_read') or result.get('declared_bytes')} bytes | {result.get('access')} | {excerpt}")
    ACCESS_LOG.write_text("\n".join(log_lines) + "\n", encoding="utf-8", newline="\n")
    aggregate_path = OUT / "aggregate.json"
    aggregate = read_json(aggregate_path)
    for row in aggregate.get("countries", []):
        row.update(country_results.get(row["iso3"], {"source_access_status": "unresolved", "claim_verification": "unresolved"}))
    aggregate["source_access_attempts"] = len(by_url)
    aggregate["countries_with_selected_records"] = len(country_results)
    aggregate["access_log"] = "research/20261027_remediation/audit/source_access.log (ignored by .gitignore)"
    aggregate["verified_claims"] = sum(1 for base in manifest for item in read_json(OUT / f"{Path(base).parts[1]}.json")["evidence"] if item["claim_verification"] == "verified")
    aggregate["limitation"] = "One source URL per country was attempted where a cited source was available. Access and PDF page extraction are recorded separately from claim verification; uninspected source claims remain unresolved."
    aggregate_path.write_text(json.dumps(aggregate, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"attempted {len(by_url)} unique URLs for {len(country_results)} countries with selected records; see per-country source_access_review and ignored source_access.log")


def finalize_cached_access_pass(manifest: list[str]) -> None:
    """Build aggregate and ignored per-record excerpt notes from completed access outputs."""
    rows = []
    statuses = Counter()
    excerpts_by_record: dict[str, str] = {}
    log_path = ACCESS_LOG
    if log_path.exists():
        for line in log_path.read_text(encoding="utf-8", errors="replace").splitlines()[1:]:
            parts = line.split(" | ", 6)
            if len(parts) != 7:
                continue
            ids, url, http, content_type, byte_count, access, excerpt = parts
            for item in ids.split(","):
                if ":" in item:
                    _, record_id = item.split(":", 1)
                    excerpts_by_record[record_id] = excerpt.strip()
    excerpt_dir = OUT / "source_documents"
    excerpt_dir.mkdir(parents=True, exist_ok=True)
    for base in manifest:
        iso = Path(base).parts[1]
        audit_path = OUT / f"{iso}.json"
        if not audit_path.exists():
            raise SystemExit(f"Missing completed per-country audit: {audit_path}")
        audit = read_json(audit_path)
        access = audit.get("source_access_review", {})
        access_status = access.get("source_access_status", "unresolved")
        claim_status = access.get("claim_verification", "unresolved")
        statuses[f"source_access:{access_status}"] += 1
        statuses[f"selected_claim:{claim_status}"] += 1
        rec_id = access.get("selected_record_id")
        excerpt = excerpts_by_record.get(rec_id, "") if rec_id else ""
        if rec_id:
            excerpt_file = excerpt_dir / f"{iso}_{rec_id}.txt"
            if excerpt:
                excerpt_file.write_text(
                    f"ISO3: {iso}\nRecord: {rec_id}\nSource: {access.get('selected_source_id')}\n"
                    f"Locator: {access.get('locator')}\nURL: {access.get('url')}\n"
                    f"Access date: {access.get('accessed_on')}\nAccess status: {access_status}\n"
                    f"Claim verification: {claim_status} (no semantic match completed)\n"
                    f"Compact extracted-page excerpt (max 20 words; for human review only): {excerpt}\n",
                    encoding="utf-8", newline="\n",
                )
        row = {
            "iso3": iso,
            "disposition": audit.get("disposition", "unresolved-limited"),
            "source_count": audit.get("scope", {}).get("source_count", 0),
            "evidence_count": audit.get("scope", {}).get("evidence_count", 0),
            "pathway_count": audit.get("scope", {}).get("pathway_count", 0),
            "flagged_evidence_ids": [x["record_id"] for x in audit.get("evidence", []) if x.get("concerns")],
            "flagged_pathway_ids": [x["record_id"] for x in audit.get("pathways", []) if x.get("concerns")],
            "stale_gap_flags": len(audit.get("profile_review", {}).get("known_gaps_requiring_reconciliation", [])),
            "selected_record_id": rec_id,
            "selected_source_id": access.get("selected_source_id"),
            "source_access_status": access_status,
            "claim_verification": claim_status,
            "cited_passage_text_extracted": access.get("cited_passage_text_extracted", False),
        }
        rows.append(row)
    log_lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines() if log_path.exists() else []
    unique_attempts = max(0, len(log_lines) - 1)
    aggregate = {
        "audit_version": "2026-10-27.record-audit.v1",
        "scope": "Exact 146-country TEST_INPUTS.json manifest",
        "country_count": len(rows),
        "evidence_count": sum(x["evidence_count"] for x in rows),
        "pathway_count": sum(x["pathway_count"] for x in rows),
        "source_count": sum(x["source_count"] for x in rows),
        "selected_unique_url_attempts": unique_attempts,
        "source_access_status_counts": dict(Counter(x["source_access_status"] for x in rows)),
        "selected_claim_status_counts": dict(Counter(x["claim_verification"] for x in rows)),
        "verified_claims": sum(1 for base in manifest for item in read_json(OUT / f"{Path(base).parts[1]}.json")["evidence"] if item["claim_verification"] == "verified"),
        "access_log": "research/20261027_remediation/audit/source_access.log (ignored by .gitignore)",
        "excerpt_directory": "research/20261027_remediation/audit/source_documents/ (ignored by .gitignore)",
        "limitation": "A selected source URL was attempted for each country with a cited source. Successful fetch or locator-page text extraction is access-only; no semantic claim match was completed in this batch. Other evidence and pathways remain unresolved unless individually adjudicated.",
        "countries": rows,
    }
    (OUT / "aggregate.json").write_text(json.dumps(aggregate, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"finalized cached access outputs: {len(rows)} countries, {unique_attempts} unique-URL log rows, {dict(statuses)}")


def refresh_inventory_preserving_access(manifest: list[str], run_date: str) -> None:
    """Regenerate record screens with current labels/relative paths, retaining access work."""
    rows = []
    for base in manifest:
        iso = Path(base).parts[1]
        path = OUT / f"{iso}.json"
        old = read_json(path) if path.exists() else {}
        fresh = build_country(base, run_date)
        old_evidence = {x["record_id"]: x for x in old.get("evidence", [])}
        for item in fresh["evidence"]:
            prior = old_evidence.get(item["record_id"], {})
            for key in ("verification_method", "verification_attempt", "verification_note", "reopened_on"):
                if key in prior:
                    item[key] = prior[key]
            if prior.get("claim_verification") == "verified":
                item["claim_verification"] = "verified"
                item["record_review"] = prior.get("record_review", "source-passage-reviewed")
            elif prior.get("verification_attempt"):
                item["claim_verification"] = prior.get("claim_verification", item["claim_verification"])
            if prior.get("manual_adjudication"):
                item["manual_adjudication"] = prior["manual_adjudication"]
                item["recommendations"] = prior.get("recommendations", item["recommendations"])
                item["concerns"] = prior.get("concerns", item["concerns"])
        old_sources = {x["source_id"]: x for x in old.get("sources", [])}
        for item in fresh["sources"]:
            prior = old_sources.get(item["source_id"], {})
            for key in ("audit_access_attempt", "audit_accessed_on"):
                if key in prior:
                    item[key] = prior[key]
            if prior.get("this_audit_verification") in {"access-only", "unresolved", "verified-for-listed-claims"}:
                item["this_audit_verification"] = prior["this_audit_verification"]
            if prior.get("manual_verified_record_ids"):
                item["manual_verified_record_ids"] = prior["manual_verified_record_ids"]
        for key in ("selected_record_id", "source_access_review", "checks", "limitations"):
            if key in old:
                fresh[key] = old[key]
        if fresh.get("source_access_review"):
            chosen_id = fresh["source_access_review"].get("selected_record_id")
            chosen = next((x for x in fresh["evidence"] if x["record_id"] == chosen_id), None)
            if chosen and chosen.get("claim_verification") == "unresolved":
                chosen["claim_verification"] = fresh["source_access_review"].get("claim_verification", "unresolved")
        evidence_counts = Counter(x["claim_verification"] for x in fresh["evidence"])
        fresh["verification_summary"]["evidence_claims"] = dict(evidence_counts)
        fresh["verification_summary"]["source_passages_reopened_by_this_audit"] = sum(
            bool(x.get("audit_access_attempt", {}).get("cited_passage_text_extracted")) for x in fresh["sources"]
        )
        fresh["verification_summary"]["source_claims_verified_by_this_audit"] = evidence_counts.get("verified", 0)
        fresh["verification_summary"]["limitation"] = "Automated inventory was refreshed and prior access observations retained. Retrieved text remains access-only until a record-level passage is manually matched; all other claims remain unresolved unless individually adjudicated."
        fresh["findings"] = [x for x in fresh["findings"] if "No source passage is certified" not in x]
        if evidence_counts.get("verified", 0) == 0:
            fresh["findings"].append("No claim was manually source-verified in this refreshed inventory; source retrieval is not verification.")
        path.write_text(json.dumps(fresh, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
        rows.append(fresh)
    OUT.mkdir(parents=True, exist_ok=True)
    aggregate = {
        "audit_version": "2026-10-27.record-audit.v1",
        "scope": "Exact 146-country TEST_INPUTS.json manifest",
        "country_count": len(rows),
        "evidence_count": sum(x["scope"]["evidence_count"] for x in rows),
        "pathway_count": sum(x["scope"]["pathway_count"] for x in rows),
        "source_count": sum(x["scope"]["source_count"] for x in rows),
        "verified_claims": sum(1 for x in rows for item in x["evidence"] if item["claim_verification"] == "verified"),
        "selected_unique_url_attempts": max(0, len(ACCESS_LOG.read_text(encoding="utf-8", errors="replace").splitlines()) - 1) if ACCESS_LOG.exists() else 0,
        "limitation": "Inventory screens all 146 candidates; source access and claim verification remain separate. See per-country checks and ignored source_documents for excerpt-level review. Automated flags prioritize follow-up but do not establish error.",
        "countries": [],
    }
    for x in rows:
        access = x.get("source_access_review", {})
        aggregate["countries"].append({
            "iso3": x["iso3"], "disposition": x["disposition"],
            "source_count": x["scope"]["source_count"], "evidence_count": x["scope"]["evidence_count"],
            "pathway_count": x["scope"]["pathway_count"],
            "flagged_evidence_ids": [e["record_id"] for e in x["evidence"] if e.get("concerns")],
            "flagged_pathway_ids": [p["record_id"] for p in x["pathways"] if p.get("concerns")],
            "stale_gap_flags": len(x["profile_review"]["known_gaps_requiring_reconciliation"]),
            "selected_record_id": access.get("selected_record_id"), "selected_source_id": access.get("selected_source_id"),
            "source_access_status": access.get("source_access_status", "unresolved"),
            "claim_verification": access.get("claim_verification", "unresolved"),
            "cited_passage_text_extracted": access.get("cited_passage_text_extracted", False),
        })
    (OUT / "aggregate.json").write_text(json.dumps(aggregate, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"refreshed {len(rows)} country ledgers; retained {aggregate['selected_unique_url_attempts']} access attempts and {aggregate['verified_claims']} verified claim statuses")


AUDITOR_REVIEWS: dict[str, dict[str, str]] = {
    "UGA-E-109": {"status": "verified", "note": "The official PreventionWeb article record reproduces the abstract: 2018-2023 crisis policies restricted pastoral mobility and increased climate exposure. The journal full text was not obtained; the result is abstract-level and is not a causal estimate of vegetation or rainfall effects.", "patch": "Retain as an abstract-level source-reported finding; do not imply the full journal article or a causal effect was independently reviewed."},
    "HND-E-101": {"status": "verified", "note": "The cited Duke brief reports department-level rainfall-deficit associations with subsequent US family-unit apprehensions, with stronger estimated association at higher homicide rates. It describes associations, not causation.", "patch": "Retain the association wording and identify US family-unit apprehensions as the measured proxy outcome; avoid causal migration language."},
    "GEO-E-109": {"status": "verified", "note": "The cited regional South Caucasus profile states climate impacts compound conflict-related displacement, describes flood/drought/resource risks to displaced households, and lists much of Georgia among areas with many IDPs. The risk description is regional, not a Georgia subnational hazard estimate.", "patch": "Retain explicitly as a regional South Caucasus profile; do not imply the general climate-risk passage is mapped specifically within Georgia."},
    "BRA-E-111": {"status": "verified", "note": "ACAPS's January 2025 secondary review reports armed-group exploitation, recruitment and forced displacement worsening access/basic needs in drought-affected Amazon communities, especially in Amazonas; it relies on dated secondary sources.", "patch": "Retain as ACAPS's secondary reporting with source-period limits; do not state that drought caused armed-group violence."},
    "SSD-E-017": {"status": "unresolved", "note": "The retrieved UN Climate Security Mechanism page contains a short summary of livelihood disruption, migration, resource-based conflict and response priorities, but not the cited brief's specific recruitment-incentive or elite-exploitation mechanisms.", "patch": "Narrow to the mechanisms and responses actually stated in the page summary, or inspect the linked full brief before retaining recruitment and elite-exploitation pathways."},
    "NGA-E-026": {"status": "verified", "note": "SIPRI page 13 states that armed conflict and Lake Chad military operations sometimes worsen livelihood insecurity and climate vulnerability; evacuations, fish-market closures and movement restrictions reduce fishing/water/pasture access. The evidence is local and operational.", "patch": "Retain the Lake Chad/Nigeria scope and distinguish military restrictions from climate effects; do not generalize this mechanism nationally."},
    "MOZ-E-016": {"status": "unresolved", "note": "The extracted cited-page window on physical PDF page 5 contains methodology and references but not the claim about Mecufi IDP pressure or mangrove cutting; the full claim was not matched.", "patch": "Keep provisional and narrow only after the exact Mecufi passage is located; otherwise exclude the mangrove/resource-pressure clause."},
    "LBY-E-019": {"status": "verified", "note": "SIPRI's Libya fact sheet describes inequitable GMR water management as a source of communal contestation and Fezzan exclusion grievances, including protester sabotage of pumps that reduced output. This is a source-reported example, not a quantified climate-conflict effect.", "patch": "Retain the named Fezzan/GMR example and avoid attributing the contestation itself to climate change."},
    "CAF-E-017": {"status": "verified", "note": "NUPI's CAR fact sheet reports illegal taxation and service demands by armed actors along transhumance corridors, worsening farmer-herder tensions and weakening local dispute resolution. This is a reported conflict mechanism, not evidence that climate stress caused it.", "patch": "Retain as a bounded armed-actor governance mechanism; do not frame it as a climate-caused conflict."},
    "AFG-E-024": {"status": "unresolved", "note": "The extracted page-3 window supports only a general statement that competition may increase when limited water availability meets poor management and climate stress. It does not substantiate the claim's Iran/dam/cooperation details.", "patch": "Narrow to the general conditional water-competition statement supported by the retrieved page, or inspect the exact Iran/transboundary-cooperation passage before retaining those details."},
    "ZWE-E-102": {"status": "unresolved", "note": "The retrieved PDF page-6 text discusses drought-related food and water insecurity but did not contain the specified GBV, child-marriage or long water-collection/sexual-violence passage. The cited page/claim fit remains unverified.", "patch": "Do not retain the GBV/sexual-violence clauses as verified from this locator; locate an exact protection-risk passage or remove them."},
    "VNM-E-111": {"status": "verified", "note": "UNICEF Innocenti's Viet Nam case study reports that Typhoon Yagi destroyed WASH facilities, increasing girls' GBV exposure, with some walking up to 10 km for water. The passage is a source-reported protection risk, not a measured incidence estimate.", "patch": "Retain as a dated Typhoon Yagi case-study risk report; do not imply measured GBV incidence."},
    "TJK-E-104": {"status": "unresolved", "note": "The retrieved article passage describes May 2021 water-infrastructure disputes, summer shortages, poor management and a participant analysis expecting climate change to increase tensions. It does not establish that the described disputes preceded the April 2021 clashes or that agreement breaches eroded trust.", "patch": "Remove the April-clash sequence and agreement-breach/trust clause unless their exact cited passage is verified; retain only the supported water-management and conditional climate-stress discussion."},
    "SLV-E-109": {"status": "verified", "note": "The cited WFP/SIPRI case-study passage describes a severe drought, losses of most maize harvests among small-scale farmers, low social cohesion associated with gang conflict, and a theory of change for rural resilience. This is historical, qualitative case-study evidence.", "patch": "Retain the historical Dry Corridor case-study context; distinguish the source's theory of change and reported conditions from a causal impact estimate."},
    "NPL-E-106": {"status": "unresolved", "note": "The extracted physical PDF page 4 supports overcrowded temporary camps, limited basic services and heightened protection risks for women, children, older people and people with disabilities. The cited page 5 objectives on violence protection/equal access were not extracted.", "patch": "Limit to the page-4 needs statement or separately verify page 5 before retaining the response-priority clause."},
    "MWI-E-103": {"status": "unresolved", "note": "The extracted PDF page 23 reports El Niño-related livelihood stress and crisis protection risks, but not the claimed children joining guardians' casual work, school absenteeism and child labour details.", "patch": "Remove or qualify the child-work/school-absence clause until its cited education/protection passage is verified."},
    "MRT-E-102": {"status": "unresolved", "note": "The URL returned current DPPA site/homepage text rather than the cited Mauritania climate-security executive summary; no matching host-refugee passage was obtained.", "patch": "Replace the mutable/homepage URL with the exact Mauritania report PDF or archive and recheck; do not treat the current page as evidence."},
    "MLI-E-112": {"status": "verified", "note": "The UNDP story reports Dembala residents' accounts of dry-season pump/well failure, water scarcity and conflict over water, and states that rehabilitated water points restored drinking and irrigation access. This is an attributed community account and project-output report, not an independent impact evaluation.", "patch": "Retain attribution to the named residents and UNDP's reported project output; do not present the story as an evaluated causal impact."},
    "MDG-E-111": {"status": "verified", "note": "UNICEF's June 2026 Gezani story reports 761 schools damaged, nearly 60,000 children's learning disrupted, and 20,854 people in temporary displacement sites where protection risks intensified. These are source-reported event figures.", "patch": "Retain the source date and event-specific figures; describe protection concerns as reported risks, not measured incidence."},
    "KGZ-E-108": {"status": "verified", "note": "FAO's 10 May 2024 feature attributes stream drying and crop-to-cattle livelihood change to water scarcity in Ak-Bashat and quotes one farmer saying depletion can cause disputes. This is one local attributed account.", "patch": "Retain as a single farmer's account in Ak-Bashat; do not generalize to all Kyrgyz communities or treat it as independent causal evidence."},
    "KAZ-E-110": {"status": "verified", "note": "International Alert's field-study pages report seasonal transboundary irrigation disputes, information gaps, water allocation problems and damaged facilities in Kazakhstan/Kyrgyzstan study areas; it notes past border-conflict precedents and potential tension. It is not an observed climate-caused conflict estimate.", "patch": "Retain named study-area context and potential-risk framing; avoid asserting climate-caused violence."},
    "JOR-E-107": {"status": "verified", "note": "The Jordan roadmap states that climate risks exacerbate water insecurity and conditionally may increase disputes and anti-refugee sentiment, while also identifying management, extraction, regional challenges and population growth as drivers.", "patch": "Retain conditional forecast language and multiple drivers; distinguish roadmap risk analysis from observed future outcomes."},
    "IND-E-110": {"status": "unresolved", "note": "The article URL returned a reCAPTCHA interstitial rather than article text. Its methods, sample denominators and adjusted odds ratios were not checked against the source.", "patch": "Keep the numerical and association summary provisional until the full article or publisher-authorized copy is accessible; do not claim this audit verified its estimates."},
    "MYS-E-106": {"status": "verified", "note": "The cited ISIS Malaysia research note states that climate-induced displacement can remove legal/social/economic protections and that children, women and older people face heightened exposure where displacement governance is limited. This is the report's analytical proposition, not a measured outcome estimate.", "patch": "Retain as a research-note proposition and preserve its conditional scope; do not present as a measured causal effect."},
    "MNG-E-102": {"status": "unresolved", "note": "The extracted printed pages 44-45 discuss urban and short-distance migration but do not show the cited Otor grazing movement, local-user disputes or movement-monitoring passage (which also cites a later page).", "patch": "Do not use this extracted passage to substantiate Otor/dispute/monitoring details; locate the cited later page and narrow the claim to the verified migration distinction."},
    "CIV-E-103": {"status": "unresolved", "note": "Only physical PDF page 5 was extracted. It supports the Bafing climatic baseline, but not the claim's dry-season resource concentration, crop damage, named communes and farmer-herder tensions on the other cited pages.", "patch": "Narrow to the climatic baseline in the extracted passage or verify the exact pages 8 and 11 before retaining the conflict mechanism."},
    "COL-E-102": {"status": "unresolved", "note": "The retrieved PDF pages 9-11 describe historical post-demobilization deforestation and dissident-group strategies, but do not contain the cited 2024 El Niño dryness/clearing/negotiation-leverage analysis from pages 14-15.", "patch": "Do not retain the El Niño-specific link as verified from these pages; verify pages 14-15 or remove that clause."},
    "BGD-E-111": {"status": "verified", "note": "The 2025-26 JRP reports that heavy rains caused more than 1,500 landslides in Cox's Bazar camps in 2024, killing 12 Rohingya refugees/FDMNs and damaging hundreds of shelters. This is an event report, not an attribution study.", "patch": "Retain the dated event figures and Cox's Bazar camp scope; do not attribute the 2024 rain event to climate change without a separate source."},
    "AGO-E-101": {"status": "verified", "note": "The UN Secretary-General report paragraph 32 states that 17 August clashes in Namibe occurred over access to a water dam amid prolonged drought, with 12-20 killed and thousands displaced. Communities remain unnamed, and this audit verifies the report's assertion, not independent event corroboration.", "patch": "Retain attribution to the UN report and its uncertainty range; do not add community names or imply independent corroboration."},
    "XKX-E-006": {"status": "verified", "note": "Kosovo's NDC states that drought, water stress, flooding and weak agricultural adaptation could exacerbate livelihood threats and increase conflict/social-tension risk over natural-resource access. It is a conditional assessment, not an observed conflict count.", "patch": "Retain the conditional 'could' framing and distinguish the NDC's risk assessment from observed incidence."},
}


SOM_REVIEWS: dict[str, dict[str, str]] = {
    "SOM-E-004": {"status": "verified", "source_id": "SOM-SRC-006", "method": "Opened the complete FAO SWALIM Q1 2026 newsletter PDF and reviewed physical PDF page 1 on 2026-10-27.", "note": "The page reports severe/extreme drought expanding during January-February, localized improvement, and persistent severe conditions in named southern regions in March; this is a Q1 snapshot.", "patch": "Retain as a dated, spatially uneven Q1 2026 drought snapshot; do not imply anthropogenic attribution."},
    "SOM-E-007": {"status": "unresolved", "source_id": "SOM-SRC-007", "method": "Opened the live FAO GIEWS country brief on 2026-10-27; the mutable page showed Reference Date 2026-09-15, not the cited 2026-03-11 historical edition.", "note": "The URL no longer exposes the cited 11 March 2026 edition or its 2025 Deyr livestock passage; the claim was not reverified.", "patch": "Supply an archived 2026-03-11 GIEWS brief or update the claim from the current dated edition; keep this claim unresolved."},
    "SOM-E-009": {"status": "verified", "source_id": "SOM-SRC-008", "method": "Opened the complete 14 May 2026 IPC projection-update PDF and reviewed physical pages 1-2 on 2026-10-27.", "note": "The report projects about 6 million people, 31% of the analysed population, in IPC Phase 3+ during April-June 2026 and attributes deterioration to interacting climate, economic, conflict and assistance factors. The period has passed.", "patch": "Keep as a dated April-June 2026 projection, not a current classification or observed October caseload."},
    "SOM-E-010": {"status": "verified", "source_id": "SOM-SRC-008", "method": "Opened the complete 14 May 2026 IPC projection-update PDF and reviewed physical pages 1-2 on 2026-10-27.", "note": "The report projects nearly 1.88 million children aged 6-59 months needing treatment for acute malnutrition during 2026, with interacting drivers; it is a full-year projection, not an observed caseload or climate-attributable estimate.", "patch": "Retain the 2026 annual projection and age range; do not label the projected total as observed or climate-attributable."},
    "SOM-E-011": {"status": "verified", "source_id": "SOM-SRC-008", "method": "Opened the complete 14 May 2026 IPC projection-update PDF and reviewed physical page 13, Annex 1, on 2026-10-27.", "note": "The most-likely scenario showed no Phase 5 population in Burhakaba; the source describes a conditional famine risk only under a worst-case combination including failed rains, higher prices and no assistance scale-up. The forecast period has passed.", "patch": "Retain the conditional worst-case scenario and its assumptions; never restate this as an observed Famine classification."},
    "SOM-E-013": {"status": "verified", "source_id": "SOM-SRC-005", "method": "Opened the complete EIP publisher PDF and reviewed Executive Summary physical pages 4-6 and physical page 40, section 3.3, on 2026-10-27.", "note": "The report's Hirshabelle/Galmudug assessment treats climate stress as interacting with pre-existing drivers; stakeholders did not identify climate as a direct cause of conflict. This is a qualitative local analysis.", "patch": "Correct locator to physical page 40 section 3.3 plus Executive Summary pages 4-6; retain explicit non-direct-causality and local scope."},
    "SOM-E-015": {"status": "unresolved", "source_id": "SOM-SRC-010", "method": "Opened the cited UNDP adaptation project page on 2026-10-27; it returned a JavaScript-required shell without the cited project-summary passage.", "note": "The stated institutional-capacity constraint was not matched to readable cited text.", "patch": "Retain unresolved until a readable UNDP project record or archived project document is available."},
    "SOM-E-016": {"status": "unresolved", "source_id": "SOM-SRC-010", "method": "Opened the cited UNDP adaptation project page on 2026-10-27; it returned a JavaScript-required shell without the cited location paragraph.", "note": "The asserted security influence on programme geography was not matched to readable cited text.", "patch": "Retain unresolved until the cited programme-location passage is obtained; do not infer security-driven site selection."},
    "SOM-E-018": {"status": "verified", "source_id": "SOM-SRC-011", "method": "Opened the complete World Bank IEG Somalia CPF evaluation PDF and reviewed physical pages 88-89 on 2026-10-27.", "note": "IEG reports 51 community management systems and improved water access for 362,731 people by February 2023; it separately reports the flood/drought livelihoods indicator as partly achieved. Outputs and outcome indicators are distinct.", "patch": "Retain dated programme outputs and separate them from the partly achieved livelihood outcome; do not claim broader impact."},
    "SOM-E-019": {"status": "verified", "source_id": "SOM-SRC-011", "method": "Opened the complete World Bank IEG Somalia CPF evaluation PDF and reviewed physical page 118, printed page 86, on 2026-10-27.", "note": "IEG identifies fiscal space and capacity as constraints on service sustainability and warns rapid growth may over-stretch systems; this is not a quantified climate-loss estimate.", "patch": "Retain as IEG institutional/fiscal assessment, not a quantified climate-loss claim."},
    "SOM-E-106": {"status": "verified", "source_id": "SOM-SRC-102", "method": "Opened the complete NRC BRCiS III endline PDF and reviewed physical page 82, section 3.6, on 2026-10-27.", "note": "Residents in Jambaluul and Buula Madino, Afgoye, describe conflict blocking farms and market roads and compounding drought losses. This is local qualitative testimony, not climate-causes-conflict evidence.", "patch": "Retain the named-site attribution and non-causal direction; do not generalize beyond these BRCiS communities."},
    "SOM-E-107": {"status": "verified", "source_id": "SOM-SRC-102", "method": "Opened the complete NRC BRCiS III endline PDF and reviewed physical page 89, section 3.7.4, Table 38, on 2026-10-27.", "note": "The table reports 52.1% of 526 cooperative members, with 95% CI 39.0-65.1, saying conflict/insecurity prevented meeting attendance. This is a programme-member subgroup, not all households.", "patch": "Restore spacing and state 'At BRCiS's June 2026 endline, 52.1% of 526 surveyed cooperative members (95% CI 39.0-65.1) reported that conflict or insecurity prevented meeting attendance; this is not a share of all households.'"},
}


def apply_record_review(audit: dict[str, Any], record_id: str, review: dict[str, Any], run_date: str) -> bool:
    item = next((x for x in audit.get("evidence", []) if x["record_id"] == record_id), None)
    if item is None:
        return False
    source_id = review.get("source_id")
    ref = next((r for r in item.get("source_refs", []) if not source_id or r.get("source_id") == source_id), item.get("source_refs", [{}])[0])
    source_id = source_id or ref.get("source_id")
    source = next((s for s in audit.get("sources", []) if s.get("source_id") == source_id), {})
    old_access = audit.get("source_access_review", {})
    url = review.get("source_url") or source.get("url")
    locator = review.get("locator") or ref.get("locator")
    method = review.get("verification_method") or review.get("method") or (
        (old_access.get("access_method") + "; human passage-to-claim comparison")
        if old_access.get("selected_record_id") == record_id and old_access.get("access_method")
        else "Manual comparison of the cited source passage with the full claim statement"
    )
    checked_on = review.get("accessed_on") or run_date
    status = "verified" if review.get("claim_verification") == "verified" or review.get("status") == "verified" else "unresolved"
    source_access_status = review.get("source_access_status")
    if not source_access_status:
        source_access_status = "passage-reviewed" if status == "verified" else "access-only"
    item["claim_verification"] = status
    if status == "verified":
        item["record_review"] = "manual-source-passage-review"
    elif source_access_status in {"unresolved", "document-fetched", "metadata-only"}:
        item["record_review"] = "manual-source-access-limited"
    else:
        item["record_review"] = "manual-passage-check-incomplete"
    item["reopened_on"] = checked_on
    item["verification_method"] = method
    item["verification_note"] = review.get("reason") or review.get("note", "")
    if review.get("verification_method") or review.get("source_url"):
        review_reason = review.get("reason") or review.get("note", "")
        recommendation = review.get("recommended_record_patch") or review.get("patch")
        item["manual_adjudication"] = {
            "status": review.get("claim_verification", review.get("status", status)),
            "reviewed_on": checked_on,
            "source_id": source_id,
            "source_url": url,
            "locator": locator,
            "verification_method": method,
            "reason": review_reason,
            "recommended_record_patch": recommendation,
            "coordinator_decision_ref": review.get("coordinator_decision_ref"),
        }
        if recommendation:
            item["recommendations"] = [recommendation]
        cues = item.get("screening_cues", [])
        if status == "verified":
            item["screening_cues_cleared_by_review"] = cues
            item["screening_cues"] = []
            item["concerns"] = [c for c in item.get("concerns", []) if c != "projection_not_obvious_in_compact_or_full_text"]
    attempt = {
        "record_id": record_id,
        "source_id": source_id,
        "url": url,
        "locator": locator,
        "accessed_on": checked_on,
        "verification_method": method,
        "source_access_status": source_access_status,
        "claim_verification": status,
        "cited_passage_text_extracted": source_access_status in {"access-only", "passage-reviewed"},
        "semantic_claim_match_completed": status == "verified",
        "manual_adjudication_completed": True,
        "verification_note": review.get("reason") or review.get("note", ""),
    }
    item["verification_attempt"] = attempt
    checks = audit.setdefault("checks", [])
    checks[:] = [x for x in checks if x.get("record_id") != record_id]
    checks.append({
        "record_id": record_id,
        "source_id": source_id,
        "locator": locator,
        "verification_status": status,
        "verification_method": method,
        "access_date": checked_on,
        "source_access_status": source_access_status,
        "cited_passage_text_extracted": attempt["cited_passage_text_extracted"],
        "semantic_claim_match_completed": status == "verified",
        "manual_adjudication_completed": True,
        "recommended_record_patch": review.get("recommended_record_patch") or review.get("patch"),
        "coordinator_decision_ref": review.get("coordinator_decision_ref"),
    })
    # Keep the one-country selected-source summary synchronized only when this
    # exact selected claim was manually adjudicated. An unrelated decision may
    # refer to a different record and must not overwrite the access result.
    if old_access.get("selected_record_id") == record_id:
        old_access.update({
            "source_access_status": source_access_status,
            "claim_verification": status,
            "cited_passage_text_extracted": attempt["cited_passage_text_extracted"],
            "semantic_claim_match_completed": status == "verified",
            "manual_adjudication_completed": True,
            "verification_method": method,
            "verification_note": review.get("reason") or review.get("note", ""),
        })
        audit["source_access_review"] = old_access
    if source:
        source.setdefault("manual_reviewed_record_ids", [])
        if record_id not in source["manual_reviewed_record_ids"]:
            source["manual_reviewed_record_ids"].append(record_id)
        if status == "verified":
            source["this_audit_verification"] = "verified-for-listed-claims"
            source.setdefault("manual_verified_record_ids", [])
            if record_id not in source["manual_verified_record_ids"]:
                source["manual_verified_record_ids"].append(record_id)
        elif source.get("this_audit_verification") != "verified-for-listed-claims":
            source["this_audit_verification"] = "access-only" if source_access_status == "access-only" else "unresolved"
    return True


def apply_manual_and_coordinator_reviews(manifest: list[str], run_date: str) -> None:
    overrides_path = ROOT / "research/20261027_remediation/overrides.json"
    overrides = read_json(overrides_path) if overrides_path.exists() else {"countries": {}}
    by_iso: dict[str, dict[str, Any]] = {}
    for base in manifest:
        iso = Path(base).parts[1]
        path = OUT / f"{iso}.json"
        audit = read_json(path)
        source_ref = "research/20261027_remediation/overrides.json"
        root_checks = 0
        root_decided_ids: set[str] = set()
        country_decisions = overrides.get("countries", {}).get(iso, {}).get("decisions", [])
        for decision in overrides.get("countries", {}).get(iso, {}).get("decisions", []):
            if decision.get("claim_verification") not in {"verified", "unresolved-limited", "access-only"}:
                continue
            status = decision["claim_verification"]
            review = {
                "claim_verification": "verified" if status == "verified" else "unresolved",
                "status": status,
                "reason": decision.get("reason", ""),
                "source_url": decision.get("source_url"),
                "locator": decision.get("locator"),
                "verification_method": decision.get("verification_method"),
                "accessed_on": decision.get("accessed_on", run_date),
                "coordinator_decision_ref": source_ref,
            }
            # An incomplete locator window is still an access observation;
            # a returned homepage, interstitial, or undecodable document is
            # not. Preserve this distinction in the audit ledger.
            reason_lower = (decision.get("reason") or "").lower()
            selected = audit.get("source_access_review", {})
            same_selected = any(
                rid == selected.get("selected_record_id")
                for rid in decision.get("record_ids", [])
            )
            if status == "verified":
                review["source_access_status"] = "passage-reviewed"
            elif any(term in reason_lower for term in (
                "no readable", "not obtained", "returned recaptcha", "homepage",
                "returned a publication landing", "connection was closed",
                "does not expose the cited", "live mutable page",
            )):
                review["source_access_status"] = "unresolved"
            elif same_selected and selected.get("cited_passage_text_extracted"):
                review["source_access_status"] = "access-only"
            else:
                # The coordinator reopened a passage but found it incomplete;
                # this is claim-unresolved even if the source itself was read.
                review["source_access_status"] = "access-only"
            for record_id in decision.get("record_ids", []):
                if apply_record_review(audit, record_id, review, run_date):
                    root_checks += 1
                    root_decided_ids.add(record_id)
        own = {**AUDITOR_REVIEWS, **(SOM_REVIEWS if iso == "SOM" else {})}
        own_checks = 0
        evidence_by_id = {x["record_id"]: x for x in audit.get("evidence", [])}
        source_by_id = {x["source_id"]: x for x in audit.get("sources", [])}
        for record_id, review in own.items():
            if not record_id.startswith(f"{iso}-") or record_id not in evidence_by_id:
                continue
            source_id = review.get("source_id") or evidence_by_id[record_id].get("source_refs", [{}])[0].get("source_id")
            source = source_by_id.get(source_id, {})
            review_fields = {
                "status": review["status"],
                "note": review.get("note", ""),
                "patch": review.get("patch"),
                "source_id": source_id,
                "source_url": source.get("url"),
                "locator": next((r.get("locator") for r in evidence_by_id[record_id].get("source_refs", []) if r.get("source_id") == source_id), None),
                "method": review.get("method") or (
                    (audit.get("source_access_review", {}).get("access_method", "") + "; human comparison of the candidate claim with the bounded locator excerpt")
                    if audit.get("source_access_review", {}).get("selected_record_id") == record_id
                    else "HTTPS full-source/locator review; manual comparison against the full candidate claim on 2026-10-27"
                ),
                "accessed_on": run_date,
                "source_access_status": "passage-reviewed" if review["status"] == "verified" else (
                    "unresolved" if record_id in {"IND-E-110", "MRT-E-102", "SOM-E-007", "SOM-E-015", "SOM-E-016"} else "access-only"
                ),
            }
            if apply_record_review(audit, record_id, review_fields, run_date):
                own_checks += 1
        # The coordinator's exact verified-record whitelist is authoritative
        # for passage-reviewed legacy IDs even when the matching country
        # decision records a recommendation without a claim_verification key.
        # Only IDs present in this 146-country legacy evidence inventory are
        # integrated here; remediation-only records remain in the override and
        # downstream candidate assembly.
        whitelist = set(overrides.get("rules", {}).get("verified_record_ids", []))
        evidence_by_id = {x["record_id"]: x for x in audit.get("evidence", [])}
        source_by_id = {x["source_id"]: x for x in audit.get("sources", [])}
        decision_by_record = {
            rid: decision
            for decision in country_decisions
            for rid in decision.get("record_ids", [])
        }
        for record_id in sorted(whitelist):
            if not record_id.startswith(f"{iso}-") or record_id not in evidence_by_id:
                continue
            if record_id in root_decided_ids or record_id in own:
                continue
            decision = decision_by_record.get(record_id, {})
            refs = evidence_by_id[record_id].get("source_refs", [])
            source = next(
                (s for s in audit.get("sources", []) if decision.get("source_url") and s.get("url") == decision.get("source_url")),
                None,
            )
            source_id = decision.get("source_id") or (source or {}).get("source_id")
            ref = next((r for r in refs if not source_id or r.get("source_id") == source_id), refs[0] if refs else {})
            source_id = source_id or ref.get("source_id")
            source = source_by_id.get(source_id, source or {})
            method = decision.get("verification_method") or (
                "Coordinator verified-record whitelist in research/20261027_remediation/overrides.json#rules.verified_record_ids; no more specific record-level method was recorded."
            )
            review = {
                "status": "verified",
                "claim_verification": "verified",
                "source_access_status": "passage-reviewed",
                "source_id": source_id,
                "source_url": decision.get("source_url") or source.get("url"),
                "locator": decision.get("locator") or ref.get("locator"),
                "verification_method": method,
                "accessed_on": decision.get("accessed_on", run_date),
                "reason": decision.get("reason") or "The coordinator's exact verified-record whitelist includes this legacy evidence ID; this finding applies only to the listed record.",
                "recommended_record_patch": decision.get("recommended_record_patch"),
                "coordinator_decision_ref": source_ref,
            }
            if apply_record_review(audit, record_id, review, run_date):
                root_checks += 1
                root_decided_ids.add(record_id)
        if iso == "ATG":
            access = audit.get("source_access_review", {})
            if access.get("selected_record_id") == "ATG-E-110":
                access.update({
                    "source_access_status": "document-fetched",
                    "claim_verification": "unresolved",
                    "cited_passage_text_extracted": False,
                    "semantic_claim_match_completed": False,
                    "error_or_limit": "HTTP 200 UTF-16 HTML/XML response was decoded as UTF-8 with NULs/markup; no readable cited passage obtained.",
                    "access_method": "HTTPS GET; response Content-Type text/html was UTF-16 with an XML declaration; UTF-8 decoder did not yield readable source text.",
                })
                record = evidence_by_id.get("ATG-E-110")
                if record:
                    record["claim_verification"] = "unresolved"
                    record["record_review"] = "source-access-failed-readable-text"
                    record["verification_method"] = access["access_method"]
                    record["verification_note"] = access["error_or_limit"]
                    record["verification_attempt"] = {**access, "record_id": "ATG-E-110", "source_id": access.get("selected_source_id"), "url": access.get("url"), "locator": access.get("locator"), "manual_adjudication_completed": False}
                    for check in audit.get("checks", []):
                        if check.get("record_id") == "ATG-E-110":
                            check.update({"verification_status": "unresolved", "source_access_status": "document-fetched", "cited_passage_text_extracted": False, "semantic_claim_match_completed": False, "verification_method": access["access_method"]})
                    source = source_by_id.get(access.get("selected_source_id"))
                    if source:
                        source["this_audit_verification"] = "unresolved"
                        source["audit_access_attempt"] = access
                audit["limitations"] = [x for x in audit.get("limitations", []) if "ATG-E-110" not in x]
                audit["limitations"].append("ATG-E-110: source server returned UTF-16 HTML/XML that was not decoded into readable cited text; claim remains unresolved.")
        count = Counter(x["claim_verification"] for x in audit.get("evidence", []))
        audit["verification_summary"]["evidence_claims"] = dict(count)
        audit["verification_summary"]["source_claims_verified_by_this_audit"] = count.get("verified", 0)
        audit["verification_summary"]["source_passages_reopened_by_this_audit"] = sum(
            bool(s.get("audit_access_attempt", {}).get("cited_passage_text_extracted")) or bool(s.get("manual_verified_record_ids"))
            for s in audit.get("sources", [])
        )
        audit["verification_summary"]["limitation"] = "Selected source access and manually adjudicated record-level passages are listed separately. Verification applies only to individually listed claims; all remaining evidence/pathways and the country bank as a whole remain unresolved-limited."
        audit["findings"] = [
            finding for finding in audit.get("findings", [])
            if not finding.startswith("No source passage is certified as verified")
            and not finding.startswith("No claim was manually source-verified")
            and not finding.startswith("Record-level passage review was completed")
        ]
        if count.get("verified", 0):
            audit["findings"].append(
                f"Record-level passage review was completed for {count['verified']} listed evidence claims only; other claims, pathways and the country bank remain unresolved-limited."
            )
        else:
            audit["findings"].append(
                "No evidence claim was manually matched to a readable cited passage in this country audit; source access alone does not verify claims."
            )
        audit["checks"].sort(key=lambda x: (x.get("record_id", ""), x.get("source_id", "")))
        audit["record_ids"] = [x["record_id"] for x in audit.get("evidence", []) + audit.get("pathways", [])]
        audit["coordinator_review_summary"] = {
            "source_file": source_ref,
            "coordinator_decisions_integrated": root_checks,
            "auditor_manual_reviews_integrated": own_checks,
            "coverage_limit": "Record-level only; does not certify all claims, source identity across all records, any pathway as a whole, or the country bank overall.",
        }
        if iso == "SOM":
            audit["source_metadata_recommendations"] = [
                {"source_id": "SOM-SRC-005", "field": "publication_date", "candidate_value": "2024", "recommended_value": "2024-09-02", "basis": "Publisher PDF cover date."},
                {"source_id": "SOM-SRC-005", "field": "license_status", "candidate_value": "open", "recommended_value": "permission-required", "basis": "Publisher terms allow educational/non-profit reuse with acknowledgement and require prior written permission for commercial/other uses; do not label unrestricted open."},
                {"source_id": "SOM-SRC-007", "field": "source_version_url", "candidate_value": source_by_id.get("SOM-SRC-007", {}).get("url"), "recommended_value": "Archived 2026-03-11 GIEWS edition or a direct dated attachment", "basis": "The live mutable page shows Reference Date 2026-09-15 and does not expose the cited historical edition."},
            ]
        path = OUT / f"{iso}.json"
        path.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
        by_iso[iso] = audit
    rebuild_aggregate_from_ledgers(by_iso)
    verified = sum(1 for audit in by_iso.values() for e in audit.get("evidence", []) if e.get("claim_verification") == "verified")
    print(f"integrated coordinator and auditor record decisions for {len(by_iso)} countries; {verified} individually verified evidence records")


def rebuild_aggregate_from_ledgers(by_iso: dict[str, dict[str, Any]]) -> None:
    countries = []
    evidence_counts = Counter()
    for iso, audit in sorted(by_iso.items()):
        evidence_counts.update(x["claim_verification"] for x in audit.get("evidence", []))
        access = audit.get("source_access_review", {})
        countries.append({
            "iso3": iso,
            "disposition": audit.get("disposition", "unresolved-limited"),
            "source_count": audit["scope"]["source_count"],
            "evidence_count": audit["scope"]["evidence_count"],
            "pathway_count": audit["scope"]["pathway_count"],
            "flagged_evidence_ids": [e["record_id"] for e in audit.get("evidence", []) if e.get("concerns")],
            "screening_cue_evidence_ids": [e["record_id"] for e in audit.get("evidence", []) if e.get("screening_cues")],
            "flagged_pathway_ids": [p["record_id"] for p in audit.get("pathways", []) if p.get("concerns")],
            "stale_gap_flags": len(audit.get("profile_review", {}).get("known_gaps_requiring_reconciliation", [])),
            "selected_record_id": access.get("selected_record_id"),
            "selected_source_id": access.get("selected_source_id"),
            "source_access_status": access.get("source_access_status", "unresolved"),
            "selected_claim_verification": access.get("claim_verification", "unresolved"),
            "cited_passage_text_extracted": access.get("cited_passage_text_extracted", False),
            "individually_verified_record_ids": [e["record_id"] for e in audit.get("evidence", []) if e.get("claim_verification") == "verified"],
            "individually_unresolved_record_ids": [e["record_id"] for e in audit.get("evidence", []) if e.get("manual_adjudication", {}).get("status") in {"unresolved", "unresolved-limited"}],
        })
    all_audits = list(by_iso.values())
    legacy_evidence_ids = {e["record_id"] for a in all_audits for e in a.get("evidence", [])}
    legacy_pathway_ids = {p["record_id"] for a in all_audits for p in a.get("pathways", [])}
    overrides_path = ROOT / "research/20261027_remediation/overrides.json"
    overrides = read_json(overrides_path) if overrides_path.exists() else {"countries": {}}
    added_evidence_ids = sorted({
        e["evidence_id"]
        for c in overrides.get("countries", {}).values()
        for e in c.get("add_evidence", [])
    } - legacy_evidence_ids)
    added_pathway_ids = sorted({
        p["pathway_id"]
        for c in overrides.get("countries", {}).values()
        for p in c.get("add_pathways", [])
    } - legacy_pathway_ids)
    aggregate = {
        "audit_version": "2026-10-27.record-audit.v1",
        "scope": "Exact 146-country TEST_INPUTS.json manifest",
        "country_count": len(countries),
        "evidence_count": sum(x["scope"]["evidence_count"] for x in all_audits),
        "pathway_count": sum(x["scope"]["pathway_count"] for x in all_audits),
        "source_count": sum(x["scope"]["source_count"] for x in all_audits),
        "evidence_claim_verification_counts": dict(evidence_counts),
        "selected_unique_url_attempts": max(0, len(ACCESS_LOG.read_text(encoding="utf-8", errors="replace").splitlines()) - 1) if ACCESS_LOG.exists() else 0,
        "verified_claims": evidence_counts.get("verified", 0),
        "remediation_ledger_comparison": {
            "basis": "Legacy audit scope plus unique add_evidence/add_pathways IDs in overrides.json; arithmetic comparison only, not a second independent validation of assembled files.",
            "legacy_audit_evidence_count": sum(x["scope"]["evidence_count"] for x in all_audits),
            "legacy_audit_pathway_count": sum(x["scope"]["pathway_count"] for x in all_audits),
            "additional_evidence_ids_in_remediation_ledger": added_evidence_ids,
            "additional_evidence_count": len(added_evidence_ids),
            "additional_pathway_ids_in_remediation_ledger": added_pathway_ids,
            "additional_pathway_count": len(added_pathway_ids),
            "expected_remediated_evidence_count": sum(x["scope"]["evidence_count"] for x in all_audits) + len(added_evidence_ids),
            "expected_remediated_pathway_count": sum(x["scope"]["pathway_count"] for x in all_audits) + len(added_pathway_ids),
        },
        "access_log": "research/20261027_remediation/audit/source_access.log (ignored by .gitignore)",
        "excerpt_directory": "research/20261027_remediation/audit/source_documents/ (ignored by .gitignore)",
        "limitation": "All 146 candidates were inventoried and one cited source per country was attempted. Selected-page access is not verification. Only listed records marked verified received manual passage-to-claim review; all other claims/pathways and every bank-level disposition remain unresolved-limited.",
        "countries": countries,
    }
    (OUT / "aggregate.json").write_text(json.dumps(aggregate, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def match_access_rows(raw: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in raw.get("access_audit", []):
        sid = row.get("source_id")
        if sid:
            rows[sid].append(row)
    return rows


def source_status(rows: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    compact = []
    methods = set()
    for row in rows:
        method = row.get("access_method") or row.get("method") or "not-recorded"
        methods.add(method)
        compact.append({
            "access_method": method,
            "locator": row.get("locator"),
            "notes": row.get("notes"),
            "reuse_terms": row.get("reuse_terms"),
            "recorded_in_intake": True,
        })
    if methods.intersection({"full-text", "official-excerpt"}):
        return "access-only", compact
    return "unresolved", compact


def ids_for_sources(records: list[dict[str, Any]]) -> dict[str, list[str]]:
    result: dict[str, list[str]] = defaultdict(list)
    for record in records:
        rid = record.get("evidence_id") or record.get("pathway_id")
        refs = record.get("source_refs", [])
        if not refs:
            refs = [{"source_id": sid} for sid in record.get("supporting_source_ids", [])]
        for ref in refs:
            if ref.get("source_id"):
                result[ref["source_id"]].append(rid)
    return result


def evidence_review(e: dict[str, Any], access_by_source: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    refs = e.get("source_refs", [])
    text = f"{e.get('statement', '')} {e.get('compact_statement', '')}"
    classes = e.get("evidence_class")
    concerns = []
    screening_cues = []
    recommendations = []
    if e.get("evidence_status") == "projected":
        if not e.get("scenario"):
            concerns.append("projected_record_missing_scenario")
            recommendations.append("Add the source's scenario or explicitly say the source does not specify one in both statements; exclude the projection if its source passage cannot be reopened.")
        if not any(h in {"near-term", "medium-term", "long-term"} for h in e.get("time_horizons", [])):
            concerns.append("projected_record_missing_future_horizon")
        if not FORECAST.search(text):
            concerns.append("projection_not_obvious_in_compact_or_full_text")
    if NUMBER.search(text):
        screening_cues.append("numeric_expression_detected_for_human_check")
    if PROGRAMME.search(text) and OUTCOME.search(text):
        screening_cues.append("programme_intent_and_outcome_terms_co-occur")
    if classes == "direct-climate-fcv" or e.get("analytical_role") == "direct-climate-fcv":
        screening_cues.append("direct_climate_fcv_role_requires_causal_scope_review")
    if not refs:
        concerns.append("no_source_reference")
        recommendations.append("Exclude the claim until a traceable source and locator are supplied.")
    missing_access_rows = []
    for ref in refs:
        if not access_by_source.get(ref.get("source_id")):
            missing_access_rows.append(ref.get("source_id"))
        if not ref.get("locator"):
            concerns.append(f"locator_missing:{ref.get('source_id')}")
    status = "access-only" if refs and all(
        any((r.get("access_method") or r.get("method")) in {"full-text", "official-excerpt"} for r in access_by_source.get(ref.get("source_id"), []))
        for ref in refs
    ) else "unresolved"
    if not recommendations:
        recommendations.append("No wording change is indicated by the record-only check; keep the claim provisional until its cited passage is independently reopened.")
    return {
        "record_id": e["evidence_id"],
        "record_review": "automated-field-and-reference-screen",
        "claim_verification": status,
        "reopened_on": None,
        "source_refs": refs,
        "geographies": e.get("geographies", []),
        "affected_groups": e.get("affected_groups", []),
        "evidence_class": classes,
        "analytical_role": e.get("analytical_role"),
        "interaction_direction": e.get("interaction_direction"),
        "evidence_status": e.get("evidence_status"),
        "time_horizons": e.get("time_horizons", []),
        "scenario": e.get("scenario"),
        "compact_statement": e.get("compact_statement"),
        "concerns": sorted(set(concerns)),
        "screening_cues": sorted(set(screening_cues)),
        "source_refs_without_inherited_access_rows": sorted(set(x for x in missing_access_rows if x)),
        "recommendations": recommendations,
    }


def pathway_review(p: dict[str, Any], evidence_by_id: dict[str, dict[str, Any]]) -> dict[str, Any]:
    support = p.get("supporting_evidence_ids", [])
    missing = sorted(set(support) - evidence_by_id.keys())
    locs: dict[str, list[str]] = {}
    for field in ("pressure", "impact", "mediator", "consequence"):
        locs[field] = p.get("link_evidence", {}).get(field, [])
    linked = set().union(*(set(v) for v in locs.values())) if locs else set()
    concerns = []
    recommendations = []
    if missing:
        concerns.append("supporting_evidence_missing")
        recommendations.append("Remove missing evidence IDs or restore their records before using the pathway.")
    if set(support) != linked:
        concerns.append("supporting_and_link_evidence_sets_differ")
    if p.get("interaction_direction") in {"fcv-to-climate", "bidirectional"}:
        concerns.append("reverse_or_bidirectional_mechanism_requires_support_review")
        recommendations.append("Keep the reverse mechanism bounded to the named institution, population and place supported by its cited evidence; do not infer violence from climate vulnerability.")
    geo_sets = [(eid, set(evidence_by_id.get(eid, {}).get("geographies", []))) for eid in support if eid in evidence_by_id]
    pathway_geo = set(p.get("geographies", []))
    out_of_scope = [eid for eid, gs in geo_sets if gs and pathway_geo and not gs.intersection(pathway_geo)]
    if out_of_scope:
        concerns.append("potential_geographic_scope_mismatch")
        recommendations.append("Retain only evidence whose documented geography supports the pathway location; otherwise narrow the pathway or keep the evidence standalone.")
    if not recommendations:
        recommendations.append("No structural linkage issue identified; review each cited passage for its specific causal link, alternatives and uncertainty before treating the pathway as verified.")
    return {
        "record_id": p["pathway_id"],
        "record_review": "automated-linkage-and-geography-screen",
        "claim_verification": "unresolved",
        "reopened_on": None,
        "supporting_evidence_ids": support,
        "link_evidence": locs,
        "geographies": p.get("geographies", []),
        "interaction_direction": p.get("interaction_direction"),
        "evidence_strength": p.get("evidence_strength"),
        "compact_statement": p.get("compact_statement"),
        "alternative_explanations": p.get("alternative_explanations", []),
        "uncertainty": p.get("uncertainty"),
        "potentially_out_of_scope_support_ids": out_of_scope,
        "missing_support_ids": missing,
        "concerns": concerns,
        "recommendations": recommendations,
    }


def build_country(base: str, run_date: str) -> dict[str, Any]:
    candidate = ROOT / base
    iso = candidate.parts[-3]
    evidence = read_json(candidate / "evidence.json")
    pathways = read_json(candidate / "pathways.json")
    sources = read_json(candidate / "sources.json")
    profile = read_json(candidate / "profile.json")
    review = read_json(candidate / "review.json")
    raw_path = next((ROOT / f"research/20261026_global_depth/{stage}/{iso}.json" for stage in ("phase1", "phase2") if (ROOT / f"research/20261026_global_depth/{stage}/{iso}.json").exists()), None)
    raw = read_json(raw_path) if raw_path else {}
    access = match_access_rows(raw)
    evidence_by_id = {e["evidence_id"]: e for e in evidence}
    evidence_audits = [evidence_review(e, access) for e in evidence]
    pathway_audits = [pathway_review(p, evidence_by_id) for p in pathways]
    source_to_records = ids_for_sources(evidence + pathways)
    source_audits = []
    for s in sources:
        status, inherited_access = source_status(access.get(s["source_id"], []))
        source_audits.append({
            "source_id": s["source_id"],
            "title": s.get("title"),
            "organization": s.get("organization"),
            "publication_date": s.get("publication_date"),
            "publication_date_basis": s.get("publication_date_basis"),
            "url": s.get("url"),
            "geographic_coverage": s.get("geographic_coverage", []),
            "temporal_coverage": s.get("temporal_coverage"),
            "accessed_on_in_source_record": s.get("accessed_on"),
            "license_status": s.get("license_status"),
            "records_using_source": sorted(source_to_records.get(s["source_id"], [])),
            "this_audit_verification": "unresolved",
            "prior_intake_access": status,
            "prior_access_rows": inherited_access,
            "reopened_on": None,
            "recommendation": "Check publisher/author, publication/version date, locator, geographic and temporal scope, actual cited passage and reuse terms before verifying any dependent claim.",
        })
    stale_gaps = []
    for gap in profile.get("known_gaps", []):
        text = gap.get("text", "")
        if pathways and re.search(r"\b(no|none|not)\b.*\b(pathway|mediat|assembled)\b", text, re.I):
            stale_gaps.append({"text": text, "recommendation": "Reconcile with the currently assembled pathway IDs or explain the narrower unresolved gap."})
    source_ids = {s.get("source_id") for s in sources}
    missing_sources = sorted({ref.get("source_id") for e in evidence for ref in e.get("source_refs", [])} - source_ids)
    status_counts = Counter(e["claim_verification"] for e in evidence_audits)
    all_refs = [r for e in evidence for r in e.get("source_refs", [])]
    findings = []
    if not pathways:
        findings.append("No structured pathway is assembled; interpret as a coverage limit, not evidence of no FCV mechanism.")
    if stale_gaps:
        findings.append("At least one known-gap statement appears inconsistent with the current pathway inventory.")
    if missing_sources:
        findings.append("One or more evidence source IDs are absent from this candidate's source metadata.")
    if any(a["concerns"] for a in evidence_audits + pathway_audits):
        findings.append("Structural record flags require targeted adjudication; they do not establish that a claim is false.")
    if any(a.get("screening_cues") for a in evidence_audits):
        findings.append("Automated numeric, programme-language and causal-role screening cues are follow-up prompts only; they are not findings of claim error.")
    findings.append("No source passage is certified as verified by this generated ledger. External claims remain provisional until the cited passage is reopened.")
    return {
        "audit_version": "2026-10-27.record-audit.v1",
        "iso3": iso,
        "candidate_path": base,
        "audited_on": run_date,
        "disposition": "unresolved-limited",
        "human_approval": "pending",
        "scope": {
            "includes_inherited_and_new_records": True,
            "exact_input_manifest": "research/20261026_global_depth/TEST_INPUTS.json",
            "source_count": len(sources),
            "evidence_count": len(evidence),
            "pathway_count": len(pathways),
            "evidence_source_reference_count": len(all_refs),
        },
        "method": [
            "Automated inventory read every source, evidence, pathway, profile and review record in the exact manifest candidate for this ISO.",
            "Automated screening compared source references, locators, geography fields, evidence class, direction, status, horizon and scenario; it checked pathway support IDs, link-evidence sets, geography fields, alternatives and uncertainty for follow-up.",
            "Raw extraction access rows are recorded only as inherited access observations. This generated screen does not treat snippets, HTTP success, prior access, or metadata as claim verification and does not replace semantic source review.",
        ],
        "verification_summary": {
            "evidence_claims": dict(status_counts),
            "pathway_claims": {"unresolved": len(pathway_audits)},
            "source_passages_reopened_by_this_audit": 0,
            "source_claims_verified_by_this_audit": 0,
            "limitation": "Record text and linkages were reviewed locally; no external passage is marked verified until that passage is reopened and checked against the claim.",
        },
        "findings": findings,
        "profile_review": {
            "coverage": profile.get("coverage", []),
            "known_gaps_requiring_reconciliation": stale_gaps,
            "review_status": profile.get("review_status"),
            "review_date": profile.get("review_date"),
        },
        "dossier_review": {
            "path": f"{base}/dossier.md",
            "automated_inventory_review": True,
            "limitation": "Dossier prose is checked against the candidate inventory, not independently certified source-by-source.",
        },
        "missing_source_metadata_ids": missing_sources,
        "sources": source_audits,
        "evidence": evidence_audits,
        "pathways": pathway_audits,
        "review_state": {
            "candidate_status": review.get("status"),
            "reviewer": review.get("reviewer"),
            "reviewed_on": review.get("reviewed_on"),
            "review_due": review.get("review_due"),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", default=AUDIT_DATE, help="Actual audit date, YYYY-MM-DD")
    parser.add_argument("--check", action="store_true", help="Validate generated inventory without writing")
    parser.add_argument("--reopen-sources", action="store_true", help="Attempt one highest-priority cited source per country; fetched text remains access-only")
    parser.add_argument("--finalize-access-pass", action="store_true", help="Build aggregate/index from completed access outputs without network requests")
    parser.add_argument("--fetch-review-excerpts", action="store_true", help="Re-fetch only previously text-extracted locators and save bounded excerpts for human review")
    parser.add_argument("--refresh-preserving-access", action="store_true", help="Regenerate inventory labels/paths while preserving all existing access and manual review fields")
    parser.add_argument("--apply-manual-reviews", action="store_true", help="Integrate this auditor's reviewed claims and coordinator decisions from overrides.json; no candidate records are edited")
    args = parser.parse_args()
    date.fromisoformat(args.date)
    manifest = read_json(MANIFEST)
    if len(manifest) != 146 or len(set(manifest)) != 146:
        raise SystemExit(f"Expected exactly 146 unique candidate paths, found {len(manifest)} entries.")
    rows = [build_country(base, args.date) for base in manifest]
    if {r["iso3"] for r in rows} != {Path(x).parts[1] for x in manifest}:
        raise SystemExit("Country ISO inventory does not match manifest.")
    if args.check:
        print(f"checked {len(rows)} countries; {sum(r['scope']['evidence_count'] for r in rows)} evidence; {sum(r['scope']['pathway_count'] for r in rows)} pathways")
        return
    if args.finalize_access_pass:
        finalize_cached_access_pass(manifest)
        return
    if args.fetch_review_excerpts:
        fetch_review_excerpts(manifest)
        return
    if args.refresh_preserving_access:
        refresh_inventory_preserving_access(manifest, args.date)
        return
    if args.apply_manual_reviews:
        apply_manual_and_coordinator_reviews(manifest, args.date)
        return
    if args.reopen_sources:
        reopen_selected_sources(manifest, args.date)
        return
    OUT.mkdir(parents=True, exist_ok=True)
    flagged = []
    for row in rows:
        path = OUT / f"{row['iso3']}.json"
        path.write_text(json.dumps(row, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
        flagged.append({
            "iso3": row["iso3"],
            "disposition": row["disposition"],
            "source_count": row["scope"]["source_count"],
            "evidence_count": row["scope"]["evidence_count"],
            "pathway_count": row["scope"]["pathway_count"],
            "flagged_evidence_ids": [x["record_id"] for x in row["evidence"] if x["concerns"]],
            "flagged_pathway_ids": [x["record_id"] for x in row["pathways"] if x["concerns"]],
            "stale_gap_flags": len(row["profile_review"]["known_gaps_requiring_reconciliation"]),
            "unverified_sources": sum(x["this_audit_verification"] != "verified" for x in row["sources"]),
        })
    (OUT / "aggregate.json").write_text(json.dumps({
        "audit_version": "2026-10-27.record-audit.v1",
        "scope": "Exact 146-country TEST_INPUTS.json manifest",
        "country_count": len(flagged),
        "evidence_count": sum(x["evidence_count"] for x in flagged),
        "pathway_count": sum(x["pathway_count"] for x in flagged),
        "source_count": sum(x["source_count"] for x in flagged),
        "verified_claims": 0,
        "limitation": "Automated screen only. Record-level semantic source review and independent passage verification remain incomplete; flags prioritize follow-up and do not establish claim error.",
        "countries": flagged,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {len(rows)} audit files to {OUT}")


if __name__ == "__main__":
    main()
