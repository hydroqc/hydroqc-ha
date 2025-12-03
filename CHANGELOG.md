## [Non publié]

### Ajouté

### Modifié

### Corrigé

### Retiré

---

## [0.1.5-beta.1] - 2025-12-03

### Ajouté
- Affichage de la version actuelle de l'intégration dans les informations de l'appareil (remplace "Firmware: 1.0" par la version réelle)

### Modifié
- Mise à jour de la documentation des instructions Copilot pour refléter l'utilisation de PyPI pour Hydro-Quebec-API-Wrapper
- Ajout de note sur la protection de la branche `main` dans le processus de release
- Amélioration du formatage du fixture `mock_integration_version` dans les tests

---

## [0.1.4-beta.1] - 2025-12-03

### Corrigé
- Gestion gracieuse des valeurs `None` retournées par l'API Hydro-Québec (évite les crashs quand `montantProjetePeriode` est `None`)
- Ajout de gestion d'exceptions `TypeError` et `ValueError` dans `get_sensor_value()` du coordinateur
- Correction de l'identifiant d'étape du flux de configuration OpenData (`opendata_offer` → `opendata_rate`)
- Résolution de l'erreur `UnknownStep` lors de l'ajout d'appareils en mode OpenData

---

## [0.1.3-beta.1] - 2025-12-02

### Corrigé
- Résolution de l'ensemble des 65 erreurs de typage mypy strict améliorant la qualité et la sûreté du code (#11)
- Correction des retours de propriétés booléennes du coordinateur avec appels `bool()` explicites
- Ajout de vérifications `None` appropriées pour l'accès aux attributs `statistics_manager` et `history_importer`
- Correction du placement des annotations `type: ignore` pour compatibilité avec les types de la librairie hydroqc
- Correction du casting des types d'options `SelectSelectorConfig` dans le flux de configuration
- Correction du nom de méthode `async_step_opendata_offer` (renommée en `async_step_opendata_rate`)
- Correction de l'annotation de type pour l'import `DeviceInfo`

### Modifié
- Mise à jour de tous les types de retour du flux de configuration de `FlowResult` vers `ConfigFlowResult`
- Amélioration des annotations de type dans les modules coordinateur, gestionnaire de statistiques et historique de consommation
- Renforcement de la sûreté des types avec annotations `Callable` appropriées et gardes `None`

### Retiré
- Retrait de 10 tests d'intégration ignorés qui n'étaient pas prévus pour implémentation
  - Tests config_flow.py (5 tests nécessitant le chargeur HA complet)
  - Tests services.py (2 tests nécessitant le chargeur HA complet)
  - Tests de méthodes privées consumption_history.py (3 tests)

---

## [0.1.3] - 2025-12-01

### Fixed
- KeyError: 'hrsCritiquesAppelees' in DPC contracts during winter season (#9)
- Updated Hydro-Quebec-API-Wrapper to 4.2.4 to fix upstream library issue

### Added
- Version logging on coordinator initialization to verify library version at runtime
- GitHub issue management guidelines in copilot-instructions.md

---

## [0.1.2] - 2024-12-01

### Added
- Initial release
- Config flow with authenticated and peak-only modes
- Support for rates: D, DT, DPC, M, M-GDP
- 50+ sensors for consumption, billing, and account data
- 16 binary sensors for peak events and service status
- Winter credit tracking (Rate D with CPC option)
- Flex-D dynamic pricing support (Rate DPC)
- Options flow for configurable update interval and pre-heat duration
- Service calls: `refresh_data` and `fetch_hourly_consumption`
- Bilingual support (English/French)
- HACS compatible

---

## Release Format

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

### Types of changes
- **Added** for new features
- **Changed** for changes in existing functionality
- **Deprecated** for soon-to-be removed features
- **Removed** for now removed features
- **Fixed** for any bug fixes
- **Security** in case of vulnerabilities
