"""Unit tests for all three recogniser layers."""
import pytest

from src.pii.recognisers.pattern import PatternRecogniser
from src.pii.recognisers.ner_heuristic import HeuristicNERRecogniser
from src.pii.recognisers.personal_facts import PersonalFactsRecogniser


def _types(results, etype: str) -> list[str]:
    return [text for typ, text, _, _ in results if typ == etype]


# ══════════════════════════════════════════════════════════════════
# PatternRecogniser
# ══════════════════════════════════════════════════════════════════

class TestPatternRecogniser:
    def setup_method(self):
        self.p = PatternRecogniser()

    def detect(self, text: str):
        return self.p.detect(text)

    # --- EMAIL ---

    def test_email_basic(self):
        results = self.detect("Contact: astrit.patozi@gmail.com today.")
        emails = _types(results, "EMAIL")
        assert "astrit.patozi@gmail.com" in emails

    def test_email_work_domain(self):
        results = self.detect("Work: a.hoxhaj@finance-consult.al")
        emails = _types(results, "EMAIL")
        assert "a.hoxhaj@finance-consult.al" in emails

    def test_email_multiple(self):
        results = self.detect(
            "Personal: qerime.dallku@gmail.com\nWork: qerime@credinsbank.al"
        )
        emails = _types(results, "EMAIL")
        assert len(emails) >= 2

    # --- PHONE ---

    def test_phone_intl_plus355(self):
        results = self.detect("Tel: +355 69 234 5678")
        phones = _types(results, "PHONE")
        assert any("355" in p for p in phones)

    def test_phone_local_06x(self):
        results = self.detect("Mobile: 068 441 2233")
        phones = _types(results, "PHONE")
        assert any("068" in p for p in phones)

    def test_phone_intl_00355(self):
        results = self.detect("Alt: 00355 68 332 1900")
        phones = _types(results, "PHONE")
        assert any("00355" in p for p in phones)

    def test_phone_dashes(self):
        results = self.detect("Mobile: 068-227-9810")
        phones = _types(results, "PHONE")
        assert any("068" in p for p in phones)

    # --- ID NUMBERS ---

    def test_al_nid(self):
        results = self.detect("National ID: J90217045L")
        types = [t for t, _, _, _ in results]
        assert "AL_NID" in types

    def test_passport(self):
        results = self.detect("Passport: BA4589201")
        types = [t for t, _, _, _ in results]
        assert "PASSPORT" in types

    def test_second_id(self):
        results = self.detect("National ID: K60904123M")
        types = [t for t, _, _, _ in results]
        assert "AL_NID" in types

    # --- DOB ---

    def test_dob_english_month(self):
        results = self.detect("Born: 17 February 1989")
        dobs = _types(results, "DOB")
        assert any("1989" in d for d in dobs)

    def test_dob_numeric(self):
        results = self.detect("DOB: 04/09/1996")
        dobs = _types(results, "DOB")
        assert any("1996" in d for d in dobs)

    def test_dob_march(self):
        results = self.detect("Date of Birth: 14 March 2000")
        dobs = _types(results, "DOB")
        assert any("2000" in d for d in dobs)

    # --- URL ---

    def test_linkedin_url(self):
        results = self.detect("linkedin.com/in/astritpatozi")
        urls = _types(results, "URL")
        assert any("linkedin" in u for u in urls)

    def test_github_url(self):
        results = self.detect("github.com/astritpatozi")
        urls = _types(results, "URL")
        assert any("github" in u for u in urls)

    def test_linkedin_finance(self):
        results = self.detect("LinkedIn: linkedin.com/in/eliona-shkurti-finance")
        urls = _types(results, "URL")
        assert any("eliona" in u for u in urls)


# ══════════════════════════════════════════════════════════════════
# HeuristicNERRecogniser
# ══════════════════════════════════════════════════════════════════

class TestHeuristicNERRecogniser:
    def setup_method(self):
        self.h = HeuristicNERRecogniser()

    def detect(self, text: str):
        return self.h.detect(text)

    # --- PERSON names ---

    def test_person_known_first_last(self):
        results = self.detect("Astrit Patozi\nSoftware Developer")
        persons = _types(results, "PERSON")
        assert any("Astrit" in p for p in persons)

    def test_person_last_name_only_in_set(self):
        results = self.detect("Qerime Dallku\nIT Support Specialist")
        persons = _types(results, "PERSON")
        assert any("Dallku" in p for p in persons)

    def test_person_compound_name(self):
        results = self.detect("Name: Arbër-Luan Hoxhaj")
        persons = _types(results, "PERSON")
        assert any("Hoxhaj" in p for p in persons)

    def test_person_reference(self):
        results = self.detect("Reference: Ilir Metaçi, Union Financial Bank")
        persons = _types(results, "PERSON")
        assert any("Ilir" in p or "Metaçi" in p for p in persons)

    # --- LOCATION ---

    def test_location_tirana(self):
        results = self.detect("Based in Tirana, Albania.")
        locs = _types(results, "LOCATION")
        assert "Tirana" in locs

    def test_location_albania(self):
        results = self.detect("Nationality: Albanian")
        locs = _types(results, "LOCATION")
        assert any("Albania" in l or "Albanian" in l for l in locs)

    def test_location_koplik(self):
        results = self.detect("City: Koplik, Shkodër")
        locs = _types(results, "LOCATION")
        assert "Koplik" in locs

    def test_location_neighbourhood(self):
        results = self.detect("Neighbourhood: Kombinat, Tiranë")
        locs = _types(results, "LOCATION")
        assert "Kombinat" in locs

    # --- ADDRESS ---

    def test_address_rruga(self):
        results = self.detect("Address: Rruga Myslym Shyri, Pallati 7, Ap. 12")
        addrs = _types(results, "ADDRESS")
        assert len(addrs) >= 1
        assert any("Myslym" in a for a in addrs)

    def test_address_rr_abbrev(self):
        results = self.detect("Rruga Skenderbej, Pall. 2, Ap. 4")
        addrs = _types(results, "ADDRESS")
        assert len(addrs) >= 1

    # --- ORG ---

    def test_org_bank_keyword(self):
        results = self.detect("Employer: Credins Bank")
        orgs = _types(results, "ORG")
        assert any("Credins" in o or "Bank" in o for o in orgs)

    def test_org_edu_institution(self):
        results = self.detect("Education: University of Tirana\n")
        orgs = _types(results, "ORG")
        assert any("University" in o or "Tirana" in o for o in orgs)


# ══════════════════════════════════════════════════════════════════
# PersonalFactsRecogniser
# ══════════════════════════════════════════════════════════════════

class TestPersonalFactsRecogniser:
    def setup_method(self):
        self.pf = PersonalFactsRecogniser()

    def detect(self, text: str):
        return self.pf.detect(text)

    def _all_text(self, results) -> list[str]:
        return [text for _, text, _, _ in results]

    def test_marital_married(self):
        results = self.detect("Marital Status: Married")
        texts = self._all_text(results)
        assert any("Married" in t for t in texts)

    def test_marital_single(self):
        results = self.detect("Marital Status: Single")
        texts = self._all_text(results)
        assert any("Single" in t for t in texts)

    def test_gender_male(self):
        results = self.detect("Gender: Male")
        texts = self._all_text(results)
        assert any("Male" in t for t in texts)

    def test_gender_female(self):
        results = self.detect("Gender: Female")
        texts = self._all_text(results)
        assert any("Female" in t for t in texts)

    def test_gender_standalone_line(self):
        results = self.detect("\nFemale\n")
        texts = self._all_text(results)
        assert any("Female" in t for t in texts)

    def test_religion_muslim(self):
        results = self.detect("Religion: Muslim")
        texts = self._all_text(results)
        assert any("Muslim" in t or "Religion" in t for t in texts)
