"""
Curated PII ground truth for the six test fixtures (section 11 of CLAUDE.md).

Keys are fixture stem names (without extension).
Values are dicts mapping entity_type → list of expected PII strings.
"""

GROUND_TRUTH: dict[str, dict[str, list[str]]] = {
    "cv_clean_backend": {
        "PERSON": ["Astrit Patozi"],
        "EMAIL": ["astrit.patozi@gmail.com"],
        "PHONE": ["+355 69 234 5678"],
        "URL": ["linkedin.com/in/astritpatozi", "github.com/astritpatozi"],
        "ADDRESS": ["Rruga Myslym Shyri, Pallati 7, Ap. 12"],
        "ORG": ["FinBridge Solutions", "Softec Albania", "AlbaSoft", "Polytechnic University of Tirana"],
        "LOCATION": ["Tirana", "Albania"],
    },
    "cv_clean_it_support": {
        "PERSON": ["Qerime Dallku"],
        "EMAIL": ["qerime.dallku@gmail.com"],
        "PHONE": ["+355 68 512 3490"],
        "URL": ["linkedin.com/in/qerimedallku"],
        "ADDRESS": ["Rruga e Kavajes, Pallati 14, Ap. 5"],
        "ORG": ["Credins Bank", "Albtelecom", "ICT Solutions Albania", "University of Tirana"],
        "LOCATION": ["Tirana", "Tiranë", "Albania"],
    },
    "cv_clean_sales": {
        "PERSON": ["Blerina Koçi"],
        "EMAIL": ["blerina.koci@gmail.com"],
        "PHONE": ["+355 67 389 2145"],
        "URL": ["linkedin.com/in/blerinakoci"],
        "ADDRESS": ["Rruga Sami Frasheri, Pallati 3, Ap. 8"],
        "ORG": ["Koleka Imobiliare", "Pro-Konsult", "Century 21 Albania", "University of Tirana"],
        "LOCATION": ["Tirana", "Tiranë", "Albania"],
        "DOB": ["14 March 2000"],
    },
    "cv_clean_bank_teller": {
        "PERSON": ["Zgjatje Ndregjoni"],
        "EMAIL": ["zgjatje.ndregjoni@gmail.com"],
        "PHONE": ["+355 69 471 8823"],
        "ADDRESS": ["Rruga Skenderbej, Pall. 2, Ap. 4"],
        "LOCATION": ["Koplik", "Shkodër", "Albania"],
        "ORG": ["Banka Kombëtare Tregtare", "BKT", "Bashkia Koplik", "Universiteti 'Luigj Gurakuqi'"],
        "DOB": ["22 July 2001"],
    },
    "cv_dense_sme_banker": {
        "PERSON": ["Arbër-Luan Hoxhaj", "Ilir Metaçi", "Mirela Kodra"],
        "EMAIL": [
            "arber.hoxhaj1989@gmail.com",
            "a.hoxhaj@finance-consult.al",
            "ilir.metaci@ufbank.al",
            "m.kodra@smefinance.al",
        ],
        "PHONE": [
            "+355 69 782 4411",
            "00355 68 332 1900",
            "+355 67 908 1122",
            "068 441 2233",
        ],
        "URL": ["linkedin.com/in/arber-luan-hoxhaj"],
        "ADDRESS": ['Rruga "Myslym Shyri", Pallati Edil-AL, Shkalla 2, Ap. 14'],
        "DOB": ["17 February 1989"],
        "ID_NUMBER": ["J90217045L", "BA4589201"],
        "ORG": [
            "Banka e Shqipërisë Tregtare",
            "Union Financial Bank",
            "CrediPlus Microfinance",
            "University of Tirana",
            "European University of Tirana",
            "Albanian Association of Banks",
            "Vienna Banking Institute",
            "AAB Training Centre",
        ],
        "LOCATION": ["Tirana", "Tiranë", "Albania", "Kukës", "Durrës"],
        "PERSONAL_FACT": ["Married", "Male"],
    },
    "cv_ocr_damaged_sales": {
        "PERSON": ["Eliona Shkurti", "Ardian Leska", "Migena Braho"],
        "EMAIL": [
            "eliona.shkurti@gmail.com",
            "e.shkurti@outlook.com",
            "ardian.leska@tmc.al",
            "m.braho@finance-team.al",
        ],
        "PHONE": [
            "+355 69 440 7219",
            "068-227-9810",
            "+355 67 555 9011",
            "069 889 1222",
        ],
        "URL": ["linkedin.com/in/eliona-shkurti-finance"],
        "ADDRESS": ["Rruga e Durrësit, Pall. 88, Hyrja B, Ap. 21"],
        "DOB": ["04/09/1996"],
        "ID_NUMBER": ["K60904123M", "BA1193308"],
        "ORG": [
            "Tirana Micro Credit",
            "MoneyPay Albania",
            "Municipality Finance Office",
            "University of Tirana",
            "tmc.al",
            "finance-team.al",
        ],
        "LOCATION": [
            "Tiranë", "Tirana", "Durrës", "Albanian", "Albania",
            "Kombinat", "Astir", "Zogu i Zi",
        ],
        "PERSONAL_FACT": ["Female", "Single"],
    },
}
