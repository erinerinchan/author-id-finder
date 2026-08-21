import html
import json
import os
from datetime import datetime
from typing import Dict

import streamlit as st
import streamlit.components.v1 as components
from dotenv import load_dotenv

from src.author_services import AuthorIdLookupService, CandidateAuthor, IdentifierItem


load_dotenv()
lookup_service = AuthorIdLookupService()

st.set_page_config(
    page_title="Author ID Finder | HKUST Library",
    page_icon="🔎",
    layout="wide",
)

st.markdown(
    """
<style>
:root {
  --hkust-blue: #003c71;
  --hkust-red: #c8102e;
  --ink: #0f1a2b;
  --card: #f7f9fc;
  --line: #c5d2e5;
}

.block-container {
  max-width: 1100px;
    padding-top: 1.25rem;
    padding-left: 1rem;
    padding-right: 1rem;
}

.banner {
  background: linear-gradient(120deg, var(--hkust-blue) 0%, #005b9f 65%, #0077c8 100%);
  color: white;
  border-radius: 14px;
  padding: 1rem 1.25rem;
  margin-bottom: 1rem;
  border-left: 8px solid var(--hkust-red);
}

.notice {
  border: 1px solid var(--line);
  border-left: 6px solid var(--hkust-red);
  background: #fef7f8;
  color: var(--ink);
  border-radius: 10px;
  padding: 0.85rem 1rem;
  margin-bottom: 1rem;
}

.result-card {
  border: 1px solid var(--line);
  background: var(--card);
  border-radius: 12px;
  padding: 1rem;
  margin: 0.4rem 0 1rem 0;
}

.id-row {
  border-bottom: 1px dashed #d7e1ef;
  padding: 0.6rem 0;
}

.id-row:last-child {
  border-bottom: none;
}

.meta-chip {
  display: inline-block;
  padding: 0.15rem 0.5rem;
  border-radius: 999px;
  font-size: 0.78rem;
  color: white;
  margin-right: 0.4rem;
}

.conf-high { background: #007a3d; }
.conf-medium { background: #8a6d1a; }
.conf-low { background: #6b7280; }

.small-note {
  color: #40506a;
  font-size: 0.88rem;
}

div[data-testid="stForm"] {
    border: 1px solid var(--line);
    border-radius: 14px;
    padding: 0.5rem;
    background: white;
}

div[data-testid="stRadio"] label p {
    overflow-wrap: anywhere;
}

div[data-testid="stTextInput"] input,
div[data-testid="stNumberInput"] input {
    min-height: 2.75rem;
}

@media (max-width: 1024px) {
    .block-container {
        max-width: 100%;
    }

    div[data-testid="stHorizontalBlock"] {
        gap: 0.75rem;
    }
}

@media (max-width: 820px) {
    div[data-testid="stHorizontalBlock"] {
        flex-direction: column;
    }

    div[data-testid="column"] {
        width: 100% !important;
        flex: 1 1 100% !important;
    }

    .banner h2 {
        font-size: 1.65rem;
        line-height: 1.15;
    }

    .result-card {
        padding: 0.85rem;
    }
}

@media (max-width: 640px) {
  .block-container {
    padding-top: 0.75rem;
        padding-left: 0.75rem;
        padding-right: 0.75rem;
    }

    .banner {
        padding: 0.9rem 1rem;
        border-left-width: 6px;
    }

    .banner h2 {
        font-size: 1.45rem;
    }

    .notice,
    .result-card {
        border-radius: 12px;
    }

    .meta-chip {
        display: inline-block;
        margin-bottom: 0.35rem;
    }

    div[data-testid="stDownloadButton"] button,
    div[data-testid="stFormSubmitButton"] button {
        width: 100%;
    }

    div[data-testid="stTextArea"] textarea {
        font-size: 0.92rem;
  }
}
</style>
""",
    unsafe_allow_html=True,
)

if "last_lookup" not in st.session_state:
    st.session_state.last_lookup = None

if "search_log" not in st.session_state:
    st.session_state.search_log = []


def integration_status() -> Dict[str, object]:
    return {
        "Scopus API key loaded": bool(os.getenv("SCOPUS_API_KEY", "").strip()),
        "SerpAPI key loaded": bool(os.getenv("SERPAPI_API_KEY", "").strip()),
        "OpenAlex enrichment": "enabled",
        "ORCID enrichment": "enabled",
        "WoS source": "public ORCID external identifiers",
        "Google Scholar fallback": "public author search",
    }

st.markdown(
    """
<div class="banner" role="banner" aria-label="Application Header">
  <h2 style="margin:0">Author ID Finder</h2>
  <div style="opacity:0.95">HKUST Library – Research & Learning Support</div>
</div>
""",
    unsafe_allow_html=True,
)

with st.expander("Integration status", expanded=False):
    st.write(integration_status())

st.markdown(
    """
<div class="notice" role="note" aria-label="Internal Privacy Notice">
<strong>Internal use only:</strong> For internal HKUST Library & repository staff use only.
Results are for profile-building purposes.
No personal data is retained beyond the current session unless explicitly required for audit.
</div>
""",
    unsafe_allow_html=True,
)


with st.form("search_form", clear_on_submit=False):
    st.subheader("Find researcher identifiers from a publication title")

    title = st.text_input(
        "Publication title (required)",
        placeholder="Paste exact or near-exact publication title",
        help="Precision is highest with exact titles.",
    )

    col1, col2, col3 = st.columns(3)
    with col1:
        author_query = st.text_input(
            "Author name (recommended)",
            placeholder="e.g., Chan Tai-Man or Chan T M",
        )
    with col2:
        year = st.number_input(
            "Publication year (recommended)",
            min_value=1900,
            max_value=datetime.now().year + 1,
            value=None,
            step=1,
            format="%d",
            placeholder="e.g., 2023",
        )
    with col3:
        doi = st.text_input(
            "DOI (recommended)",
            placeholder="10.xxxx/xxxxx",
        )

    submitted = st.form_submit_button("Search / Retrieve IDs", type="primary")

if submitted:
    if not title.strip():
        st.error("Publication title is required.")
    else:
        with st.spinner("Searching trusted sources and building author candidates..."):
            result = lookup_service.search(
                title=title.strip(),
                author_query=author_query.strip(),
                year=int(year) if year else None,
                doi=doi.strip(),
            )

        st.session_state.last_lookup = {
            "query": {
                "title": title.strip(),
                "author_query": author_query.strip(),
                "year": int(year) if year else None,
                "doi": doi.strip(),
            },
            "result": result,
        }

        # Session-only troubleshooting log.
        st.session_state.search_log.append(
            {
                "ts": datetime.utcnow().isoformat(),
                "query": {
                    "title": title.strip(),
                    "author_query": author_query.strip(),
                    "year": int(year) if year else None,
                    "doi": doi.strip(),
                },
                "candidate_count": len(result.candidates),
            }
        )


def confidence_class(label: str) -> str:
    if label == "high":
        return "conf-high"
    if label == "medium":
        return "conf-medium"
    return "conf-low"


def render_copy_field(label: str, value: str, key_seed: str) -> None:
    input_id = f"copy_{key_seed}"
    safe_value = html.escape(value)
    safe_label = html.escape(label)
    components.html(
        f"""
<div style="display:flex; gap:8px; align-items:center; margin-top:4px; flex-wrap:wrap;">
  <label for="{input_id}" style="position:absolute; left:-10000px; top:auto; width:1px; height:1px; overflow:hidden;">{safe_label}</label>
  <input id="{input_id}" value="{safe_value}" readonly
                 style="flex:1 1 240px; min-width:0; padding:7px 8px; border:1px solid #b8c5d9; border-radius:6px; font-family:monospace;" />
  <button
        style="padding:7px 10px; background:#003c71; color:white; border:none; border-radius:6px; cursor:pointer; flex:0 0 auto;"
    onclick="navigator.clipboard.writeText(document.getElementById('{input_id}').value)">
    Copy
  </button>
</div>
""",
                height=78,
    )


def candidate_option_text(index: int, candidate: CandidateAuthor) -> str:
    return (
        f"{index + 1}. {candidate.display_name} | Affiliation: {candidate.affiliation or 'N/A'} | "
        f"Matched papers: {candidate.matched_papers} | Score: {candidate.score:.2f}"
    )


def to_plain_text(candidate: CandidateAuthor, bundle: Dict[str, IdentifierItem]) -> str:
    lines = [
        f"Author: {candidate.display_name}",
        f"Affiliation: {candidate.affiliation or 'N/A'}",
        f"Confidence: {bundle['ORCID iD'].confidence}",
        "",
    ]
    for label, item in bundle.items():
        lines.append(f"{label}: {item.value or 'Not found'}")
        if item.profile_url:
            lines.append(f"{label} URL: {item.profile_url}")
        lines.append(f"Source: {item.source}")
        if item.note:
            lines.append(f"Note: {item.note}")
        lines.append("")
    return "\n".join(lines)


def to_json_payload(candidate: CandidateAuthor, bundle: Dict[str, IdentifierItem]) -> Dict[str, object]:
    return {
        "author": {
            "name": candidate.display_name,
            "affiliation": candidate.affiliation,
            "matched_papers": candidate.matched_papers,
            "works_count": candidate.works_count,
            "score": round(candidate.score, 3),
            "evidence": candidate.evidence,
        },
        "identifiers": {
            label: {
                "value": item.value,
                "profile_url": item.profile_url,
                "source": item.source,
                "confidence": item.confidence,
                "note": item.note,
            }
            for label, item in bundle.items()
        },
    }


def missing_value_label(label: str, item: IdentifierItem) -> str:
    if label == "Google Scholar Profile" and "rate-limited or blocked" in item.note.lower():
        return "Unavailable: public Google Scholar lookup was rate-limited"
    if label == "ORCID iD" and item.note.startswith("No public ORCID"):
        return "Unavailable: no public ORCID found"
    if label == "Web of Science ResearcherID" and item.note.startswith("Web of Science ResearcherID cannot be derived"):
        return "Unavailable: no ORCID available to derive WoS ID"
    if label == "Web of Science ResearcherID" and "No Web of Science ResearcherID was exposed" in item.note:
        return "Unavailable: no public WoS ResearcherID exposed"
    return "Not found"


def render_identifier_row(label: str, item: IdentifierItem, chosen_idx: int) -> None:
    css_class = confidence_class(item.confidence)
    st.markdown('<div class="id-row">', unsafe_allow_html=True)
    st.markdown(f"**{label}**")
    st.markdown(
        f"<span class='meta-chip {css_class}'>{item.confidence} confidence</span>"
        f"<span class='small-note'>Source: {item.source}</span>",
        unsafe_allow_html=True,
    )

    if item.value:
        st.write(item.value)
        render_copy_field(label, item.value, f"{label}_{chosen_idx}".replace(" ", "_"))
    else:
        st.write(missing_value_label(label, item))

    if item.profile_url:
        st.markdown(f"[Open profile link]({item.profile_url})")
    if item.note:
        st.caption(item.note)
    st.markdown("</div>", unsafe_allow_html=True)


last_lookup = st.session_state.last_lookup
if last_lookup:
    result = last_lookup["result"]
    candidates = result.candidates

    if result.source_warnings:
        with st.expander("Source warnings / limitations", expanded=False):
            for warn in result.source_warnings:
                st.warning(warn)

    if not candidates:
        st.error("No high-confidence match found.")
        st.markdown(
            """
Try one or more of the following:
- Use the exact publication title from the publisher page.
- Add a DOI.
- Add author last name + initials.
- Add publication year.
- Check title spelling and punctuation.
"""
        )
    else:
        st.subheader("Candidate author disambiguation")
        st.caption("Select the candidate that best matches the intended author.")

        options = [candidate_option_text(idx, candidate) for idx, candidate in enumerate(candidates[:8])]

        chosen_option = st.radio(
            "Candidate list",
            options,
            index=0,
            help="If the top candidate looks incorrect, select another candidate before exporting IDs.",
        )

        chosen_idx = options.index(chosen_option)
        chosen = candidates[chosen_idx]
        bundle = lookup_service.to_identifier_bundle(chosen)

        st.markdown('<div class="result-card">', unsafe_allow_html=True)
        st.markdown(f"### Result card: {chosen.display_name}")
        st.markdown(
            f"Affiliation: {chosen.affiliation or 'N/A'}  \\n"
            f"Matched papers in query set: {chosen.matched_papers}  \\n"
            f"Estimated lifetime works (OpenAlex): {chosen.works_count or 'N/A'}"
        )

        for label, item in bundle.items():
            render_identifier_row(label, item, chosen_idx)

        st.markdown("</div>", unsafe_allow_html=True)

        plain_text_export = to_plain_text(chosen, bundle)
        json_export = json.dumps(to_json_payload(chosen, bundle), indent=2, ensure_ascii=False)

        col_a, col_b = st.columns(2)
        with col_a:
            st.download_button(
                "Download plain text",
                data=plain_text_export,
                file_name="author_ids.txt",
                mime="text/plain",
                use_container_width=True,
            )
        with col_b:
            st.download_button(
                "Download JSON snippet",
                data=json_export,
                file_name="author_ids.json",
                mime="application/json",
                use_container_width=True,
            )

        st.text_area("Plain text preview", plain_text_export, height=200)
        st.text_area("JSON preview", json_export, height=260)

with st.expander("Data sources and known limitations", expanded=False):
    st.markdown(
        """
- OpenAlex and ORCID public endpoints are the primary matching/enrichment sources.
- Crossref, Semantic Scholar, and direct Scopus verification can be integrated/extended further if needed.
- Scopus verification is active only when `SCOPUS_API_KEY` is configured.
- Google Scholar profile retrieval is active only when `SERPAPI_API_KEY` is configured.
- Web of Science ResearcherID may be unavailable if not exposed in the ORCID public record.
- The app prioritizes precision over recall and may return no match when confidence is low.
"""
    )

st.caption("Built for internal HKUST Library workflows. Session logs are ephemeral and reset on app restart.")
