"""Unit tests for CVSanitiser."""
from __future__ import annotations

import pytest
from src.pii.sanitiser import CVSanitiser


@pytest.fixture
def s() -> CVSanitiser:
    return CVSanitiser()


# ── Token removal ──────────────────────────────────────────────────────────────

class TestTokenRemoval:
    def test_person_removed(self, s):
        assert "[PERSON_1]" not in s.sanitise("[PERSON_1]\nSoftware Engineer")

    def test_email_removed(self, s):
        assert "[EMAIL" not in s.sanitise("Email: [EMAIL_1]")

    def test_phone_removed(self, s):
        assert "[PHONE" not in s.sanitise("Phone: [PHONE_1]")

    def test_address_removed(self, s):
        assert "[ADDRESS" not in s.sanitise("Address: [ADDRESS_1]")

    def test_dob_removed(self, s):
        assert "[DOB" not in s.sanitise("DOB: [DOB_1]")

    def test_al_nid_removed(self, s):
        assert "[AL_NID" not in s.sanitise("ID: [AL_NID_1]")

    def test_passport_removed(self, s):
        assert "[PASSPORT" not in s.sanitise("Passport: [PASSPORT_1]")

    def test_marital_removed(self, s):
        assert "[MARITAL" not in s.sanitise("Marital Status: [MARITAL_1]")

    def test_gender_removed(self, s):
        assert "[GENDER" not in s.sanitise("[GENDER_1]")

    def test_religion_removed(self, s):
        assert "[RELIGION" not in s.sanitise("Religion: [RELIGION_1]")


# ── Token label normalisation ──────────────────────────────────────────────────

class TestLabelNormalisation:
    def test_url_collapsed(self, s):
        result = s.sanitise("LinkedIn: [URL_1]")
        assert "[URL]" in result
        assert "[URL_1]" not in result

    def test_location_collapsed(self, s):
        result = s.sanitise("Based in [LOCATION_3]")
        assert "[LOCATION]" in result
        assert "[LOCATION_3]" not in result

    def test_multiple_urls_all_collapsed(self, s):
        result = s.sanitise("[URL_1] and [URL_2]")
        assert result.count("[URL]") == 2

    def test_multiple_locations_all_collapsed(self, s):
        result = s.sanitise("[LOCATION_1], [LOCATION_2]")
        assert result.count("[LOCATION]") == 2


# ── ORG classification — pii_map path ─────────────────────────────────────────

class TestOrgClassificationWithMap:
    def test_company(self, s):
        pii_map = {"[ORG_1]": "Credins Bank"}
        result = s.sanitise("Employer: [ORG_1]", pii_map)
        assert "[COMPANY]" in result

    def test_university_keyword(self, s):
        pii_map = {"[ORG_1]": "University of Tirana"}
        result = s.sanitise("Education: [ORG_1]", pii_map)
        assert "[UNIVERSITY]" in result

    def test_college_keyword(self, s):
        pii_map = {"[ORG_1]": "London College of Finance"}
        result = s.sanitise("[ORG_1]", pii_map)
        assert "[UNIVERSITY]" in result

    def test_polytechnic_keyword(self, s):
        pii_map = {"[ORG_1]": "Polytechnic University of Tirana"}
        result = s.sanitise("[ORG_1]", pii_map)
        assert "[UNIVERSITY]" in result

    def test_training_provider_keyword(self, s):
        pii_map = {"[ORG_1]": "AAB Training Centre"}
        result = s.sanitise("[ORG_1]", pii_map)
        assert "[TRAINING_PROVIDER]" in result

    def test_academy_keyword(self, s):
        pii_map = {"[ORG_1]": "Vienna Banking Institute"}
        result = s.sanitise("[ORG_1]", pii_map)
        assert "[TRAINING_PROVIDER]" in result

    def test_university_beats_training(self, s):
        # "Academy of" has training keyword but should lose to university
        pii_map = {"[ORG_1]": "University Training Academy"}
        result = s.sanitise("[ORG_1]", pii_map)
        assert "[UNIVERSITY]" in result

    def test_unknown_org_defaults_company(self, s):
        pii_map = {"[ORG_1]": "Zogu i Zi Solutions"}
        result = s.sanitise("[ORG_1]", pii_map)
        assert "[COMPANY]" in result

    def test_token_not_in_map_defaults_company(self, s):
        pii_map = {}  # empty map
        result = s.sanitise("[ORG_1]", pii_map)
        assert "[COMPANY]" in result


# ── ORG classification — section header fallback ───────────────────────────────

class TestOrgClassificationBySection:
    def test_education_section_yields_university(self, s):
        text = "EDUCATION\n[ORG_1]\nBachelor of Economics"
        result = s.sanitise(text)
        assert "[UNIVERSITY]" in result

    def test_training_section_yields_training_provider(self, s):
        text = "CERTIFICATIONS\n[ORG_1] — Certified Banker"
        result = s.sanitise(text)
        assert "[TRAINING_PROVIDER]" in result

    def test_experience_section_yields_company(self, s):
        text = "WORK EXPERIENCE\n[ORG_1] — Senior Analyst"
        result = s.sanitise(text)
        assert "[COMPANY]" in result

    def test_no_header_defaults_company(self, s):
        result = s.sanitise("[ORG_1]")
        assert "[COMPANY]" in result

    def test_nearest_header_wins(self, s):
        text = "EDUCATION\n[ORG_1]\n\nWORK EXPERIENCE\n[ORG_2]"
        result = s.sanitise(text)
        assert "[UNIVERSITY]" in result
        assert "[COMPANY]" in result


# ── Broken word repair ─────────────────────────────────────────────────────────

class TestBrokenWordRepair:
    def test_suffix_include(self, s):
        result = s.sanitise("wide variety [ORG_3]luding")
        assert "including" in result

    def test_suffix_income(self, s):
        result = s.sanitise("[ORG_39]ome statement")
        assert "income statement" in result

    def test_suffix_increase(self, s):
        result = s.sanitise("[ORG_1]rease in revenue")
        assert "increase" in result

    def test_suffix_corporate(self, s):
        result = s.sanitise("[ORG_2]orate governance")
        assert "corporate" in result

    def test_suffix_bachelor(self, s):
        result = s.sanitise("[PASSPORT_1]chelor of Science")
        assert "bachelor" in result

    def test_unknown_suffix_leaves_token_for_replacement(self, s):
        # "xyz" is not in _SUFFIX_REPAIR — token is not repaired and
        # gets replaced by its label (or removed) normally
        result = s.sanitise("[ORG_1]xyz")
        assert "[ORG_" not in result   # token was still replaced
        assert "xyz" in result          # dangling suffix preserved


# ── Artifact cleanup ───────────────────────────────────────────────────────────

class TestArtifactCleanup:
    def test_double_space_collapsed(self, s):
        result = s.sanitise("Phone:  [PHONE_1]")
        assert "  " not in result

    def test_whitespace_only_line_removed(self, s):
        text = "Senior Analyst\n[GENDER_1]\nExperience in finance"
        result = s.sanitise(text)
        # The gender token line becomes whitespace-only after removal;
        # it should not leave a blank line that breaks the paragraph.
        lines = result.splitlines()
        assert not any(line.strip() == "" and line != "" for line in lines)

    def test_three_blank_lines_collapsed_to_two(self, s):
        result = s.sanitise("Section A\n\n\n\nSection B")
        assert "\n\n\n" not in result

    def test_trailing_spaces_removed(self, s):
        result = s.sanitise("Software Engineer   ")
        assert not result.rstrip("\n").endswith(" ")


# ── End-to-end integration ─────────────────────────────────────────────────────

class TestEndToEnd:
    def test_realistic_cv_snippet(self, s):
        anonymised = (
            "[PERSON_1]\n"
            "Senior Relationship Manager\n\n"
            "PERSONAL INFORMATION\n"
            "Email: [EMAIL_1]\n"
            "Phone: [PHONE_1]\n"
            "Address: [ADDRESS_1]\n"
            "DOB: [DOB_1]\n"
            "Gender: [GENDER_1]\n\n"
            "WORK EXPERIENCE\n"
            "[ORG_1] — Senior Analyst\n"
            "2019–2023 | [LOCATION_1]\n"
            "- Managed [ORG_2] portfolio of 120 SME clients\n"
            "- Grew [ORG_3]ome by 34% YoY\n\n"
            "EDUCATION\n"
            "[ORG_4] — Bachelor of Economics\n"
            "2014–2018\n\n"
            "CERTIFICATIONS\n"
            "[ORG_5] — Risk Management Certificate\n"
        )
        pii_map = {
            "[ORG_1]": "Union Financial Bank",
            "[ORG_2]": "Banka e Shqiperise",
            "[ORG_3]": "Macro Inc",         # will trigger "ome" suffix repair
            "[ORG_4]": "University of Tirana",
            "[ORG_5]": "AAB Training Centre",
        }

        result = s.sanitise(anonymised, pii_map)

        # Private fields gone
        assert "[PERSON" not in result
        assert "[EMAIL" not in result
        assert "[PHONE" not in result
        assert "[ADDRESS" not in result
        assert "[DOB" not in result
        assert "[GENDER" not in result

        # ORG labels correctly classified
        assert "[COMPANY]" in result
        assert "[UNIVERSITY]" in result
        assert "[TRAINING_PROVIDER]" in result

        # Location normalised
        assert "[LOCATION]" in result
        assert "[LOCATION_1]" not in result

        # Broken word repaired
        assert "income" in result

        # Professional content preserved
        assert "Senior Relationship Manager" in result
        assert "Bachelor of Economics" in result
        assert "Risk Management Certificate" in result
        assert "120 SME clients" in result
        assert "34%" in result
