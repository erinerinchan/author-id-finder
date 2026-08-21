import os
import re
from urllib.parse import quote
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, Tuple

import requests


USER_AGENT_BASE = "HKUST-Author-ID-Finder/1.0"


def _build_headers() -> Dict[str, str]:
    contact = os.getenv("CONTACT_EMAIL", "").strip()
    user_agent = USER_AGENT_BASE if not contact else f"{USER_AGENT_BASE} ({contact})"
    return {
        "User-Agent": user_agent,
        "Accept": "application/json",
    }


def _safe_get(url: str, params: Optional[Dict[str, Any]] = None, headers: Optional[Dict[str, str]] = None) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    try:
        merged_headers = _build_headers()
        if headers:
            merged_headers.update(headers)
        resp = requests.get(url, params=params, headers=merged_headers, timeout=20)
        if resp.status_code >= 400:
            return None, f"HTTP {resp.status_code} from {url}"
        if not resp.text:
            return None, f"Empty response from {url}"
        content_type = (resp.headers.get("Content-Type") or "").lower()
        if "json" not in content_type:
            return None, f"Non-JSON response from {url} (content-type: {content_type or 'unknown'})"
        return resp.json(), None
    except requests.RequestException as exc:
        return None, str(exc)
    except ValueError as exc:
        return None, f"Invalid JSON from {url}: {exc}"


def _safe_get_text(url: str, params: Optional[Dict[str, Any]] = None, headers: Optional[Dict[str, str]] = None) -> Tuple[Optional[str], Optional[str]]:
    try:
        merged_headers = _build_headers()
        if headers:
            merged_headers.update(headers)
        resp = requests.get(url, params=params, headers=merged_headers, timeout=20)
        if resp.status_code >= 400:
            return None, f"HTTP {resp.status_code} from {url}"
        if not resp.text:
            return None, f"Empty response from {url}"
        return resp.text, None
    except requests.RequestException as exc:
        return None, str(exc)


def normalize_title(title: str) -> str:
    cleaned = re.sub(r"\s+", " ", title.lower()).strip()
    cleaned = re.sub(r"[^a-z0-9\s]", "", cleaned)
    return cleaned


def _name_signatures(name: str) -> List[Tuple[str, str]]:
    cleaned = re.sub(r"[^A-Za-z\s\.]", " ", name or "")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if not cleaned:
        return []

    tokens = [t for t in cleaned.replace(".", "").split(" ") if t]
    if not tokens:
        return []

    sigs: List[Tuple[str, str]] = []
    # Natural style: Given ... Surname
    sigs.append((tokens[-1].lower(), "".join(t[0].lower() for t in tokens[:-1] if t)))
    # Indexed style: Surname Initials
    if len(tokens) >= 2:
        sigs.append((tokens[0].lower(), "".join(t[0].lower() for t in tokens[1:] if t)))

    # Deduplicate while preserving order.
    dedup: List[Tuple[str, str]] = []
    for s in sigs:
        if s not in dedup:
            dedup.append(s)
    return dedup


def person_name_similarity(a: str, b: str) -> float:
    seq_sim = title_similarity(a, b)
    a_sigs = _name_signatures(a)
    b_sigs = _name_signatures(b)

    if not a_sigs or not b_sigs:
        return seq_sim

    for a_surname, a_initials in a_sigs:
        for b_surname, b_initials in b_sigs:
            if a_surname == b_surname:
                if a_initials and b_initials and (a_initials[0] == b_initials[0]):
                    return max(seq_sim, 0.95)
                return max(seq_sim, 0.8)

    return seq_sim


def title_similarity(a: str, b: str) -> float:
    a_norm = normalize_title(a)
    b_norm = normalize_title(b)
    if not a_norm or not b_norm:
        return 0.0
    return SequenceMatcher(None, a_norm, b_norm).ratio()


def normalize_orcid(orcid: str) -> str:
    raw = orcid.strip()
    raw = raw.replace("https://orcid.org/", "").replace("http://orcid.org/", "")
    return raw


def normalize_doi(doi: str) -> str:
    raw = doi.strip().lower()
    raw = raw.replace("https://doi.org/", "").replace("http://doi.org/", "")
    return raw


def _clean_query_text(value: str) -> str:
    return value.replace('"', "").strip()


def parse_scopus_author_id(raw_value: str) -> Optional[str]:
    raw = (raw_value or "").strip()
    if not raw:
        return None

    # Most common OpenAlex/Elsevier style: ...authorId=<digits>
    match = re.search(r"authorId=(\d+)", raw)
    if match:
        return match.group(1)

    # Elsevier API style: .../author_id/<digits>
    match = re.search(r"/author_id/(\d+)", raw)
    if match:
        return match.group(1)

    # Some payloads provide bare numeric IDs.
    if raw.isdigit():
        return raw

    # Common legacy Scopus style: 2-s2.0-<author_id>
    match = re.search(r"(\d{7,})$", raw)
    if match:
        return match.group(1)

    return None


def normalize_openalex_author_api_url(author_id: str) -> Optional[str]:
    raw = (author_id or "").strip()
    if not raw:
        return None

    if raw.startswith("https://api.openalex.org/authors/"):
        return raw

    if raw.startswith("https://openalex.org/"):
        suffix = raw.rsplit("/", 1)[-1]
        return f"https://api.openalex.org/authors/{suffix}"

    if re.fullmatch(r"A\d+", raw):
        return f"https://api.openalex.org/authors/{raw}"

    return raw


@dataclass
class IdentifierItem:
    value: Optional[str]
    profile_url: Optional[str]
    source: str
    confidence: str
    note: str = ""


@dataclass
class CandidateAuthor:
    display_name: str
    openalex_author_id: Optional[str]
    affiliation: str
    works_count: int
    matched_papers: int
    score: float
    evidence: List[str] = field(default_factory=list)
    orcid: Optional[str] = None
    scopus_author_id: Optional[str] = None
    scopus_source: str = ""
    wos_researcher_id: Optional[str] = None
    wos_profile_url: Optional[str] = None
    google_scholar_id: Optional[str] = None
    google_scholar_url: Optional[str] = None
    google_scholar_status: str = ""


@dataclass
class LookupResult:
    candidates: List[CandidateAuthor]
    source_warnings: List[str]


class AuthorIdLookupService:
    def __init__(self) -> None:
        self.scopus_api_key = os.getenv("SCOPUS_API_KEY", "").strip()
        self.serpapi_api_key = os.getenv("SERPAPI_API_KEY", "").strip()

    def search(self, title: str, author_query: str = "", year: Optional[int] = None, doi: str = "") -> LookupResult:
        source_warnings: List[str] = []
        doi_norm = normalize_doi(doi) if doi else ""

        openalex_candidates, openalex_warning = self._search_openalex(title, author_query, year, doi_norm)
        if openalex_warning:
            source_warnings.append(openalex_warning)

        if not openalex_candidates:
            if self.scopus_api_key:
                scopus_candidates = self._search_scopus_candidates(title, author_query, doi_norm, source_warnings)
                if scopus_candidates:
                    sorted_scopus = sorted(scopus_candidates, key=lambda c: c.score, reverse=True)
                    for candidate in sorted_scopus[:12]:
                        self._enrich_orcid(candidate, source_warnings)
                    return LookupResult(candidates=sorted_scopus, source_warnings=source_warnings)
            return LookupResult(candidates=[], source_warnings=source_warnings)

        sorted_candidates = sorted(openalex_candidates, key=lambda c: c.score, reverse=True)

        # Enrich the top scored candidates shown for disambiguation.
        for candidate in sorted_candidates[:12]:
            self._enrich_candidate(candidate, source_warnings)

        # Optional direct Scopus enrichment when API key is available.
        self._enrich_scopus_direct(
            title=title,
            author_query=author_query,
            doi_norm=doi_norm,
            candidates=sorted_candidates[:12],
            source_warnings=source_warnings,
        )

        if doi_norm:
            self._enrich_crossref_candidates(sorted_candidates[:12], doi_norm, source_warnings)

        return LookupResult(candidates=sorted_candidates, source_warnings=source_warnings)

    def _scopus_headers(self) -> Dict[str, str]:
        return {
            "X-ELS-APIKey": self.scopus_api_key,
            "Accept": "application/json",
        }

    def _load_openalex_works(self, title: str, doi_norm: str) -> Tuple[List[Dict[str, Any]], List[str]]:
        warnings: List[str] = []
        works: List[Dict[str, Any]] = []

        if doi_norm:
            data, err = _safe_get(
                "https://api.openalex.org/works",
                params={
                    "filter": f"doi:{doi_norm}",
                    "select": "id,display_name,publication_year,doi,authorships",
                },
            )
            if err:
                warnings.append(f"OpenAlex DOI lookup warning: {err}")
            else:
                works = data.get("results", []) if data else []

        if not works:
            data, err = _safe_get(
                "https://api.openalex.org/works",
                params={
                    "search": title,
                    "per-page": 25,
                    "select": "id,display_name,publication_year,doi,authorships",
                },
            )
            if err:
                warnings.append(f"OpenAlex title lookup warning: {err}")
            else:
                works = data.get("results", []) if data else []

        return works, warnings

    def _run_scopus_search_queries(
        self,
        query_candidates: List[str],
        fields: str,
    ) -> Tuple[List[Dict[str, Any]], List[str]]:
        entries: List[Dict[str, Any]] = []
        errors: List[str] = []

        for query in query_candidates:
            data, err = _safe_get(
                "https://api.elsevier.com/content/search/scopus",
                params={
                    "query": query,
                    "count": 10,
                    "field": fields,
                },
                headers=self._scopus_headers(),
            )
            if err:
                errors.append(f"{query}: {err}")
                continue

            entries = (((data or {}).get("search-results") or {}).get("entry")) or []
            if entries:
                break

        return entries, errors

    def _build_scopus_queries(self, title: str, author_query: str, doi_norm: str = "") -> List[str]:
        title_q = _clean_query_text(title)
        author_q = _clean_query_text(author_query)
        base_query = f'TITLE("{title_q}")'
        if doi_norm:
            base_query = f'DOI("{doi_norm}") OR {base_query}'

        queries: List[str] = []
        if author_q:
            queries.append(f"({base_query}) AND AUTH({author_q})")
        queries.append(base_query)
        return queries

    def to_identifier_bundle(self, candidate: CandidateAuthor) -> Dict[str, IdentifierItem]:
        if not candidate.google_scholar_id and not candidate.google_scholar_url:
            self._enrich_google_scholar(candidate, source_warnings=[])

        scopus_url = None
        if candidate.scopus_author_id:
            scopus_url = f"https://www.scopus.com/authid/detail.uri?authorId={candidate.scopus_author_id}"

        orcid_url = None
        if candidate.orcid:
            orcid_url = f"https://orcid.org/{normalize_orcid(candidate.orcid)}"

        wos_note = "If ResearcherID is absent, WoS profile may not be publicly discoverable without institutional tools."
        if not candidate.orcid:
            wos_note = "Web of Science ResearcherID cannot be derived because no public ORCID was found for this author."
        elif candidate.orcid and not candidate.wos_researcher_id:
            wos_note = "No Web of Science ResearcherID was exposed on the public ORCID record for this author."

        scholar_note = "Google Scholar has no official free public API; this app uses SerpAPI when configured and a best-effort public search fallback otherwise."
        if not self.serpapi_api_key and not candidate.google_scholar_id:
            if candidate.google_scholar_status == "blocked":
                scholar_note = "Google Scholar public search was rate-limited or blocked. Add SERPAPI_API_KEY for more reliable matching."
            else:
                scholar_note = "Google Scholar profile not found via public fallback. Add SERPAPI_API_KEY for higher-recall matching."

        orcid_note = "ORCID is treated as authoritative when explicitly present on source records."
        if not candidate.orcid:
            orcid_note = "No public ORCID was found for this author in OpenAlex, Crossref, or linked source metadata."

        return {
            "Scopus Author ID": IdentifierItem(
                value=candidate.scopus_author_id,
                profile_url=scopus_url,
                source=candidate.scopus_source or "OpenAlex author IDs (+ Scopus profile URL format)",
                confidence=self._confidence_label(candidate.score),
                note="Scopus API lookup may be used as optional verification when API key is configured.",
            ),
            "Web of Science ResearcherID": IdentifierItem(
                value=candidate.wos_researcher_id,
                profile_url=candidate.wos_profile_url,
                source="ORCID public record external identifiers",
                confidence=self._confidence_label(candidate.score),
                note=wos_note,
            ),
            "Google Scholar Profile": IdentifierItem(
                value=candidate.google_scholar_id,
                profile_url=candidate.google_scholar_url,
                source="SerpAPI Google Scholar Profiles (optional) or public Scholar author search fallback",
                confidence="medium" if candidate.google_scholar_id else "low",
                note=scholar_note,
            ),
            "ORCID iD": IdentifierItem(
                value=normalize_orcid(candidate.orcid) if candidate.orcid else None,
                profile_url=orcid_url,
                source="OpenAlex / Crossref / ORCID public record",
                confidence=self._confidence_label(candidate.score),
                note=orcid_note,
            ),
        }

    def _search_openalex(self, title: str, author_query: str, year: Optional[int], doi_norm: str) -> Tuple[List[CandidateAuthor], Optional[str]]:
        works, warnings = self._load_openalex_works(title, doi_norm)

        if not works:
            warning_text = " | ".join(warnings) if warnings else None
            return [], warning_text

        candidate_map: Dict[str, CandidateAuthor] = {}
        for work in works:
            work_title = work.get("display_name") or ""
            sim = title_similarity(title, work_title)
            work_doi = normalize_doi(work.get("doi") or "")
            work_year = work.get("publication_year")

            doi_bonus = 0.25 if doi_norm and work_doi and doi_norm == work_doi else 0.0
            year_bonus = 0.1 if year and work_year and year == work_year else 0.0

            for authorship in work.get("authorships", []):
                author = authorship.get("author") or {}
                author_name = author.get("display_name") or "Unknown"
                author_id = author.get("id")
                key = author_id or f"name:{author_name.lower()}"

                institutions = authorship.get("institutions") or []
                affiliation = "; ".join(inst.get("display_name", "") for inst in institutions if inst.get("display_name"))
                author_bonus = self._author_bonus(author_query, author_name)

                score = min(1.0, (sim * 0.6) + doi_bonus + year_bonus + author_bonus)
                evidence = [f"Title similarity {sim:.2f}"]
                if doi_bonus > 0:
                    evidence.append("DOI exact match")
                if year_bonus > 0:
                    evidence.append("Publication year match")
                if author_bonus > 0:
                    evidence.append("Author name query match")

                if key not in candidate_map:
                    candidate_map[key] = CandidateAuthor(
                        display_name=author_name,
                        openalex_author_id=author_id,
                        affiliation=affiliation,
                        works_count=0,
                        matched_papers=1,
                        score=score,
                        evidence=evidence,
                        orcid=author.get("orcid"),
                    )
                else:
                    existing = candidate_map[key]
                    existing.matched_papers += 1
                    if score > existing.score:
                        existing.score = score
                        existing.evidence = evidence
                    if affiliation and not existing.affiliation:
                        existing.affiliation = affiliation
                    if not existing.orcid and author.get("orcid"):
                        existing.orcid = author.get("orcid")

        warning_text = " | ".join(warnings) if warnings else None
        return list(candidate_map.values()), warning_text

    def _enrich_candidate(self, candidate: CandidateAuthor, source_warnings: List[str]) -> None:
        if candidate.openalex_author_id:
            author_api_url = normalize_openalex_author_api_url(candidate.openalex_author_id)
            data, err = _safe_get(author_api_url) if author_api_url else (None, "Missing OpenAlex author ID")
            if err:
                source_warnings.append(f"OpenAlex author enrichment warning ({candidate.display_name}): {err}")
            elif data:
                ids = data.get("ids") or {}
                candidate.works_count = data.get("works_count") or candidate.works_count
                candidate.orcid = candidate.orcid or ids.get("orcid")

                scopus_value = ids.get("scopus")
                if scopus_value:
                    candidate.scopus_author_id = parse_scopus_author_id(scopus_value)
                    if candidate.scopus_author_id and not candidate.scopus_source:
                        candidate.scopus_source = "OpenAlex author IDs"

                if not candidate.affiliation:
                    institutions = data.get("last_known_institutions") or []
                    names = [inst.get("display_name", "") for inst in institutions if inst.get("display_name")]
                    candidate.affiliation = "; ".join(names)

        self._enrich_orcid(candidate, source_warnings)

        # Optional higher-fidelity checks if integrations are configured.
        self._optional_scopus_verify(candidate, source_warnings)

    def _enrich_orcid(self, candidate: CandidateAuthor, source_warnings: List[str]) -> None:
        if not candidate.orcid:
            return
        orcid_id = normalize_orcid(candidate.orcid)
        url = f"https://pub.orcid.org/v3.0/{orcid_id}/record"
        data, err = _safe_get(url, headers={"Accept": "application/json"})
        if err:
            source_warnings.append(f"ORCID enrichment warning ({candidate.display_name}): {err}")
            return

        ext_ids = (
            (((data or {}).get("person") or {}).get("external-identifiers") or {}).get("external-identifier")
            or []
        )
        if isinstance(ext_ids, dict):
            ext_ids = [ext_ids]

        for ext in ext_ids:
            if not isinstance(ext, dict):
                continue
            ext_type = (ext.get("external-id-type") or "").lower()
            ext_value = ext.get("external-id-value") or ""
            ext_url = ((ext.get("external-id-url") or {}).get("value") or "").strip() or None

            if ("researcherid" in ext_type) or ("web of science" in ext_type) or ("wos" in ext_type):
                candidate.wos_researcher_id = ext_value or candidate.wos_researcher_id
                candidate.wos_profile_url = ext_url or candidate.wos_profile_url

    def _enrich_crossref_candidates(
        self,
        candidates: List[CandidateAuthor],
        doi_norm: str,
        source_warnings: List[str],
    ) -> None:
        url = f"https://api.crossref.org/works/{quote(doi_norm, safe='')}"
        data, err = _safe_get(url)
        if err:
            source_warnings.append(f"Crossref DOI enrichment warning: {err}")
            return

        authors = (((data or {}).get("message") or {}).get("author")) or []
        for author in authors:
            given = (author.get("given") or "").strip()
            family = (author.get("family") or "").strip()
            orcid = author.get("ORCID")
            if not orcid:
                continue

            crossref_name = f"{given} {family}".strip()
            best_candidate = None
            best_score = 0.0
            for candidate in candidates:
                sim = person_name_similarity(candidate.display_name, crossref_name)
                if sim > best_score:
                    best_score = sim
                    best_candidate = candidate

            if best_candidate and best_score >= 0.8 and not best_candidate.orcid:
                best_candidate.orcid = orcid
                self._enrich_orcid(best_candidate, source_warnings)

    def _enrich_google_scholar(self, candidate: CandidateAuthor, source_warnings: List[str]) -> None:
        if not self.serpapi_api_key:
            self._enrich_google_scholar_public(candidate, source_warnings)
            return

        params = {
            "engine": "google_scholar_profiles",
            "mauthors": candidate.display_name,
            "api_key": self.serpapi_api_key,
        }
        data, err = _safe_get("https://serpapi.com/search.json", params=params)
        if err:
            source_warnings.append(f"Google Scholar lookup warning ({candidate.display_name}): {err}")
            return

        profiles = (data or {}).get("profiles") or []
        if not profiles:
            return

        best = profiles[0]
        candidate.google_scholar_id = best.get("author_id")
        if candidate.google_scholar_id:
            candidate.google_scholar_url = f"https://scholar.google.com/citations?user={candidate.google_scholar_id}"

    def _enrich_google_scholar_public(self, candidate: CandidateAuthor, source_warnings: List[str]) -> None:
        query_name = candidate.display_name.strip()
        if not query_name:
            return

        url = "https://scholar.google.com/citations"
        params = {
            "view_op": "search_authors",
            "mauthors": query_name,
            "hl": "en",
        }
        text, err = _safe_get_text(url, params=params)
        if err:
            if "HTTP 429" in err or "captcha" in err.lower():
                candidate.google_scholar_status = "blocked"
                return
            source_warnings.append(f"Google Scholar public search warning ({candidate.display_name}): {err}")
            return

        match = re.search(r"/citations\?user=([A-Za-z0-9_-]{6,})", text or "")
        if match:
            candidate.google_scholar_id = match.group(1)
            candidate.google_scholar_url = f"https://scholar.google.com/citations?user={candidate.google_scholar_id}"
            candidate.google_scholar_status = "found"

    def _optional_scopus_verify(self, candidate: CandidateAuthor, source_warnings: List[str]) -> None:
        if not self.scopus_api_key or not candidate.scopus_author_id:
            return

        # Lightweight verification call. If the profile exists, response confirms author record.
        verify_url = f"https://api.elsevier.com/content/author/author_id/{candidate.scopus_author_id}"
        _, err = _safe_get(verify_url, params={"view": "ENHANCED"}, headers=self._scopus_headers())
        if err:
            source_warnings.append(
                f"Scopus verification warning ({candidate.display_name}): {err}"
            )

    def _enrich_scopus_direct(
        self,
        title: str,
        author_query: str,
        doi_norm: str,
        candidates: List[CandidateAuthor],
        source_warnings: List[str],
    ) -> None:
        if not self.scopus_api_key:
            return

        if doi_norm:
            self._enrich_scopus_from_doi(doi_norm, candidates, source_warnings)

        if any(c.scopus_author_id for c in candidates):
            return

        self._enrich_scopus_from_title(title, author_query, candidates, source_warnings)

    def _enrich_scopus_from_doi(
        self,
        doi_norm: str,
        candidates: List[CandidateAuthor],
        source_warnings: List[str],
    ) -> None:
        encoded_doi = quote(doi_norm, safe="")
        url = f"https://api.elsevier.com/content/abstract/doi/{encoded_doi}"
        data, err = _safe_get(url, params={"view": "FULL"}, headers=self._scopus_headers())
        if err:
            source_warnings.append(f"Scopus DOI lookup warning: {err}")
            return

        author_nodes = (
            (((data or {}).get("abstracts-retrieval-response") or {}).get("authors") or {}).get("author")
            or []
        )

        pairs: List[Tuple[str, str]] = []
        for node in author_nodes:
            scopus_id = parse_scopus_author_id(str(node.get("@auid") or ""))
            if not scopus_id:
                continue
            indexed_name = (node.get("ce:indexed-name") or "").strip()
            surname = (node.get("ce:surname") or "").strip()
            given = (node.get("ce:given-name") or "").strip()
            display_name = indexed_name or f"{given} {surname}".strip()
            if display_name:
                pairs.append((display_name, scopus_id))

        self._apply_scopus_pairs(candidates, pairs, "Scopus Abstract Retrieval API")

    def _search_scopus_candidates(
        self,
        title: str,
        author_query: str,
        doi_norm: str,
        source_warnings: List[str],
    ) -> List[CandidateAuthor]:
        entries, query_errors = self._run_scopus_search_queries(
            self._build_scopus_queries(title, author_query, doi_norm),
            "eid,dc:title,dc:creator,prism:doi,prism:coverDate",
        )

        if not entries and query_errors:
            source_warnings.append("Scopus fallback search warning: " + " | ".join(query_errors[:2]))
        if not entries:
            return []

        candidate_map: Dict[str, CandidateAuthor] = {}
        for entry in entries:
            eid = (entry.get("eid") or "").strip()
            if not eid:
                continue

            work_title = (entry.get("dc:title") or "").strip()
            sim = title_similarity(title, work_title)
            doi_bonus = 0.25 if doi_norm and normalize_doi(str(entry.get("prism:doi") or "")) == doi_norm else 0.0

            author_pairs = self._get_scopus_authors_by_eid(eid, source_warnings)
            if not author_pairs:
                creator = (entry.get("dc:creator") or "").strip()
                if creator:
                    author_pairs = [(creator, None)]

            for name, sid in author_pairs:
                author_bonus = self._author_bonus(author_query, name)
                score = min(1.0, (sim * 0.65) + doi_bonus + author_bonus)
                key = f"scopus:{sid}" if sid else f"name:{name.lower()}"

                if key not in candidate_map:
                    candidate_map[key] = CandidateAuthor(
                        display_name=name,
                        openalex_author_id=None,
                        affiliation="",
                        works_count=0,
                        matched_papers=1,
                        score=score,
                        evidence=[f"Scopus title similarity {sim:.2f}"],
                        scopus_author_id=sid,
                        scopus_source="Scopus Search + Abstract API" if sid else "Scopus Search API",
                    )
                else:
                    existing = candidate_map[key]
                    existing.matched_papers += 1
                    if score > existing.score:
                        existing.score = score
                    if sid and not existing.scopus_author_id:
                        existing.scopus_author_id = sid
                        existing.scopus_source = "Scopus Search + Abstract API"

        return list(candidate_map.values())

    def _get_scopus_authors_by_eid(
        self,
        eid: str,
        source_warnings: List[str],
    ) -> List[Tuple[str, Optional[str]]]:
        url = f"https://api.elsevier.com/content/abstract/eid/{quote(eid, safe='')}"
        data, err = _safe_get(url, params={"view": "FULL"}, headers=self._scopus_headers())
        if err:
            source_warnings.append(f"Scopus abstract lookup warning ({eid}): {err}")
            return []

        author_nodes = (
            (((data or {}).get("abstracts-retrieval-response") or {}).get("authors") or {}).get("author")
            or []
        )

        pairs: List[Tuple[str, Optional[str]]] = []
        for node in author_nodes:
            sid = parse_scopus_author_id(str(node.get("@auid") or ""))
            if not sid:
                sid = parse_scopus_author_id(str(node.get("author-url") or ""))
            indexed_name = (node.get("ce:indexed-name") or "").strip()
            surname = (node.get("ce:surname") or "").strip()
            given = (node.get("ce:given-name") or "").strip()
            name = indexed_name or f"{given} {surname}".strip()
            if name:
                pairs.append((name, sid))

        return pairs

    def _enrich_scopus_from_title(
        self,
        title: str,
        author_query: str,
        candidates: List[CandidateAuthor],
        source_warnings: List[str],
    ) -> None:
        entries, errors = self._run_scopus_search_queries(
            self._build_scopus_queries(title, author_query),
            "eid,dc:title,dc:creator,prism:doi",
        )

        if not entries and errors:
            source_warnings.append("Scopus title lookup warning: " + " | ".join(errors[:2]))
            return

        pairs: List[Tuple[str, str]] = []

        for entry in entries:
            eid = (entry.get("eid") or "").strip()
            if not eid:
                continue

            author_pairs = self._get_scopus_authors_by_eid(eid, source_warnings)
            for name, sid in author_pairs:
                if sid:
                    pairs.append((name, sid))

        self._apply_scopus_pairs(candidates, pairs, "Scopus Search API")

    def _apply_scopus_pairs(
        self,
        candidates: List[CandidateAuthor],
        pairs: List[Tuple[str, str]],
        source_label: str,
    ) -> None:
        if not pairs:
            return

        for candidate in candidates:
            if candidate.scopus_author_id:
                continue

            best_id = None
            best_score = 0.0
            for name, sid in pairs:
                sim = person_name_similarity(candidate.display_name, name)
                if sim > best_score:
                    best_score = sim
                    best_id = sid

            if best_id and best_score >= 0.6:
                candidate.scopus_author_id = best_id
                candidate.scopus_source = source_label

    @staticmethod
    def _author_bonus(author_query: str, candidate_name: str) -> float:
        if not author_query.strip():
            return 0.0
        sim = title_similarity(author_query, candidate_name)
        if sim >= 0.85:
            return 0.2
        if sim >= 0.65:
            return 0.15
        if sim >= 0.45:
            return 0.08
        return 0.0

    @staticmethod
    def _confidence_label(score: float) -> str:
        if score >= 0.8:
            return "high"
        if score >= 0.6:
            return "medium"
        return "low"
