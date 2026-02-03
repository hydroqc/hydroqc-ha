## [Non publié]

### Ajouté

### Modifié

### Corrigé

### Retiré

---

## [0.7.0-beta.3] - 2026-02-03

### ⚠️ CHANGEMENT MAJEUR

**Le calendrier est maintenant obligatoire pour les tarifs DPC/DCPC.**

Les utilisateurs avec un tarif DPC ou DCPC qui n'avaient pas configuré de calendrier devront en configurer un. Les capteurs de pointe ne seront pas créés sans calendrier.

Pour migrer :
1. Créez une intégration Calendrier Local si vous n'en avez pas
2. Reconfigurez HydroQc pour sélectionner l'entité calendrier

### Ajouté

- **Service `hydroqc.create_peak_event`** : Création manuelle d'événements de pointe critique (#108)
  - Paramètre `date` : Date de l'événement (sélecteur de date)
  - Paramètre `time_slot` : Matin (AM: 6h-10h) ou Soir (PM: 16h-20h)
  - Utilise le même format d'UID que les événements OpenData
  - Rafraîchit immédiatement les capteurs après création
  - Vérifie les doublons avant création
- Validation du calendrier dans le flux de configuration
- Lien pour créer un Calendrier Local directement depuis le flux de configuration

### Modifié

- Le calendrier est maintenant **obligatoire** (non optionnel) pour les tarifs DPC/DCPC
- Les capteurs de pointe sont ignorés si aucun calendrier n'est configuré
- Mises à jour des traductions EN/FR/ES avec les nouvelles instructions

### Corrigé

- Correction des références `datetime.datetime.now()` dans `calendar_manager.py`

---

## [0.7.0-beta.2] - 2026-01-29

### Ajouté

- `utils.py` : Nouveau module utilitaire avec fonctions de saison d'hiver (#102)
  - `is_winter_season(dt)` : Vérifie si une date est en saison hivernale (1er déc - 31 mars)
  - `get_winter_season_bounds(date)` : Retourne les bornes de la saison d'hiver

### Modifié

- Refactorisation : Extraction de `is_winter_season` vers `utils.py` (suggestion de revue @lit-af)
- Refactorisation : Utilisation de `is_winter_season()` dans `calendar_sync.py` et `public_data/peak_handler.py`
- Renommage du capteur "Économie vs Tarif D" → "Différence Flex D vs Tarif D" (#88)
  - Clarifie que les valeurs négatives = économies (coût Flex D - coût Tarif D)
  - Mis à jour dans les trois langues (EN/FR/ES)

### Corrigé

- Correction du formatage dans `button.py` et `sensor.py`

---

## [0.7.0-beta.1] - 2026-01-29

### 🎯 Points saillants de cette version

Cette version introduit une architecture où le calendrier devient la source de vérité pour les capteurs de pointe, avec trois ordonnanceurs indépendants et une protection anti-thundering herd.

#### 📅 Calendrier comme source de vérité
- **Données persistantes** : Les événements de pointe survivent aux redémarrages de Home Assistant
- **CalendarPeakHandler** : Nouveau gestionnaire qui lit les événements depuis le calendrier HA
- **Synchronisation bidirectionnelle** : OpenData → Calendrier → Capteurs
- **Détection par signature** : Détecte les ajouts, suppressions et modifications d'événements

#### ⏰ Trois ordonnanceurs indépendants
- **OpenData** : Toutes les 15 minutes avec décalage aléatoire (10h30-15h00 fenêtre active)
- **Portail** : Aux heures avec décalage aléatoire
- **Calendrier** : Toutes les 15 minutes pour capter les modifications manuelles

#### 🔄 Anti-thundering herd
- **Décalage aléatoire** : Minutes (0-14) et secondes (0-59) calculés au démarrage
- **Distribution des appels** : Évite que tous les utilisateurs appellent l'API en même temps
- **Appliqué à OpenData ET Portail** : Les deux ordonnanceurs utilisent le même décalage

#### 🔘 Bouton de rafraîchissement manuel
- **Nouveau bouton** : Permet de forcer un rafraîchissement des données de pointe
- **Portée limitée** : Rafraîchit uniquement OpenData et calendrier (pas le portail)

### Ajouté

- `CalendarPeakHandler` : Gestionnaire de pointe basé sur le calendrier HA (#102)
- `CalendarPeakEvent` : Modèle d'événement simplifié parsé depuis le calendrier
- Bouton de rafraîchissement manuel pour les tarifs DPC/DCPC (#104)
- Détection par signature pour la synchronisation du calendrier
- Décalage aléatoire minute/seconde pour l'ordonnanceur OpenData
- Documentation mise à jour dans `copilot-instructions.md`

### Modifié

- Fenêtre active OpenData changée de 11h00-18h00 à 10h30-15h00 EST
- Intervalle OpenData changé de 5 minutes à 15 minutes
- Ordonnanceur Portail avec décalage aléatoire (plus au top de l'heure)
- Les capteurs de pointe lisent maintenant depuis `CalendarPeakHandler` au lieu de l'API directement
- Trois ordonnanceurs indépendants au lieu d'un seul

### Corrigé

- Correction du nom de méthode du bouton (`async_fetch_peaks()` → `fetch_peak_data()`)
- Correction de la restauration des capteurs timestamp (parsing des chaînes ISO)
- Corrections de linting et erreurs de typage

---

## [0.6.0] - 2025-01-04

**Rafraichissez vos Blueprint**

### 🎯 Points saillants de cette version

Cette version majeure améliore considérablement la performance et la fiabilité de l'intégration avec trois fonctionnalités clés :

#### 📊 Importation optimisée de l'historique de consommation
- **Traitement par lots** : Importation par blocs de 7 jours avec pauses entre chaque lot
- **Vérification d'intégrité** : Détection automatique des données corrompues avec tentatives de récupération
- **Support DST** : Gestion intelligente des transitions heure d'été/hiver
- **Fiabilité** : Import en arrière-plan sans bloquer Home Assistant

#### ⏰ Ordonnancement intelligent des mises à jour
- **Fenêtres temporelles adaptées** aux heures réelles de mise à jour d'Hydro-Québec
- **Réduction drastique** des appels API inutiles (90% de réduction)
- **Les capteurs se mettent à jour uniquement** lorsque de nouvelles données sont disponibles
- **Préservation de l'état** : plus de valeurs "Inconnu" entre les mises à jour

#### 🏷️ Organisation améliorée des capteurs
- **36 capteurs diagnostiques** : désencombre la liste principale des entités
- **14 capteurs désactivés par défaut** : activation manuelle selon vos besoins
- **Attribution des sources** : indication claire de la provenance des données (Portail vs OpenData)
- **Interface épurée** : focus sur les capteurs les plus importants

#### 🔧 Améliorations de l'expérience utilisateur
- **Détection du portail hors-ligne** : évite les erreurs pendant les maintenances HQ
- **Détection des changements de période de facturation** : messages contextuels lors des transitions
- **Messages contextuels** : explications claires lors d'échecs temporaires de synchronisation de conso

### ⚠️ Changements importants

**Suppression de l'option d'intervalle de mise à jour configurable**

L'option "Intervalle de mise à jour" a été retirée de la configuration. Le système utilise maintenant un ordonnancement intelligent basé sur les heures de mise à jour réelles des données Hydro-Québec.

**Migration automatique** : L'intégration supprimera automatiquement l'ancienne configuration lors de la mise à jour. Aucune action requise de votre part.

### Ajouté

- **Importation CSV par lots avec vérification d'intégrité** (#30)
  - Traitement par lots de 168 heures (7 jours) pour éviter de surcharger les systèmes lents
  - Délai de 0.5s entre les lots et 1s entre les types de consommation
  - Vérification automatique de l'intégrité après chaque lot (3 tentatives avec délai)
  - Détection des journées de transition DST pour éviter les fausses alertes
  - Vérification des sommes cumulatives non-décroissantes

- **Ordonnancement intelligent des mises à jour** (#35)
  - Fenêtres temporelles adaptées aux heures de mise à jour HQ
  - OpenData : 11h-18h EST (5 min actif / 60 min inactif)
  - Portail : 0h-8h EST (60 min actif / 180 min inactif)
  - Pointes : toutes les heures à XX:00:00 (saison hivernale uniquement)
  - Synchronisation consommation : toutes les heures (60+ minutes)
  - Détection automatique hors-saison (OpenData désactivé hors déc-mars)
  
- **Détection du portail hors-ligne**
  - Vérifie le statut du portail avant toute opération
  - Évite les erreurs inutiles pendant les maintenances
  - Journalisation limitée (1x par heure maximum)
  - Nouveau capteur binaire diagnostique montrant la disponibilité du portail (#23)
  
- **Détection des changements de période de facturation**
  - Identifie automatiquement les périodes à risque (±3 jours autour de la fin de période)
  - **Problème connu** : Le portail Hydro-Québec peut être indisponible pendant les transitions de période
  - **Messages explicites** : Au lieu d'afficher une erreur générique, l'intégration explique maintenant que les données peuvent être temporairement indisponibles pendant les transitions de période
  - **Exemple de message** : "[Portal] Error during consumption sync (near billing period boundary, consumption data may be temporarily unavailable)"
  - Réduit la confusion des utilisateurs en expliquant que c'est un problème temporaire du portail HQ

- **Attribution des sources de données**
  - Capteurs du portail : "Espace Client Hydro-Québec"
  - Capteurs OpenData : "Données ouvertes Hydro-Québec"
  - Affichage de l'attribution dans les détails des entités

- **Organisation des capteurs**
  - **36 capteurs diagnostiques** pour désencombrer la liste principale :
    - 1 capteur de statut du portail
    - 4 capteurs de période de facturation (durée, jour actuel, moyenne, tarif)
    - 3 capteurs d'informations techniques
    - 2 capteurs de début pré-chauffage (WC et DPC)
    - 15 capteurs binaires de pointes (WC et DPC)
    - 6 capteurs timestamp (ancrages et pointes régulières DCPC, panne)
    - 5 autres capteurs techniques (état WC, heures critiques DPC, etc.)
  - **14 capteurs désactivés par défaut** (peuvent être activés manuellement) :
    - Tarif et option de tarif
    - Statut du portail
    - EPP activé
    - Jours d'hiver (DPC)
    - Heures de début pré-chauffage (WC et DPC)
    - Pré-chauffage en cours (WC et DPC)
    - Pointes aujourd'hui/demain matin/soir (WC et DPC)

### Modifié

- **Ordonnancement manuel uniquement** : l'intervalle automatique du coordinateur est désactivé
- **Les capteurs ne se mettent à jour que lors de la récupération réelle de données**
- **Préservation de l'état des capteurs** :
  - Données du portail préservées lors des actualisations ignorées
  - État précédent restauré après redémarrage de Home Assistant
  - Plus de valeurs "Inconnu" entre les actualisations
- **Optimisation de la synchronisation calendrier** : mise à jour uniquement si nouveaux événements
- Synchronisation consommation : toutes les heures (au lieu de 15 min)
- Réduction significative de la charge système et des mises à jour inutiles

### Corrigé

- **Synchronisation du calendrier pour les pointes critiques annoncées**
  - Le suivi compte maintenant uniquement les pointes critiques (pas le total)
  - Les annonces de pointes critiques pour des plages déjà planifiées (DCPC) déclenchent maintenant la synchronisation du calendrier
  - Corrige le problème où les événements critiques n'apparaissaient pas dans le calendrier jusqu'au redémarrage

- **Configuration du calendrier optionnel** (#80)
  - Le champ calendrier peut maintenant être vidé dans les options sans erreur de validation
  - Les utilisateurs peuvent désactiver complètement la fonctionnalité calendrier
  - Les événements existants restent dans le calendrier (gestion manuelle possible)

- **Détection améliorée des transitions DST lors de l'importation CSV**
  - Vérification basée sur la date spécifique au lieu de la différence de comptage
  - Utilise les capacités de fuseau horaire de Python pour identifier les vraies journées de transition DST
  - Évite les faux positifs tout en capturant les vrais problèmes d'intégrité des données

- Gestion des erreurs "No data available" lors de la synchronisation de consommation (données du jour actuel pas encore disponibles)
- Suppression du délai de démarrage bloquant (améliore le temps de démarrage de HA)
- Correction de l'accès à l'attribut `_events` dans PeakHandler

### Retiré

- Option de configuration "Intervalle de mise à jour" (BREAKING CHANGE)
  - Migration automatique incluse
  - L'ordonnancement intelligent remplace ce réglage

---

## [0.5.0] - 2025-12-22


### Note de mise à jour importante

**⚠️ Actions requises lors de la mise à jour** :

1. **Blueprint Crédits Hivernaux** : Le blueprint a été complètement refondu pour prendre en charge les ancrage et les pointes non-critiques. Seulenent les pointes critiques sont géré via le calendrier désormais.
   - **Action requise** : Réimportez le blueprint depuis HACS ou GitHub

2. **Nettoyage du calendrier DCPC** : Les événements non-critiques ne sont plus créés
   - **Recommandation** : Supprimez manuellement les futures événements non-critiques de votre calendrier
   - Les événements non-critiques ont le titre "Pointe régulière" (avant cette version)
   - Seules les pointes critiques annoncées par Hydro-Québec apparaissent maintenant (titre: "Pointe")

3. **Système de traduction** : Les noms d'entités suivent maintenant la langue du système Home Assistant
   - Vérifiez **Paramètres → Système → Général → Langue** pour votre langue d'affichage
   - Support complet : Français, Anglais, Espagnol

### Ajouté

- **Système de traduction multilingue** (PR #75, #78, merci @jf-navica)
  - Migration complète vers le système `translation_key` de Home Assistant
  - **Nouveau** : Support complet de l'espagnol (`es.json`) - 319 lignes de traductions
  - Noms de capteurs plus courts et concis pour améliorer l'affichage mobile
  - Exemples : "Billing Period Day" au lieu de "Current Billing Period Current Day"
  - Les entités affichent automatiquement les noms dans la langue du système Home Assistant
  - Langues supportées : Français, Anglais, Espagnol (couverture complète des 58 capteurs et 16 capteurs binaires)

- **Option de désactivation de la synchronisation de consommation** (PR #74, #78)
  - Nouvelle option dans le flux de configuration Portal mode : "Activer la synchronisation de l'historique de consommation"
  - Activée par défaut pour compatibilité ascendante
  - Permet de désactiver le suivi de consommation pour réduire les appels API
  - Utile pour les utilisateurs qui n'utilisent pas le tableau de bord Énergie
  - Configurable après l'installation via Options

### Modifié

- **Simplification du flux de configuration initial** (PR #78)
  - Retrait de la configuration du pré-chauffage du flux de configuration initial.
  - Durée de pré-chauffage utilise la valeur par défaut (120 minutes) lors de la configuration
  - Configuration du pré-chauffage reste disponible dans les Options après l'installation
  - Réduit le nombre d'étapes de configuration pour simplifier l'expérience initiale

- **Refonte complète du blueprint Crédits Hivernaux** (`winter-credits-calendar.yaml`, PR #72, #73)
  - Déclencheurs à heures fixes (01h, 04h, 06h, 10h, 12h, 14h, 16h, 20h) pour l'horaire quotidien
  - Déclencheurs calendrier avec offset uniquement pour le pré-chauffage des pointes critiques
  - Variable `next_peak_critical` pour déterminer si la prochaine pointe est critique
  - Validation du tarif DCPC pour éviter les conflits avec calendriers multi-tarifs
  - Mode `single` avec `max_exceeded: silent` pour éviter les exécutions multiples
  - Utilisation de `calendar.get_events` pour obtenir les événements du jour à l'exécution
  - Patron de templating inspiré du blueprint Flex-D pour une meilleure cohérence

- **Amélioration des noms de capteurs** (PR #75, merci @jf-navica)
  - 58 noms de capteurs raccourcis pour meilleure lisibilité
  - Exemples français : "Conso. totale" au lieu de "Consommation totale horaire"
  - Améliore l'affichage sur mobile et dans les tableaux de bord

- **Simplification du calendrier DCPC** (PR #72)
  - Le calendrier ne crée plus d'événements pour les pointes non-critiques
  - Seules les pointes critiques annoncées par Hydro-Québec apparaissent dans le calendrier

### Corrigé

- **Bug critique du blueprint winter-credits-calendar** (PR #73)
  - `state_attr(calendar_entity, 'events')` retournait vide, empêchant la distinction entre pointes critiques et régulières
  - Solution : Utilisation de `calendar.get_events` pour obtenir les événements réels à l'exécution
  - Les déclencheurs à heures fixes fonctionnent maintenant correctement
  - La variable `next_peak_critical` reflète maintenant l'état réel du calendrier

- **Erreur de sélection du calendrier dans le flux de configuration** (PR #75, merci @jf-navica)
  - Simplification du schéma de configuration en utilisant le type natif `bool` au lieu de `BooleanSelector()`
  - Correction des erreurs de sérialisation du schéma Home Assistant
  - Configuration plus fiable et maintenable

- **Corrections de sérialisation du schéma de configuration** (PR #78)
  - Changement de `str` vers `TextSelector()` pour le champ `contract_name`
  - Changement de `vol.Boolean()` vers `bool` pour le champ `enable_consumption_sync`
  - Imports corrects des sélecteurs Home Assistant

- **État `current_state` pour DPC** (PR #70, merci @lit-af)
  - Retourne maintenant "normal" au lieu de "off_season" lorsqu'il n'y a pas d'événements pendant la saison hivernale
  - Améliore la clarté de l'état des capteurs DPC

- **Gestion des fuseaux horaires** (PR #66, merci @jf-navica)
  - Migration de `pytz` vers `zoneinfo` (bibliothèque standard Python)
  - Meilleure compatibilité et performances

- **Calcul de la somme cumulative de consommation** (PR #66, merci @jf-navica)
  - Correction pour éviter les réinitialisations lors de lacunes dans les données
  - `get_base_sum()` regarde maintenant jusqu'à 30 jours en arrière pour trouver la dernière somme connue
  - Base la continuité sur le premier point de données réel au lieu de la date de début demandée
  - Blocage des valeurs de consommation négatives lors de l'importation CSV

### Retiré

- **Option "Inclure les pointes non-critiques"** pour DCPC (PR #72)
  - Suppression de `CONF_INCLUDE_NON_CRITICAL_PEAKS` de la configuration
  - Retiré du flux de configuration et des options
  - Simplification de la gestion des événements calendrier

- **Logique de gestion des événements non-critiques** dans `calendar_manager.py` (PR #72)
  - Fonction `async_update_peak_event()` supprimée
  - Constante `TITLE_REGULAR` supprimée
  - Paramètre `include_non_critical` retiré de `_create_or_update_peak_events()`

- **Champs `name` codés en dur** dans `const.py` (PR #75, merci @jf-navica)
  - 58 suppressions de champs "name" dans les dictionnaires SENSORS et BINARY_SENSORS
  - Remplacés par le système translation_key pour une meilleure maintenabilité

### Guide de mise à jour depuis 0.3.1 ou version antérieure

#### 1. Mise à jour de l'intégration

**Via HACS (recommandé)** :
1. Ouvrez HACS → Intégrations
2. Trouvez "Hydro-Québec"
3. Cliquez sur "Mettre à jour"
4. Redémarrez Home Assistant

**Manuellement** :
1. Téléchargez `hydroqc.zip` depuis la [page des releases](https://github.com/hydroqc/hydroqc-ha/releases/tag/v0.5.0)
2. Extrayez dans `custom_components/hydroqc/`
3. Redémarrez Home Assistant

#### 2. Mise à jour du blueprint Crédits Hivernaux (OBLIGATOIRE si vous l'utilisez)

Le blueprint a été complètement refondu pour corriger un bug critique. **Vous devez le réimporter.**

**Via HACS** :
1. Allez dans **Paramètres → Automatisations & Scènes → Blueprints**
2. Cliquez sur **⋮** à côté de "HydroQC - Crédits Hivernaux"
3. Sélectionnez **Réimporter le blueprint**

**Manuellement** :
1. Téléchargez [`winter-credits-calendar.yaml`](https://github.com/hydroqc/hydroqc-ha/blob/main/blueprints/winter-credits-calendar.yaml)
2. Copiez le fichier dans `config/blueprints/automation/hydroqc/`
3. Rechargez les blueprints : **Paramètres → Automatisations & Scènes → Blueprints → ⋮ → Recharger les blueprints**

**Vérification** :
- Vos automatisations existantes continueront de fonctionner automatiquement
- Le blueprint détectera maintenant correctement les pointes critiques vs régulières
- Testez votre automatisation avant la prochaine pointe critique

#### 3. Nettoyage du calendrier DCPC (recommandé)

Les versions précédentes créaient des événements "Pointe régulière" dans le calendrier. Ces événements ne sont plus créés dans cette version.

**Pour supprimer les futures événements non-critiques** :

1. Ouvrez l'entité calendrier HydroQC dans Home Assistant
2. Trouvez les événements avec le titre **"Pointe régulière"**
3. Supprimez-les manuellement un par un (ils apparaissent quotidiennement à 6h-10h et 16h-20h)

#### 4. Vérification de la langue d'affichage

Les noms d'entités suivent maintenant la **langue du système** Home Assistant, pas la langue du profil utilisateur.

**Pour vérifier ou changer la langue** :
1. Allez dans **Paramètres → Système → Général**
2. Vérifiez le champ **Langue** sous "Langue & Région"
3. Sélectionnez votre langue préférée (Français, English, Español)
4. Cliquez sur **Enregistrer** et rafraîchissez votre navigateur

**Langues supportées** :
- 🇫🇷 Français : Noms complets et concis (ex: "Solde", "Conso. totale")
- 🇬🇧 English : Clean names (e.g., "Balance", "Billing Period Day")
- 🇪🇸 Español : Traducciones completas (ej: "Saldo", "Día período facturación")

#### 5. Option de synchronisation de consommation (nouvelle fonctionnalité)

Si vous ne souhaitez pas synchroniser l'historique de consommation (par exemple, si vous n'utilisez pas le tableau de bord Énergie) :

1. Allez dans **Paramètres → Appareils & Services → Hydro-Québec**
2. Cliquez sur **Configurer** (icône engrenage) sur votre intégration
3. Décochez **"Activer la synchronisation de l'historique de consommation"**
4. Cliquez sur **Soumettre**

**Effet** :
- ✅ Réduit les appels API vers Hydro-Québec
- ✅ Améliore les performances si vous n'avez pas besoin des données de consommation
- ✅ Les autres capteurs (balance, facture, pointes) continuent de fonctionner normalement
- ⚠️ Les statistiques de consommation horaire ne seront plus mises à jour

### Remerciements

Un grand merci à tous les contributeurs de cette version :

- **@jf-navica** : Système de traduction complet, support espagnol, corrections de bugs (PR #75, #66)
- **@lit-af** : Correction de l'état DPC `current_state` (PR #70)
- Et tous les utilisateurs qui ont testé les versions beta et fourni des retours précieux !

**Merci de signaler tout problème via les [issues GitHub](https://github.com/hydroqc/hydroqc-ha/issues).**

---

## [0.4.0-beta.1] - 2025-12-18

### Note

**⚠️ Changement important** : Les événements de pointe non-critiques ne sont plus créés dans le calendrier pour les tarifs DCPC (Crédits Hivernaux). Seules les pointes critiques annoncées par Hydro-Québec apparaissent maintenant dans le calendrier.

**Migration requise** : Si vous utilisez le blueprint Crédits Hivernaux :
1. Réimportez le nouveau blueprint depuis HACS ou GitHub
2. Le blueprint utilise maintenant des déclencheurs à heures fixes combinés avec des vérifications du calendrier
3. Les anciennes automatisations continueront de fonctionner mais ne recevront plus d'événements non-critiques

### Modifié
- **Architecture des blueprints** : Refonte complète du blueprint Crédits Hivernaux (winter-credits-calendar.yaml)
  - Déclencheurs à heures fixes (01h, 04h, 06h, 10h, 12h, 14h, 16h, 20h) pour l'horaire quotidien
  - Déclencheurs calendrier avec offset pour le pré-chauffage des pointes critiques uniquement
  - Variable `next_peak_critical` pour déterminer si la prochaine pointe est critique
  - Validation du tarif DCPC pour éviter les conflits avec calendriers multi-tarifs
  - Mode `single` avec `max_exceeded: silent` pour éviter les exécutions multiples
  - Inspiration du patron de templating du blueprint Flex-D pour une meilleure cohérence
- **Simplification du calendrier DCPC** : Le calendrier ne crée plus d'événements pour les pointes non-critiques
  - Réduit la charge sur le calendrier Home Assistant
  - Élimine la mise à jour quotidienne des événements non-critiques
  - Améliore les performances et la fiabilité
- Mise à jour de la documentation des blueprints pour refléter les nouveaux comportements

### Retiré
- **Option de configuration** : Retrait de l'option "Inclure les pointes non-critiques" pour DCPC
  - Supprimé de `CONF_INCLUDE_NON_CRITICAL_PEAKS` de la configuration
  - Retiré du flux de configuration et des options
- **Gestion des événements non-critiques** : Retrait de la logique de création/mise à jour des événements non-critiques dans `calendar_manager.py`
  - Fonction `async_update_peak_event()` supprimée
  - Constante `TITLE_REGULAR` supprimée
  - Paramètre `include_non_critical` retiré de `_create_or_update_peak_events()`

---

## [0.3.1] - 2025-12-11

### Modifié
- Ajout du champ `country` à la configuration HACS pour indiquer que l'intégration est spécifique au Canada

---

## [0.3.0] - 2025-12-10

### Note

Ce projet est toujours en phase de développement initial et en constante évolution. Assurez-vous de vérifier les mises à jour fréquemment afin d'obtenir les dernières fonctionnalités et corrections.

- Cette version contient un fix important pour les mise à jour de pointes non-critiques vers critiques dans le calendrier. **⚠️Lors de la prochaine pointe critique, assurez-vous que l'événement calendrier est mis à jour correctement.⚠️**
- Assurez-vous de réimporter vos blueprints

**Merci de signaler tout problème via les issues GitHub.**

### Modifié
- Refactorisation complète du code en structure modulaire pour améliorer la maintenabilité
  - **coordinator/** : Division en modules (base, calendar_sync, consumption_sync, sensor_data)
  - **config_flow/** : Séparation en modules (base, options, helpers)
  - **public_data/** : Organisation en couches (models, peak_handler, client)
  - Principe de responsabilité unique appliqué à tous les modules
  - Compatibilité ascendante maintenue via ré-exportations
  - Aucun changement fonctionnel - refactorisation pure du code
- Mise à jour de la version minimale de Home Assistant à 2025.9.0
- Mise à jour de Hydro-Quebec-API-Wrapper à la version 4.2.6

### Corrigé
- Erreur hydroqc.error.HydroQcHTTPError: Bad JSON format Fix: [#31](https://github.com/hydroqc/hydroqc-ha/issues/31)
- Mise à jour automatique de la criticité des événements calendrier de pointe existants
  - Les événements calendrier sont maintenant mis à jour en place lorsque leur criticité change (critique ↔ non-critique)
  - Évite la suppression et recréation d'événements, préservant les UIDs et l'historique
  - Mise à jour du titre et de la description pour refléter le nouveau statut de criticité
  - Améliore l'expérience utilisateur en maintenant la cohérence des événements calendrier
- Correction des importations de tests suite à la refactorisation modulaire
- Amélioration des tests avec freezegun pour des tests déterministes basés sur le temps

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
