## [Non publié]

### Ajouté

### Modifié

### Corrigé

### Retiré

---

## [0.1.9-beta.1] - 2025-12-05

### Ajouté
- Flux de récupération des pics critiques 7 jours à l'avance avec filtrage par date
  - Requête API avec clause `where=datedebut>='YYYY-MM-DD'` pour limiter aux événements futurs
  - Logs de débogage affichant la plage de dates des pics critiques récupérés
- Documentation complète des blueprints avec exemples et recommandations
  - Instructions pour workflows complexes et automatisations séparées
  - Exemples de titres d'événements (🔴 Pointe critique / ⚪ Pointe régulière)
  - Instructions de création manuelle d'événements avec exemples de code
  - Explication des délais aléatoires et actions parallèles
- Validation des blueprints avec workflow CI dédié
  - Script Python utilisant les tags Home Assistant pour validation
  - Workflow GitHub Actions séparé pour validation des blueprints
- Boutons d'importation My Home Assistant dans le README
  - Import direct des blueprints depuis l'interface HA

### Modifié
- Génération du planning DCPC limitée à 2 jours (aujourd'hui/demain) pour les pics non-critiques
  - Les pics critiques au-delà de demain proviennent des annonces API (fenêtre 7 jours)
  - Améliore la séparation entre pics réguliers et critiques
- Décalage de pics critiques configurable (1 minute avant le début)
  - Permet des actions de préparation de dernière minute
- Délai aléatoire à la fin des pics (30 sec - 5 min par défaut)
  - Évite la surcharge réseau avec multiples automatisations simultanées
- Améliorations des blueprints
  - Actions parallèles par défaut pour fiabilité accrue
  - Descriptions plus lisibles dans l'interface HA

### Corrigé
- Format des descriptions de blueprints pour meilleur rendu dans l'interface HA
  - Suppression des retours à la ligne forcés en milieu de paragraphes
  - Flux de texte naturel pour affichage fluide
  - Espacement de sections avec lignes vides entre en-têtes et contenu
- Erreurs de parsing YAML dans les blueprints
  - Format de description corrigé
  - Définition d'entrée manquante pour critical_peak_offset
  - Sélecteur de texte pour les valeurs de décalage négatives
- Nettoyage du justfile (suppression des commandes dupliquées)

---

## [0.1.8-beta.1] - 2025-12-05

### Ajouté
- Intégration complète du calendrier pour les événements de pointe (DPC et DCPC) (#7)
  - Création automatique d'événements de calendrier pour les pointes critiques et régulières
  - Support pour les modes Portal et OpenData
  - Gestion UID d'événements persistante avec stockage HA pour prévenir les doublons
  - Détection automatique des entités calendrier supprimées (désactivation automatique)
  - Événements en français uniquement avec métadonnées détaillées
  - Conservation du fuseau horaire des événements (America/Toronto)
- Deux blueprints d'automatisation pour les événements de calendrier
  - `winter-credits-calendar.yaml` : Automatisation complète DCPC avec différenciation critique/régulière
  - `flex-d-calendar.yaml` : Automatisation DPC pour les pointes critiques
  - Actions essentielles (pré-chauffage, début/fin pointe) en premier
  - Actions optionnelles (ancrages, pointes régulières) regroupées et repliables
  - Exécution parallèle par défaut pour fiabilité
  - Filtres de tarif et de criticité intégrés
- Configuration flexible du calendrier dans les options
  - Activation/désactivation du calendrier
  - Sélection d'une entité calendrier existante (optionnel)
  - Configuration des pointes non-critiques (DCPC uniquement)
- 25 tests complets pour le gestionnaire de calendrier
  - Tests de création d'événements (DPC/DCPC, critique/régulier)
  - Tests de gestion UID et prévention de doublons
  - Tests de transitions DST et fuseaux horaires
  - Tests de désactivation automatique
  - Tous les scénarios edge cases couverts

### Modifié
- Ajout de `calendar` dans `after_dependencies` du manifest
- Blueprints : Séparation des fins d'ancrage matin/soir pour plus de flexibilité

### Corrigé
- Correction du format de délai de pré-chauffage dans les blueprints
  - Changement de sélecteur numérique (minutes) vers sélecteur de durée (HH:MM:SS)
  - Défaut : `-02:00:00` au lieu de `-120` (correctement interprété comme 2 heures)
  - Corrige le bug où `-120` était interprété comme 120 secondes au lieu de 120 minutes
- Correction de la synchronisation calendrier en mode OpenData
  - Déplacement de la synchronisation avant le retour anticipé OpenData
  - Les événements de calendrier sont maintenant créés correctement en mode OpenData
- Correction du timing de dépendance calendrier
  - Ajout de `calendar` dans `after_dependencies` pour initialisation correcte
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
