"""
Layer 2 — Heuristic NER recogniser.

Simulates GLiNER-Multi for the test environment. In production this module
is replaced by a real multilingual NER:

    from gliner import GLiNER
    model = GLiNER.from_pretrained("urchade/gliner_multi_pii-v1")
    entities = model.predict_entities(text, labels=[
        "person name", "home address", "city", "organisation", ...
    ])

This implementation uses curated lists + heuristics, which is sufficient
for regression testing but should NOT be used in production. Production
needs the actual multilingual NER for unseen names and contextual
understanding.
"""
import re
from typing import List, Tuple

__all__ = ["HeuristicNERRecogniser"]


class HeuristicNERRecogniser:
    """
    Fallback NER for environments where the GLiNER model can't be loaded.

    Catches:
      - Albanian first/last names from a curated seed list
      - Location names from a static city list
      - Address blocks anchored on Albanian street keywords
      - Organisations with Albanian/EU legal-form suffixes
      - Education institutions
    """

    # Albanian + regional cities (extend as needed)
    AL_CITIES = {
        "Tirana", "Tiranë", "Tirane", "Durrës", "Durres", "Vlorë", "Vlore",
        "Shkodër", "Shkoder", "Elbasan", "Korçë", "Korce", "Fier", "Berat",
        "Lushnjë", "Pogradec", "Kavajë", "Gjirokastër", "Sarandë", "Saranda",
        "Koplik", "Lezhë", "Kukës", "Përmet", "Permet", "Bual", "Tropojë",
        "Prishtinë", "Pristina", "Prizren", "Peja",
        "Albania", "Albanian", "Shqipëri", "Shqiperi",
        # Tirana neighbourhoods (frequently appear in CVs)
        "Kombinat", "Astir", "Zogu i Zi", "Komuna e Parisit", "Blloku",
        "21 Dhjetori", "Don Bosko", "Lapraka",
    }

    AL_ADDRESS_TOKENS = {
        "rruga", "rr.", "rr ", "pallati", "pall.", "apartamenti", "ap.",
        "ap ", "lagjja", "lagja", "lagje", "njësia", "njesia", "blloku",
        "shesh", "sheshi", "kati", "shkalla", "hyrja",
    }

    AL_FIRST_NAMES = {
        "astrit", "qerime", "blerina", "zgjatje", "ardit", "besnik", "bujar",
        "dritan", "edmond", "endrit", "enver", "fatmir", "florian", "gentian",
        "ilir", "jorgo", "klodian", "luan", "mentor", "petrit", "saimir",
        "agim", "albert", "alfred", "altin", "armand", "arben", "arta",
        "blerta", "diana", "drita", "edi", "elona", "ermal", "fatos",
        "festim", "gentiana", "halil", "ilirjana", "klodiana", "lindita",
        "manjola", "merita", "miranda", "nora", "olta", "pranvera", "rezarta",
        "sara", "shpresa", "valbona", "vera", "vjollca", "yllka",
        "eliona", "ardian", "migena", "arber", "arbër", "mirela",
    }

    AL_LAST_NAMES = {
        "patozi", "dallku", "koçi", "koci", "ndregjoni", "hoxha", "hoxhaj",
        "krasniqi", "berisha", "kelmendi", "shehu", "sula", "frashëri",
        "frasheri", "gjoni", "marku", "kola", "luka", "leka", "leska",
        "noli", "rexhepi", "selmani", "tafa", "veliu", "xhafa", "ymeri",
        "zeneli", "shkurti", "braho", "metaçi", "metaci", "kodra",
    }

    ORG_SUFFIXES = [
        r"sh\.?p\.?k\.?", r"sh\.?a\.?", r"L\.?L\.?C\.?", r"Ltd\.?",
        r"Inc\.?", r"S\.?p\.?A\.?", r"GmbH",
    ]

    KNOWN_ORG_KEYWORDS = {
        # Banking / finance / telecoms — common employers
        "bank", "banka", "telecom", "albtelecom", "credins", "raiffeisen",
        "intesa", "abi", "tirana", "alpha", "bkt", "kombetare", "kombëtare",
        "softec", "century", "imobiliare", "consult", "konsult", "solutions",
        "albania", "shqiperi", "shqipëri", "albasoft", "ict",
        # Government / public sector
        "bashkia", "ministria", "ministry", "qkb", "ashk", "drejtoria",
        "spitali", "spitalit", "prefektura",
    }

    EDU_KEYWORDS = {
        "university", "universiteti", "polytechnic", "politechnic",
        "gjimnazi", "shkolla", "fakulteti", "akademia", "instituti",
        "school", "academy", "institute", "college", "kolegji",
    }

    def detect(self, text: str) -> List[Tuple[str, str, int, int]]:
        results: List[Tuple[str, str, int, int]] = []

        # Cities → LOCATION
        for city in self.AL_CITIES:
            for m in re.finditer(rf"\b{re.escape(city)}\b", text):
                results.append(("LOCATION", m.group(), m.start(), m.end()))

        # Address blocks
        addr_pattern = re.compile(
            r"\b(?:Rruga|Rr\.?)\s+[^\n,]+(?:,\s*[^\n,]+){0,4}",
            re.IGNORECASE,
        )
        for m in addr_pattern.finditer(text):
            results.append(("ADDRESS", m.group().strip(), m.start(), m.end()))

        # Person names — heuristic: TitleCase pair where one token is in
        # Albanian first/last name list. Compound names (hyphenated) supported.
        name_pattern = re.compile(
            r"\b[A-ZÇËÄ][a-zçëä]+(?:[-'][A-ZÇËÄ][a-zçëä]+)?"
            r"(?:\s+[A-ZÇËÄ][a-zçëä']+){1,3}\b"
        )
        for m in name_pattern.finditer(text):
            tokens_lower = [t.lower().rstrip("'") for t in re.split(r"[\s\-]", m.group())]
            if any(t in self.AL_FIRST_NAMES for t in tokens_lower) or \
               any(t in self.AL_LAST_NAMES for t in tokens_lower):
                results.append(("PERSON", m.group(), m.start(), m.end()))

        # Organisations — legal-form suffix
        for suffix in self.ORG_SUFFIXES:
            org_pat = re.compile(rf"\b[A-Z][\w\-&.\s]{{2,40}}\s+{suffix}", re.IGNORECASE)
            for m in org_pat.finditer(text):
                results.append(("ORG", m.group().strip(), m.start(), m.end()))

        # Organisations — TitleCase with known keyword
        title_phrase = re.compile(
            r"\b[A-Z][\w&]{2,}(?:\s+(?:[A-Z][\w&]{1,}|[a-z]{2,3}\.?|of|the|de|al))?"
            r"(?:\s+[A-Z][\w&]{2,})?(?:\s+[A-Z][\w&]{2,})?\b"
        )
        for m in title_phrase.finditer(text):
            phrase = m.group()
            tokens = phrase.lower().split()
            if any(t.rstrip(".,") in self.KNOWN_ORG_KEYWORDS for t in tokens):
                # Skip if it looks like an address line
                if not any(addr in phrase.lower() for addr in ["rruga", "pall.", "pallati"]):
                    results.append(("ORG", phrase, m.start(), m.end()))

        # Education institutions
        for kw in self.EDU_KEYWORDS:
            edu_pat = re.compile(
                rf"\b(?:{kw})\s+(?:of\s+|i\s+|e\s+|'[^']+'\s*)?[\w\s,\-']{{3,80}}?"
                rf"(?=\s*[—,|\n])",
                re.IGNORECASE,
            )
            for m in edu_pat.finditer(text):
                value = m.group().strip().rstrip(",|—-")
                if len(value) > 8:
                    results.append(("ORG", value, m.start(), m.end()))

        return results
