## [Non publié]

### Ajouté

### Modifié

### Corrigé

### Retiré

---

## [0.1.7-beta.1] - 2025-12-05

### Modifié
- Mise à jour de Hydro-Quebec-API-Wrapper à 4.2.5 avec dépendances assouplies pour compatibilité Home Assistant

---

## [0.1.6-beta.1] - 2025-12-03

### Corrigé
- Correction des capteurs de préchauffage DCPC (Crédits hivernaux) qui se déclenchaient pour les pics non-critiques (#18, #20)
  - Le capteur binaire `wc_pre_heat` ne retourne maintenant `True` que si le préchauffage est actif ET le prochain pic est critique
  - Le capteur timestamp `wc_next_pre_heat_start` ne retourne maintenant l'horodatage que si le prochain pic est critique
  - Les pics non-critiques (pics réguliers programmés) ne déclenchent plus d'alertes de préchauffage
- Correction du mode OpenData qui retournait toujours des capteurs non disponibles
  - Le coordinateur retourne maintenant correctement les données du `public_client` au lieu d'un dictionnaire vide
  - Tous les capteurs du mode OpenData s'affichent maintenant correctement
- Correction des capteurs et capteurs binaires pour supporter le mode OpenData
  - Les champs `contract_name` et `contract_id` sont maintenant optionnels (mode OpenData utilise l'ID d'entrée de configuration)
- Correction du fichier `services.yaml` pour utiliser le ciblage d'entité au lieu du ciblage d'appareil (non supporté)
- Correction de la validation hassfest du manifest
  - Ajout du champ requis `integration_type` (défini à `service`)
  - Changement de `dependencies` à `after_dependencies` pour `recorder` (patron correct pour dépendance optionnelle)
  - Tri alphabétique des clés du manifest (domaine, nom, puis alphabétique)
- Correction de la validation HACS en ajoutant `ignore: brands` au workflow CI

### Modifié
- Mise à jour de Hydro-Quebec-API-Wrapper de 4.2.4 à 4.2.5
- Changement de `integration_type` de `hub` à `service` (classification plus appropriée)

### Ajouté
- Ajout de tests complets pour le mode OpenData (14 nouveaux tests, total de 83 tests)
  - Tests du coordinateur OpenData (8 tests): initialisation, récupération de données, gestion des erreurs
  - Tests des capteurs OpenData (6 tests): création, valeurs d'état, attributs, disponibilité
  - Fixtures pour tester les modes DPC et DCPC en OpenData
  - Couverture de test pour le bug de retour de dictionnaire vide
- Ajout de tests complets pour le filtrage du préchauffage par criticité (5 scénarios couverts)

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
