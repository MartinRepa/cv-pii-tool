"""
CVSanitiser — post-pipeline text sanitisation for anonymised CVs.

Pass sequence
-------------
  0. Clean empty PII field labels left by removed tokens
     ("Date of birth:", "Address:", etc.)
  1. Repair broken words where a token absorbed a word prefix/suffix
     ("[ORG_3]lude" → "include")
  2. Replace every typed, indexed token with a semantic label or the
     original value, depending on category:
       - Private fields        → removed
       - [URL_N]               → [URL]
       - [LOCATION_N]          → [LOCATION]
       - [ORG_N] (tech tool)   → original name restored (e.g. "Snowflake")
       - [ORG_N] (university)  → [UNIVERSITY]
       - [ORG_N] (training)    → [TRAINING_PROVIDER]
       - [ORG_N] (company)     → [COMPANY]
  3. Fix label-fragment debris after replacement
     ("[COMPANY]red goals" → "shared goals")
  4. Mask surviving explicit addresses ("Address Bulevardi..." lines)
  5. Mask surviving explicit locations (world cities/countries not
     caught by the PII pipeline)
  6. Mask surviving explicit employer names identifiable in the text
  7. Final whitespace cleanup

Usage:
    sanitiser = CVSanitiser()
    clean_text = sanitiser.sanitise(result.anonymised_text, result.pii_map)
"""
from __future__ import annotations

import re
from typing import Final

__all__ = ["CVSanitiser"]


# ── Token regex ────────────────────────────────────────────────────────────────

_TOKEN_RE: Final = re.compile(
    r"\[("
    r"PERSON|EMAIL|PHONE|ADDRESS|DOB|AL_NID|PASSPORT|ID_NUMBER|IBAN"
    r"|MARITAL|GENDER|RELIGION|FAMILY"
    r"|LOCATION|URL|ORG"
    r")_(\d+)\]"
)

_REMOVE_TYPES: Final[frozenset[str]] = frozenset({
    "PERSON", "EMAIL", "PHONE", "ADDRESS", "DOB",
    "AL_NID", "PASSPORT", "ID_NUMBER", "IBAN",
    "MARITAL", "GENDER", "RELIGION", "FAMILY",
})

# ── Step 0: empty field label patterns ────────────────────────────────────────

# These are common CV Europass field labels whose values are PII.
# After the PII tokens are removed the labels become meaningless noise.
# We strip the entire pattern (including any trailing parenthetical).
_EMPTY_FIELD_PATTERNS: Final[list[re.Pattern]] = [
    # "Date of birth: [DOB_N]" → after DOB removal → "Date of birth: "
    re.compile(r"Date\s+of\s+birth\s*:?\s*", re.IGNORECASE),
    # "Phone number: [PHONE_N] (Mobile)" — removes label; (Mobile) handled below
    re.compile(r"Phone\s+(?:number|no\.?)\s*:?\s*", re.IGNORECASE),
    # "Email address:" — may span a line break in Europass PDFs
    re.compile(r"Email\s+address\s*:?\s*", re.IGNORECASE),
    # "Email:" / "E-mail:" — word boundary prevents matching inside [EMAIL_N]
    re.compile(r"\bE-?mail\b\s*:?\s*", re.IGNORECASE),
    # "(Mobile)" parenthetical descriptor left after phone label removal
    re.compile(r"\(\s*Mobile\s*\)\s*", re.IGNORECASE),
]

# ── Step 1: broken-word repair ────────────────────────────────────────────────

_SUFFIX_GLUE_RE: Final = re.compile(
    r"\[(?:PERSON|EMAIL|PHONE|ADDRESS|DOB|AL_NID|PASSPORT|ID_NUMBER|IBAN"
    r"|MARITAL|GENDER|RELIGION|FAMILY|LOCATION|URL|ORG)_\d+\]"
    r"([a-z]{2,})"
)

_PREFIX_GLUE_RE: Final = re.compile(
    r"([a-z]{2,})"
    r"\[(?:PERSON|EMAIL|PHONE|ADDRESS|DOB|AL_NID|PASSPORT|ID_NUMBER|IBAN"
    r"|MARITAL|GENDER|RELIGION|FAMILY|LOCATION|URL|ORG)_\d+\]"
)

# Suffix → repaired word.  Only unambiguous cases.
_SUFFIX_REPAIR: Final[dict[str, str]] = {
    "lude":     "include",
    "luded":    "included",
    "ludes":    "includes",
    "luding":   "including",
    "ome":      "income",
    "omes":     "incomes",
    "rease":    "increase",
    "reased":   "increased",
    "reases":   "increases",
    "reasing":  "increasing",
    "orate":    "corporate",
    "oration":  "corporation",
    "orations": "corporations",
    "gorithm":  "algorithm",
    "gorithms": "algorithms",
    "chelor":   "bachelor",
    # "sha" absorbed from "shared" — leaves "[TOKEN]red goals" dangling.
    # Handled here (pre-replacement) for tokens with garbage values (removed
    # in step 2) and also in step 3 for tokens replaced with a label.
    "red":      "shared",
    "ring":     "sharing",
}

_PREFIX_REPAIR: Final[dict[str, str | None]] = {
    "co":  None,
    "pro": None,
}

# ── Step 2: ORG classification ─────────────────────────────────────────────────

# Technology/tool names that are dual-use (company AND product).
# When a candidate uses one of these as a skill/tool, restore the real name.
# Match against the lowercased original value from pii_map.
_TECH_TOOLS: Final[frozenset[str]] = frozenset({
    # Data platforms & pipelines
    "snowflake", "databricks", "dbt", "apache spark", "spark",
    "hadoop", "hive", "kafka", "apache kafka", "airflow", "apache airflow",
    "airbyte", "fivetran", "talend", "informatica", "snowpark", "snowpipe",
    # Cloud & DevOps
    "aws", "azure", "gcp", "google cloud", "amazon web services",
    "azure devops", "azure data factory", "azure blob", "azure blobs",
    "github", "gitlab", "jenkins", "docker", "kubernetes", "terraform",
    "git", "vscode", "vs code",
    # Databases
    "oracle", "postgresql", "postgres", "mysql", "mongodb",
    "redis", "elasticsearch", "cassandra", "teradata",
    "sql server", "microsoft sql server", "db2",
    # BI & analytics
    "tableau", "power bi", "qlik", "qlik sense", "qlik compose",
    "qlik replicate", "looker", "metabase", "superset",
    "ssrs", "ssis", "ssas", "microsoft ssis", "microsoft ssrs",
    # CRM / ERP
    "salesforce", "sap", "dynamics", "dynamics 365", "hubspot", "workday",
    # Orchestration / ML
    "airflow", "prefect", "dagster", "mlflow", "kubeflow",
    "power automate", "power apps",
    # Statistical / science
    "spss", "stata", "matlab", "r studio",
    # Misc
    "jira", "confluence",
    # Note: "udemy" intentionally excluded — it is a training provider,
    # not a technical tool, and should be masked as [TRAINING_PROVIDER].
})

_ORG_UNIVERSITY_KWS: Final[frozenset[str]] = frozenset({
    "university", "universiteti", "college", "kolegji",
    "polytechnic", "politechnic", "faculty", "fakulteti",
    "school of", "shkolla", "academic",
})

_ORG_TRAINING_KWS: Final[frozenset[str]] = frozenset({
    "training", "institute", "instituti", "academy", "akademia",
    "centre", "center", "certification", "professional development",
    "association of", "chamber of",
})

_EDUCATION_SECTIONS: Final[frozenset[str]] = frozenset({
    "education", "qualifications", "academic background",
    "education and training",
})

_TRAINING_SECTIONS: Final[frozenset[str]] = frozenset({
    "certifications", "certification", "training",
    "courses", "course", "professional development",
})

_SECTION_HEADER_RE: Final = re.compile(
    r"^[ \t]*("
    r"EDUCATION(?:\s+AND\s+TRAINING)?|CERTIFICATIONS?|TRAINING|COURSES?|QUALIFICATIONS?"
    r"|WORK EXPERIENCE|EXPERIENCE|EMPLOYMENT|PROFESSIONAL SUMMARY|SUMMARY"
    r"|REFERENCES?|SKILLS?|LANGUAGES?|PERSONAL INFORMATION|DIGITAL SKILLS"
    r")[ \t]*$",
    re.IGNORECASE | re.MULTILINE,
)

# ── Step 3: post-replacement label-fragment cleanup ────────────────────────────

# After token replacement a label can be fused to a lowercase fragment when
# the original detection absorbed only part of a word.
# E.g. [ORG_2] = "...to achieve sha" → after replacement: [COMPANY]red goals
#
# Strategy: look up the suffix in a small repair table; if unknown, drop the
# label but keep the fragment (any text is better than "[COMPANY]red goals").

_LABEL_FRAGMENT_RE: Final = re.compile(
    r"\[(?:COMPANY|UNIVERSITY|TRAINING_PROVIDER|LOCATION|URL)\]([a-z][a-z0-9]*)"
)

_LABEL_SUFFIX_REPAIR: Final[dict[str, str]] = {
    "red": "shared",          # [COMPANY]red goals → shared goals
    "red goals": "shared goals",
}

# ── Step 4: explicit address masking ──────────────────────────────────────────

# Lines/phrases that start with "Address" followed by real street content.
# Replace the street portion with [ADDRESS_REDACTED] while keeping any
# "Business or Sector" prefix that precedes the Address keyword.
_ADDRESS_CONTENT_RE: Final = re.compile(
    r"\bAddress\s+(?!\[ADDRESS_REDACTED\])([A-Z0-9\[][^\n]{5,})",
    re.MULTILINE,
)

# ── Step 5: explicit location masking ─────────────────────────────────────────

# Locations that commonly appear in international CVs but are not in the
# pipeline's Albanian-focused location list.
_EXPLICIT_LOCATIONS: Final[list[tuple[str, ...]]] = [
    # City, Country pairs — order matters (longer first to avoid partial match)
    ("Grand Canyon", "Arizona", "United States"),
    ("Skopje", "North Macedonia"),
    ("North Macedonia",),
    ("Luxembourg", "Luxembourg"),
    ("Budapest", "Hungary"),
    ("Chicago", "Illinois"),
    ("Vienna", "Austria"),
    ("Prague", "Czech Republic"),
    ("Czech Republic",),
    ("Brussels", "Belgium"),
    ("Amsterdam", "Netherlands"),
    ("Paris", "France"),
    ("Berlin", "Germany"),
    ("Rome", "Italy"),
    ("Madrid", "Spain"),
    ("Warsaw", "Poland"),
    ("Bucharest", "Romania"),
    ("Belgrade", "Serbia"),
    ("Sarajevo",),
    ("Podgorica",),
    ("Pristina",),
    ("Skopje",),
    ("United States",),
    ("United Kingdom",),
    ("Arizona",),
    ("Hungary",),
    ("Luxembourg",),
    ("Chicago",),
    ("Budapest",),
]

# Build a single alternation pattern from all location strings.
_all_loc_strings = sorted(
    {loc for group in _EXPLICIT_LOCATIONS for loc in group},
    key=len, reverse=True,   # longest first so "Czech Republic" beats "Republic"
)
_LOCATION_MASK_RE: Final = re.compile(
    r"\b(" + "|".join(re.escape(l) for l in _all_loc_strings) + r")\b"
)

# ── Step 6: surviving employer name masking ────────────────────────────────────

# Employer names that the pipeline commonly misses (no Albanian keyword match,
# not in GLiNER training for this domain).  Listed explicitly when seen.
# Case-insensitive whole-word match.
_KNOWN_MISSED_EMPLOYERS: Final[list[str]] = [
    "INSPIRE11",
    "XANTERRA PARKS & RESORTS",
    "XANTERRA",
    "REDCLIFFE",
    "ATTF",
    "GLC",
    "Semos Education",
    "Semos",
    "Okionomotekniki",
]

_EMPLOYER_MASK_RE: Final = re.compile(
    r"\b(" + "|".join(re.escape(e) for e in _KNOWN_MISSED_EMPLOYERS) + r")\b",
    re.IGNORECASE,
)

# ── Step 7: surviving person masking ──────────────────────────────────────────

# Instructors/trainers with academic titles: "Dr. X Y", "Prof. Dr. X Y"
# Requires at least two name tokens after the title to avoid false positives.
_TITLED_PERSON_RE: Final = re.compile(
    r"\b(?:Prof\.?[^\S\n]+)?Dr\.?[^\S\n]+"
    r"[A-Z][a-zA-Z]+"
    r"(?:[^\S\n]+[A-Z][a-zA-Z]+)+"
    r"\b"
)

# Specific non-Albanian person names that the pipeline missed (no title).
# Extend this list as new names are confirmed in review.
_KNOWN_MISSED_PERSONS: Final[list[str]] = [
    "Mark Andrews",
]

# ── Step 8: surviving training provider / institution masking ─────────────────

# Online learning platforms — not tech tools, should be masked.
_KNOWN_MISSED_TRAINING: Final[list[str]] = [
    "Udemy",
]
_TRAINING_MASK_RE: Final = re.compile(
    r"\b(" + "|".join(re.escape(t) for t in _KNOWN_MISSED_TRAINING) + r")\b",
    re.IGNORECASE,
)

# High school / secondary institution names.
_QEMAL_STAFA_RE: Final = re.compile(
    r'[\u201c\u201d"]?Qemal Stafa[\u201c\u201d"]?\s*(?:High(?:\s+School)?)?',
    re.IGNORECASE,
)

# ── Step 9: education line normalization ──────────────────────────────────────

# Europass education entries where "MASTER" was absorbed into a removed ORG token,
# leaving "'S DEGREE" as a suffix attached to the date+location prefix.
# Pattern: "– [LOCATION], 'S DEGREE …"
_EDU_MASTERS_LINE_RE: Final = re.compile(
    r"^([ \t]*)([–—-]+[ \t]*)?\[LOCATION\][^'A-Za-z\n]*'S DEGREE",
    re.MULTILINE | re.IGNORECASE,
)

# Europass bachelor entries with garbled date prefix.
# Pattern: "– [LOCATION], , BACHELOR DEGREE …"
_EDU_BACHELOR_LINE_RE: Final = re.compile(
    r"^([ \t]*)([–—-]+[ \t]*)?\[LOCATION\][^\n]*?\bBACHELOR DEGREE\b",
    re.MULTILINE | re.IGNORECASE,
)

# Fully-tokenized date range line: "– [LOCATION], [LOCATION]" on its own.
_EDU_DATE_LINE_RE: Final = re.compile(
    r"^[ \t]*[–—-]+[ \t]*\[LOCATION\]\s*,\s*\[LOCATION\]\s*$",
    re.MULTILINE,
)

# Date line followed immediately by institution: "– [LOCATION], [UNIVERSITY]"
_EDU_DATE_UNI_LINE_RE: Final = re.compile(
    r"^[ \t]*[–—-]+[ \t]*\[LOCATION\]\s*,?\s*\[UNIVERSITY\]\s*$",
    re.MULTILINE,
)

# " - PROFILE: " connector between field title and profile description.
_PROFILE_PREFIX_RE: Final = re.compile(r"\s*-\s*PROFILE:\s*", re.IGNORECASE)

# "Universiteti Europian i [remainder]" institution fragment from PDF extraction.
_EUROPIAN_UNI_RE: Final = re.compile(
    r"\bUniversiteti\s+Europian\s+i\b[^,\[\n\)]*(?:,\s*\[LOCATION\])?",
    re.IGNORECASE,
)

# "(graduated at X)" parenthetical leftover from Europass education format.
_GRADUATED_AT_RE: Final = re.compile(r"\(graduated at [^\)\n]+\)", re.IGNORECASE)

# Quotes (ASCII or Unicode typographic) wrapping a semantic label — strip them.
# Handles PDFs that encode institution names as "Qemal Stafa" with curly quotes.
_QUOTED_LABEL_RE: Final = re.compile(
    r'["“”‘’"]'
    r'(\[(?:UNIVERSITY|COMPANY|TRAINING_PROVIDER|LOCATION|URL|PERSON)\])'
    r'["“”‘’"]?'
)

# ── Artifact cleanup ──────────────────────────────────────────────────────────

_DOUBLE_SPACE_RE:    Final = re.compile(r"  +")
_TRAILING_SPACE_RE:  Final = re.compile(r"[ \t]+$", re.MULTILINE)
_BLANK_LINE_RE:      Final = re.compile(r"\n{3,}")
_WHITESPACE_ONLY_RE: Final = re.compile(r"^[ \t]+$", re.MULTILINE)
# Lines that are only "–" or "— " (empty date-range lines after DOB removal)
_EMPTY_DASH_LINE_RE: Final = re.compile(r"^[ \t]*[–—-]+[ \t]*$", re.MULTILINE)
# "Address:" on its own line (value was already a pipeline token, now gone)
_BARE_ADDRESS_RE:    Final = re.compile(r"^[ \t]*Address\s*:?\s*$", re.MULTILINE)


class CVSanitiser:
    """Post-pipeline sanitiser.  Stateless — instantiate once and reuse."""

    def sanitise(
        self,
        anonymised_text: str,
        pii_map: dict[str, str] | None = None,
    ) -> str:
        """
        Produce a sanitised, scorer-ready version of an anonymised CV.

        Parameters
        ----------
        anonymised_text:
            Output of PIIPipeline.anonymise() — text with typed, indexed tokens.
        pii_map:
            Optional token → original value mapping.  When supplied, ORG
            classification uses keyword matching on the real name; technology
            tools are restored rather than masked.

        Returns
        -------
        str
            Clean text with all private fields removed, organisation names
            classified into semantic labels or restored (for tech tools), and
            explicit addresses/locations masked by a secondary pass.
        """
        text = self._clean_empty_field_labels(anonymised_text)
        text = self._repair_broken_words(text)
        text = self._replace_tokens(text, pii_map)
        text = self._fix_label_fragments(text)
        text = self._mask_explicit_addresses(text)
        text = self._mask_explicit_locations(text)
        text = self._mask_surviving_employers(text)
        text = self._mask_surviving_persons(text)
        text = self._mask_additional_training(text)
        text = self._normalise_education_lines(text)
        text = self._cleanup_artifacts(text)
        return text

    # ── Step 0: empty field label cleanup ─────────────────────────────────────

    def _clean_empty_field_labels(self, text: str) -> str:
        """
        Remove CV field labels whose value token has already been stripped
        or will be stripped (DOB, PHONE, EMAIL).  Avoids leaving behind
        artefacts like "Date of birth:  Phone number: (Mobile) Email address:".
        """
        for pat in _EMPTY_FIELD_PATTERNS:
            text = pat.sub("", text)
        return text

    # ── Step 1: broken-word repair ─────────────────────────────────────────────

    def _repair_broken_words(self, text: str) -> str:
        def _repair_suffix(m: re.Match) -> str:
            return _SUFFIX_REPAIR.get(m.group(1), m.group(0))

        def _repair_prefix(m: re.Match) -> str:
            repaired = _PREFIX_REPAIR.get(m.group(1))
            return repaired if repaired is not None else m.group(0)

        text = _SUFFIX_GLUE_RE.sub(_repair_suffix, text)
        text = _PREFIX_GLUE_RE.sub(_repair_prefix, text)
        return text

    # ── Step 2: token replacement ──────────────────────────────────────────────

    def _replace_tokens(self, text: str, pii_map: dict[str, str] | None) -> str:
        source = text  # pre-replacement snapshot for section-header scanning

        def _replace(m: re.Match) -> str:
            token_type = m.group(1)
            full_token = m.group(0)

            if token_type in _REMOVE_TYPES:
                return ""
            if token_type == "URL":
                return "[URL]"
            if token_type == "LOCATION":
                return "[LOCATION]"
            if token_type == "ORG":
                return self._classify_org(full_token, source, m.start(), pii_map)
            return ""

        return _TOKEN_RE.sub(_replace, text)

    # ── ORG classification ─────────────────────────────────────────────────────

    def _classify_org(
        self,
        full_token: str,
        source: str,
        token_start: int,
        pii_map: dict[str, str] | None,
    ) -> str:
        if pii_map is not None:
            original = pii_map.get(full_token)
            if original is not None:
                return self._classify_by_name(original, source, token_start)
            # Token not in map — fall through to section-based classification
        return self._classify_by_section(source, token_start)

    def _classify_by_name(
        self,
        original: str,
        source: str = "",
        token_start: int = 0,
    ) -> str:
        lowered = original.lower().strip()

        # Tech tool — restore the real name so skills are not masked
        if lowered in _TECH_TOOLS:
            return original.strip()

        # Garbage detection: pii_map value is a false positive
        # (multi-line paragraph, address fragment, etc.) — silently remove.
        # Note: "not in map" is handled before calling here (returns None),
        # so this only fires when the token IS in the map but the value is junk.
        if not lowered or "\n" in original or len(lowered) < 2:
            return ""

        if any(kw in lowered for kw in _ORG_UNIVERSITY_KWS):
            return "[UNIVERSITY]"
        if any(kw in lowered for kw in _ORG_TRAINING_KWS):
            return "[TRAINING_PROVIDER]"
        return "[COMPANY]"

    def _classify_by_section(self, source: str, token_start: int) -> str:
        headers = list(_SECTION_HEADER_RE.finditer(source[:token_start]))
        if not headers:
            return "[COMPANY]"
        nearest = headers[-1].group(1).lower().strip()
        if nearest in _EDUCATION_SECTIONS:
            return "[UNIVERSITY]"
        if nearest in _TRAINING_SECTIONS:
            return "[TRAINING_PROVIDER]"
        return "[COMPANY]"

    # ── Step 3: label-fragment cleanup ────────────────────────────────────────

    def _fix_label_fragments(self, text: str) -> str:
        """
        After replacement, a semantic label fused to a lowercase fragment
        (e.g. "[COMPANY]red goals") indicates a false-positive detection that
        absorbed the start of a real word.  Look up a repair; otherwise drop
        the label and keep only the fragment.
        """
        def _fix(m: re.Match) -> str:
            suffix = m.group(1)
            return _LABEL_SUFFIX_REPAIR.get(suffix, suffix)

        return _LABEL_FRAGMENT_RE.sub(_fix, text)

    # ── Step 4: explicit address masking ──────────────────────────────────────

    def _mask_explicit_addresses(self, text: str) -> str:
        """
        Replace surviving street-level address content with [ADDRESS_REDACTED].
        Preserves "Business or Sector" and similar labels that may precede
        "Address" on the same line.
        """
        text = _ADDRESS_CONTENT_RE.sub(r"Address [ADDRESS_REDACTED]", text)
        text = _BARE_ADDRESS_RE.sub("", text)
        return text

    # ── Step 5: explicit location masking ─────────────────────────────────────

    def _mask_explicit_locations(self, text: str) -> str:
        """
        Mask world cities and countries that the pipeline missed because
        they are not in the Albanian-focused city list.
        """
        return _LOCATION_MASK_RE.sub("[LOCATION]", text)

    # ── Step 6: surviving employer masking ────────────────────────────────────

    def _mask_surviving_employers(self, text: str) -> str:
        """
        Mask known employer names that the pipeline did not detect.
        This list is extended whenever a new name is confirmed in review.
        """
        return _EMPLOYER_MASK_RE.sub("[COMPANY]", text)

    # ── Step 7: surviving person masking ──────────────────────────────────────

    def _mask_surviving_persons(self, text: str) -> str:
        """
        Mask instructor/trainer names that the pipeline missed.

        Two paths:
        - Titled persons (Dr., Prof.) detected via regex.
        - Specific untitled names added to _KNOWN_MISSED_PERSONS.
        """
        text = _TITLED_PERSON_RE.sub("[PERSON]", text)
        for name in _KNOWN_MISSED_PERSONS:
            text = re.sub(rf"\b{re.escape(name)}\b", "[PERSON]", text, flags=re.IGNORECASE)
        return text

    # ── Step 8: surviving training provider / institution masking ─────────────

    def _mask_additional_training(self, text: str) -> str:
        """Mask online learning platforms and named high schools."""
        text = _TRAINING_MASK_RE.sub("[TRAINING_PROVIDER]", text)
        text = _QEMAL_STAFA_RE.sub("[UNIVERSITY]", text)
        # Strip ASCII or Unicode typographic quotes that wrapped the institution name
        text = _QUOTED_LABEL_RE.sub(r"\1", text)
        return text

    # ── Step 9: education line normalization ──────────────────────────────────

    def _normalise_education_lines(self, text: str) -> str:
        """
        Repair Europass education entries garbled by PDF extraction and
        PII token removal.

        - "'S DEGREE" prefix artifact → "Master's Degree —"
        - "BACHELOR DEGREE" with garbled prefix → "Bachelor Degree —"
        - "– [LOCATION], [LOCATION]" date lines → "[DATE_RANGE]"
        - "– [LOCATION], [UNIVERSITY]" date+institution lines →
          "[DATE_RANGE]\\n[UNIVERSITY]"
        - "Universiteti Europian i …" fragment → "[UNIVERSITY]"
        - "(graduated at …)" parentheticals → removed
        """
        def _replace_masters(m: re.Match) -> str:
            prefix = m.group(1)
            return f"{prefix}[DATE_RANGE]\n{prefix}Master's Degree —"

        def _replace_bachelor(m: re.Match) -> str:
            prefix = m.group(1)
            return f"{prefix}[DATE_RANGE]\n{prefix}Bachelor Degree —"

        text = _EDU_MASTERS_LINE_RE.sub(_replace_masters, text)
        text = _EDU_BACHELOR_LINE_RE.sub(_replace_bachelor, text)
        # Clean "— - " produced when the field starts with a dash separator
        text = re.sub(r"—\s*-\s*", "— ", text)
        # Clean "- PROFILE: " from degree field descriptions
        text = _PROFILE_PREFIX_RE.sub(", ", text)
        # Fully-tokenized date lines in education
        text = _EDU_DATE_LINE_RE.sub("[DATE_RANGE]", text)
        # Date line with institution on same line
        text = _EDU_DATE_UNI_LINE_RE.sub("[DATE_RANGE]\n[UNIVERSITY]", text)
        # Institution name fragment spanning lines
        text = _EUROPIAN_UNI_RE.sub("[UNIVERSITY]", text)
        # "(graduated at X)" parentheticals
        text = _GRADUATED_AT_RE.sub("", text)
        # Move [UNIVERSITY] to its own line when appended to a degree title line
        text = re.sub(
            r"((?:Master'?s|Bachelor) Degree\s*[^\n]+?)\s*,?\s*\[UNIVERSITY\]"
            r"(?:\s*,\s*\[LOCATION\])?",
            r"\1\n[UNIVERSITY]",
            text,
            flags=re.IGNORECASE,
        )
        return text

    # ── Step 10: artifact cleanup ──────────────────────────────────────────────

    def _cleanup_artifacts(self, text: str) -> str:
        text = _WHITESPACE_ONLY_RE.sub("", text)
        text = _EMPTY_DASH_LINE_RE.sub("", text)
        text = _BARE_ADDRESS_RE.sub("", text)
        text = _TRAILING_SPACE_RE.sub("", text)
        text = _BLANK_LINE_RE.sub("\n\n", text)
        text = _DOUBLE_SPACE_RE.sub(" ", text)
        return text
