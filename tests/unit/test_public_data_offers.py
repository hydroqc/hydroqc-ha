"""Unit tests for the Hydro-Québec peak offer catalog."""

from __future__ import annotations

import pytest

from custom_components.hydroqc.public_data.offers import (
    PEAK_OFFERS,
    RATE_CODE_MAPPING,
    fold_text,
    is_known_offer,
    normalize_offer,
    offers_for_rate,
)


class TestNormalizeOffer:
    """Offer values from the public feeds are mapped back to catalog codes."""

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("CPC-D", "CPC-D"),
            ("TPC-DPC", "TPC-DPC"),
            ("cpc-d", "CPC-D"),
            ("  TPC-DPC  ", "TPC-DPC"),
            ("Credit hivernal Residentiel (CPC-D)", "CPC-D"),
            ("Flex Residentiel (TPC-DPC)", "TPC-DPC"),
            ("Crédit hivernal résidentiel (cpc-d)", "CPC-D"),
            ("Flex résidentiel (Tpc-Dpc)", "TPC-DPC"),
            ("Rate D + Winter Credits (CPC)", "CPC-D"),
        ],
    )
    def test_known_values(self, value: str, expected: str) -> None:
        """Both feeds and their accents resolve to the catalog code."""
        assert normalize_offer(value) == expected

    @pytest.mark.parametrize("value", ["", "   ", None, 42, ["CPC-D"]])
    def test_empty_values(self, value: object) -> None:
        """Non-string and blank values normalize to an empty code."""
        assert normalize_offer(value) == ""

    def test_unknown_value_is_kept(self) -> None:
        """A new Hydro-Québec offer stays visible instead of being dropped."""
        assert normalize_offer("LAT_40H_7J") == "LAT_40H_7J"
        assert normalize_offer("Offre mystere (XYZ-1)") == "Offre mystere (XYZ-1)"

    def test_is_known_offer(self) -> None:
        """Known values, including labelled ones, are recognized."""
        assert is_known_offer("CPC-D")
        assert is_known_offer("Credit hivernal Residentiel (CPC-D)")
        assert not is_known_offer("LAT_40H_7J")


class TestOfferCatalog:
    """The catalog feeds the fetch filter and the config flow."""

    def test_offers_for_rate(self) -> None:
        """Internal rates resolve to their HQ offer codes."""
        assert offers_for_rate("DCPC") == ["CPC-D"]
        assert offers_for_rate("DPC") == ["TPC-DPC"]
        assert offers_for_rate("M-GDP") == ["GDP-Affaires"]
        assert offers_for_rate("D") == []

    def test_rate_code_mapping(self) -> None:
        """The legacy code -> internal rate view stays available."""
        assert RATE_CODE_MAPPING["CPC-D"] == "DCPC"
        assert RATE_CODE_MAPPING["TPC-DPC"] == "DPC"

    def test_fold_text(self) -> None:
        """Accents, case and spacing are folded away."""
        assert fold_text("  Résidentiel ") == "residentiel"
        assert fold_text("AFFAIRES") == "affaires"
        assert fold_text(None) == ""

    def test_catalog_labels_are_unique(self) -> None:
        """No two offers share a label, which would make normalization ambiguous."""
        labels = [offer.label for offer in PEAK_OFFERS.values()]
        assert len(labels) == len(set(labels))
