"""Sample JSON API responses for testing."""

from typing import Any

SAMPLE_HOURLY_RESPONSE_BASIC: dict[str, Any] = {
    "results": {
        "listeDonneesConsoEnergieHoraire": [
            {
                "dateHeureDebutPeriode": "2024-11-26 00:00",
                "consoReg": 1.234,
                "consoHaut": None,
                "consoTotal": 1.234,
            },
            {
                "dateHeureDebutPeriode": "2024-11-26 01:00",
                "consoReg": 1.567,
                "consoHaut": None,
                "consoTotal": 1.567,
            },
            {
                "dateHeureDebutPeriode": "2024-11-26 02:00",
                "consoReg": 1.890,
                "consoHaut": None,
                "consoTotal": 1.890,
            },
        ]
    }
}

SAMPLE_HOURLY_RESPONSE_DT: dict[str, Any] = {
    "results": {
        "listeDonneesConsoEnergieHoraire": [
            {
                "dateHeureDebutPeriode": "2024-11-26 00:00",
                "consoReg": 0.500,
                "consoHaut": 0.734,
                "consoTotal": 1.234,
            },
            {
                "dateHeureDebutPeriode": "2024-11-26 01:00",
                "consoReg": 0.600,
                "consoHaut": 0.967,
                "consoTotal": 1.567,
            },
        ]
    }
}

SAMPLE_CONTRACT_INFO: dict[str, Any] = {
    "noContrat": "test_contract_id",
    "adresse": "123 Test St",
    "tarif": "D",
    "optionTarif": "",
}

SAMPLE_ACCOUNT_INFO: dict[str, Any] = {
    "noCompte": "test_account_id",
    "solde": 123.45,
}

SAMPLE_CUSTOMER_INFO: dict[str, Any] = {
    "noClient": "test_customer_id",
    "nom": "Test Customer",
}

SAMPLE_PEAK_EVENT: dict[str, Any] = {
    "dateDebut": "2024-12-15 13:00:00",
    "dateFin": "2024-12-15 17:00:00",
    "plageHoraire": "13-17",
    "secteurClient": "Residentiel",
}

SAMPLE_WINTER_CREDIT_DATA: dict[str, Any] = {
    "creditCumule": 5.25,
    "performanceHier": "Good",
    "heurePointe": "17",
}
