## [Non publié]

### Ajouté

### Modifié

### Corrigé

### Retiré

---

## [0.2.2-beta.1] - 2025-12-09

### Corrigé
- Mise à jour automatique de la criticité des événements calendrier de pointe existants
  - Les événements calendrier sont maintenant mis à jour en place lorsque leur criticité change (critique ↔ non-critique)
  - Évite la suppression et recréation d'événements, préservant les UIDs et l'historique
  - Mise à jour du titre et de la description pour refléter le nouveau statut de criticité
  - Améliore l'expérience utilisateur en maintenant la cohérence des événements calendrier

---

## [0.2.1] - 2025-12-07

> **⚠️ IMPORTANT - Action requise** : Si vous avez installé les blueprints de la version 0.2.0, vous **devez les réimporter** car ils contenaient une erreur qui empêchait leur bon fonctionnement.

### Corrigé
- Correction critique des blueprints calendrier (Flex-D et Crédits hivernaux)
  - **Blueprint Flex-D** : Correction du filtre de tarif (utilisait incorrectement `trigger.calendar_event.location` au lieu de `trigger.calendar_event.description`)
  - **Blueprint Crédits hivernaux** : Ajout du filtre de tarif manquant pour éviter les déclenchements croisés
  - Les blueprints filtrent maintenant correctement sur `"Tarif: DPC"` et `"Tarif: DCPC"` dans la description de l'événement
  - Prévient les déclenchements incorrects si plusieurs intégrations Hydro-Québec utilisent le même calendrier

**Comment mettre à jour vos blueprints** :
1. Allez dans **Paramètres** → **Automatisations et scènes** → **Blueprints**
2. Trouvez les blueprints Hydro-Québec (Flex-D ou Crédits hivernaux)
3. Cliquez sur **⋮** → **Réimporter le blueprint**
4. Vos automatisations existantes continueront de fonctionner avec la version corrigée

Ou réimportez directement via ces liens :
- [![Blueprint Crédits hivernaux](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fhydroqc%2Fhydroqc-ha%2Fblob%2Fmain%2Fblueprints%2Fwinter-credits-calendar.yaml)
- [![Blueprint Flex-D](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fhydroqc%2Fhydroqc-ha%2Fblob%2Fmain%2Fblueprints%2Fflex-d-calendar.yaml)

---

## [0.2.0] - 2025-12-06

**🎉 Première version officielle (v0.2.0) pour l'intégration hydroqc-ha !**

### ⭐ Fonctionnalité majeure : Intégration calendrier pour événements de pointe

Nous sommes ravis d'introduire une fonctionnalité révolutionnaire qui améliore considérablement la fiabilité de vos automatisations de périodes de pointe : **l'intégration calendrier native**.

#### Pourquoi le calendrier améliore la fiabilité

L'approche "ceinture et bretelles" offre plusieurs niveaux de protection :

1. **Persistance des événements** : Une fois créés dans le calendrier, les événements restent disponibles même si l'API d'Hydro-Québec est temporairement indisponible
2. **Déclencheurs natifs HA** : Utilise les déclencheurs de calendrier intégrés de Home Assistant, éprouvés et fiables
3. **Fallback manuel** : En cas de problème avec les API, vous pouvez créer manuellement les événements de pointe dans votre calendrier

#### Configuration du calendrier

**Étape 1 : Créer un calendrier local**

1. Dans Home Assistant, allez à **Paramètres** → **Appareils et services** → **Intégrations**
2. Cliquez sur **+ Ajouter une intégration**
3. Recherchez et installez **"Calendrier local"** (Local Calendar)
4. Créez un nouveau calendrier (ex: "Hydro-Québec Pointes")
5. Documentation complète : [Home Assistant Calendar Documentation](https://www.home-assistant.io/integrations/local_calendar/)

**Étape 2 : Activer le calendrier dans l'intégration Hydro-Québec**

1. Allez à **Paramètres** → **Appareils et services** → **Hydro-Québec**
2. Cliquez sur **Options** (⋮) → **Configurer**
3. Activez **"Synchroniser les événements de pointe vers un calendrier"**
4. Sélectionnez votre calendrier créé à l'étape 1
5. Configurez les options (pointes non-critiques pour DCPC, etc.)
6. Les événements seront créés automatiquement dans le calendrier

**Création manuelle d'événements (fallback)**

Si les API sont indisponibles ou en cas de problème, vous pouvez créer manuellement des événements :

**Exemple d'événement - Crédits hivernaux (DCPC)** :
```yaml
Titre: 🔴 Pointe critique
Date de début: 2025-12-06 16:00
Date de fin: 2025-12-06 20:00
Description:
  Tarif: DCPC
  Critique: Oui
```

**Exemple d'événement- Flex-D (DPC)** :
```yaml
Titre: 🔴 Pointe critique
Date de début: 2025-12-06 06:00
Date de fin: 2025-12-06 10:00
Description:
  Tarif: DPC
  Critique: Oui
```

L'intégration reconnaîtra ces événements et vos automatisations fonctionneront normalement.

#### Installation des blueprints recommandés

Nous avons créé deux blueprints optimisés pour utiliser le calendrier :

**Blueprint Crédits hivernaux (DCPC)** :

[![Importer le blueprint](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fhydroqc%2Fhydroqc-ha%2Fblob%2Fmain%2Fblueprints%2Fwinter-credits-calendar.yaml)

**Blueprint Flex-D (DPC)** :

[![Importer le blueprint](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fhydroqc%2Fhydroqc-ha%2Fblob%2Fmain%2Fblueprints%2Fflex-d-calendar.yaml)

> **⚠️ Utilisateurs de blueprints existants** : 
> - **Venant de hydroqc2mqtt** : Supprimez vos anciens blueprints et remplacez-les par les nouveaux blueprints calendrier (approche plus fiable)
> - **Utilisant déjà nos blueprints** : Réimportez-les pour bénéficier des dernières améliorations (notifications persistantes par défaut, meilleure gestion des erreurs)

#### Tester vos blueprints

Après configuration, **créez un événement de test** dans votre calendrier pour valider le fonctionnement :

**Exemple d'événement de test - Crédits hivernaux (DCPC)** :
```yaml
Titre: 🔴 Pointe critique TEST
Date de début: 2025-12-06 15:10
Date de fin: 2025-12-06 15:15
Description:
  Tarif: DCPC
  Critique: Oui
```

**Exemple d'événement de test - Flex-D (DPC)** :
```yaml
Titre: 🔴 Pointe critique TEST
Date de début: 2025-12-06 15:10
Date de fin: 2025-12-06 15:15
Description:
  Tarif: DPC
  Critique: Oui
```

Observez les actions de pré-chauffage (~1 min avant), début et fin de pointe.

#### Comprendre les paramètres des blueprints

**Délai avant début pointe critique (Pre-critical peak start offset)**
- Par défaut : `-00:01:00` (1 minute avant)
- Permet à vos appareils de se stabiliser avant le début officiel de la pointe
- Exemple : Si la pointe commence à 18:00, les actions se déclenchent à 17:59
- Utile pour les appareils qui prennent du temps à s'ajuster

**Actions en parallèle (Parallel action calls)**
- Les actions sont exécutées simultanément plutôt que séquentiellement
- **Avantage** : Si une action échoue, les autres continuent de s'exécuter
- **Recommandation** : Utilisez toujours `parallel:` pour regrouper vos actions
- Exemple :
  ```yaml
  - parallel:
      - action: climate.set_temperature
        target:
          entity_id: climate.chambre
        data:
          temperature: 19
      - action: switch.turn_off
        target:
          entity_id: switch.chauffe_eau
  ```

**Délai aléatoire en fin de pointe (Random delay on critical peak end)**
- Par défaut : 30 secondes à 5 minutes
- **Raison** : Évite une surcharge du réseau électrique causée par des milliers d'appareils redémarrant simultanément
- **Impact** : Aide à stabiliser le réseau électrique après une pointe
- **Recommandation** : Conservez ce délai pour être un bon citoyen du réseau

### Améliorations incluses dans cette version

#### Depuis v0.1.10-beta.2
- ✅ Restauration de l'état des capteurs binaires lors du rechargement (évite les faux déclenchements)

#### Depuis v0.1.10-beta.1
- ✅ Validation calendrier avec 10 tentatives avant désactivation (élimine les faux positifs au démarrage)
- ✅ Synchronisation immédiate du calendrier après reconfiguration (pas de redémarrage HA requis)
- ✅ Blueprints avec notifications persistantes par défaut (actions fonctionnelles dès l'installation)

#### Depuis v0.1.8-beta.1
- ✅ Intégration complète du calendrier pour événements de pointe (DPC et DCPC)
- ✅ Création automatique d'événements pour pointes critiques et régulières
- ✅ Support modes Portal et OpenData
- ✅ Gestion UID persistante avec stockage HA (prévention des doublons)
- ✅ Détection automatique des entités calendrier supprimées
- ✅ Conservation du fuseau horaire America/Toronto
- ✅ Blueprints d'automatisation optimisés
- ✅ 25 tests complets pour le gestionnaire de calendrier

### Notes de migration

**Migration depuis hydroqc2mqtt ou le Add-on**
- Les noms des capteurs sont identiques, seul le préfixe d'entité change
- Mettez à jour vos automatisations avec les nouveaux IDs d'entité
- **IMPORTANT** : Remplacez vos anciens blueprints par les nouveaux blueprints calendrier
  - Les anciens blueprints hydroqc2mqtt utilisaient uniquement les capteurs binaires
  - Les nouveaux blueprints utilisent le calendrier pour une fiabilité maximale
  - Supprimez les automatisations basées sur les anciens blueprints
  - Importez les nouveaux blueprints via les badges "My Home Assistant" (voir section Blueprints)
- Vous pouvez exécuter les deux systèmes en parallèle pour une transition en douceur

**Utilisateurs de versions beta**
- Aucune migration requise
- Si vous utilisez le calendrier, suivez les instructions de reconfiguration ci-dessus
- Réimportez les blueprints pour bénéficier des dernières améliorations

### Remerciements

Merci à tous les testeurs beta qui ont aidé à identifier et corriger les problèmes avant cette version stable !

---

## [0.1.10-beta.2] - 2025-12-06

### Corrigé
- Capteurs binaires qui basculent temporairement à 'éteint' lors du rechargement de l'intégration
  - Implémentation de RestoreEntity pour maintenir l'état des capteurs binaires pendant le rechargement
  - Les capteurs binaires conservent maintenant leur dernier état au lieu de basculer temporairement à 'off'
  - Prévient les déclenchements d'automatisations indésirables lors du rechargement
  - L'état restauré est utilisé jusqu'à ce que le coordinateur récupère de nouvelles données
  - Évite les fausses fins de pointe qui pourraient déclencher des automatisations de rétablissement

---

## [0.1.10-beta.1] - 2025-12-06

> **⚠️ IMPORTANT pour les utilisateurs existants** : Si vous utilisez la fonctionnalité calendrier :
> 1. Mettez à jour l'intégration via HACS (Home Assistant vous demandera de redémarrer)
> 2. Après le redémarrage, **reconfigurer le calendrier** (Paramètres → Appareils et services → Hydro-Québec → Options → Configurer le calendrier)
> 3. **Recharger l'intégration** (Paramètres → Appareils et services → Hydro-Québec → ⋮ → Recharger)

### Corrigé
- Faux positifs de validation du calendrier lors du démarrage (#41)
  - Logique de validation avec 10 tentatives avant désactivation permanente
  - Validation non-destructive qui vérifie l'existence sans désactiver la fonctionnalité
  - Journalisation progressive (debug → avertissement → erreur) selon le nombre de tentatives
  - Gestion gracieuse des problèmes temporaires pendant le démarrage de HA
- Synchronisation immédiate du calendrier après reconfiguration (#41)
  - Ajout d'un écouteur de mise à jour des options dans `__init__.py`
  - Réinitialisation de l'état de validation lors de la reconfiguration
  - Synchronisation immédiate sans redémarrage de Home Assistant requis
  - Amélioration de l'expérience utilisateur lors des changements de configuration

---

## [0.1.9-beta.2] - 2025-12-05

### Corrigé
- Correction de la détection du calendrier lors du démarrage de Home Assistant
  - Ajout d'une vérification pour s'assurer que le composant calendrier est chargé avant la validation
  - Évite les faux positifs "calendrier introuvable" lors du redémarrage de HA
  - Résout les notifications erronées de calendrier manquant sur chaque redémarrage

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
