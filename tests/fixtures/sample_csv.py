"""Sample CSV consumption data for testing."""

SAMPLE_CSV_BASIC = """Date,Heure début,Heure fin,Consommation (kWh)
2024-11-26,00:00,01:00,1.234
2024-11-26,01:00,02:00,1.567
2024-11-26,02:00,03:00,1.890
2024-11-26,03:00,04:00,1.456
2024-11-26,04:00,05:00,1.123
"""

SAMPLE_CSV_FRENCH_DECIMALS = """Date,Heure début,Heure fin,Consommation (kWh)
2024-11-26,00:00,01:00,"1,234"
2024-11-26,01:00,02:00,"1,567"
2024-11-26,02:00,03:00,"1,890"
"""

SAMPLE_CSV_DST_SPRING = """Date,Heure début,Heure fin,Consommation (kWh)
2024-03-10,00:00,01:00,1.234
2024-03-10,01:00,03:00,1.567
2024-03-10,03:00,04:00,1.890
"""

SAMPLE_CSV_DST_FALL = """Date,Heure début,Heure fin,Consommation (kWh)
2024-11-03,00:00,01:00,1.234
2024-11-03,01:00,02:00,1.567
2024-11-03,02:00,03:00,1.890
"""

SAMPLE_CSV_MISSING_DATA = """Date,Heure début,Heure fin,Consommation (kWh)
2024-11-26,00:00,01:00,1.234
2024-11-26,01:00,02:00,
2024-11-26,02:00,03:00,1.890
"""
