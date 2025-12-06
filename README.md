# Intégration Hydro-Québec pour Home Assistant

<p align="center">
  <img src="https://raw.githubusercontent.com/hydroqc/hydroqc-ha/main/images/logo.png" alt="Hydro-Québec Logo" width="200"/>
</p>

<p align="center">
  Surveillez et automatisez votre consommation électrique directement dans Home Assistant
</p>

<p align="center">
  <a href="https://github.com/hacs/integration"><img src="https://img.shields.io/badge/HACS-Custom-41BDF5.svg" alt="HACS"></a>
  <a href="https://github.com/hydroqc/hydroqc-ha/releases"><img src="https://img.shields.io/github/release/hydroqc/hydroqc-ha.svg" alt="Release"></a>
  <a href="https://github.com/hydroqc/hydroqc-ha/blob/main/LICENSE"><img src="https://img.shields.io/github/license/hydroqc/hydroqc-ha.svg" alt="License"></a>
  <a href="https://github.com/hydroqc/hydroqc-ha/stargazers"><img src="https://img.shields.io/github/stars/hydroqc/hydroqc-ha?style=social" alt="Stars"></a>
</p>

**Navigation rapide:** [Installation](#-installation-rapide) • [Configuration](#-configuration) • [Blueprints](#-blueprints) • [Capteurs](#-capteurs-disponibles) • [FAQ](#-faq)

---

## Qu'est-ce que c'est ?

Intégration **native** pour Home Assistant qui vous permet de :
- Surveiller votre consommation électrique en temps réel
- Suivre vos factures et coûts électriques
- Recevoir des alertes de périodes de pointe critiques
- Gérer vos crédits hivernaux (tarif DCPC)
- Automatiser vos appareils pendant les périodes de pointe
- Utiliser un calendrier intégré pour une fiabilité maximale

## Pourquoi cette integration ?

### Fiabilité avec l'approche "ceinture et bretelles"

L'intégration calendrier offre **plusieurs niveaux de protection** pour vos automatisations :

- **Persistance** - Les événements restent même si l'API est indisponible  
- **Déclencheurs natifs HA** - Utilise le système éprouvé de Home Assistant  
- **Fallback manuel** - Créez des événements manuellement en cas de problème  

### Fonctionnalités complètes

- **Tous les tarifs supportés** : D, DT, DPC (Flex-D), DCPC (Crédits hivernaux)
- **Mode sans compte** : Surveillez les pointes sans identifiants
- **Multi-contrats** : Gérez maison, chalet, etc.
- **Blueprints prêt-à-l'emploi** : Automatisations optimisées incluses

---

## Installation rapide

### Via HACS (Recommande)

**Option 1 : Installation en un clic**

[![Ajouter à HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=hydroqc&repository=hydroqc-ha&category=integration)

Cliquez sur le badge ci-dessus, puis :
1. Cliquez sur **"Télécharger"**
2. **Redémarrez Home Assistant**
3. Ajoutez l'intégration dans **Paramètres** → **Appareils et services**

**Option 2 : Installation manuelle dans HACS**

<details>
<summary>Cliquez pour voir les étapes détaillées</summary>

1. Ouvrez **HACS** dans Home Assistant
2. Cliquez sur **Intégrations**
3. Cliquez sur les **3 points** → **"Dépôts personnalisés"**
4. Ajoutez : `https://github.com/hydroqc/hydroqc-ha` (catégorie: Intégration)
5. Recherchez **"Hydro-Québec"** et cliquez sur **"Télécharger"**
6. **Redémarrez Home Assistant**

</details>

### Installation manuelle

<details>
<summary>Pour les utilisateurs avancés</summary>

1. Téléchargez depuis [GitHub Releases](https://github.com/hydroqc/hydroqc-ha/releases)
2. Extrayez dans `custom_components/hydroqc`
3. Redémarrez Home Assistant

</details>

---

## Configuration

### Option 1 : Avec compte Hydro-Québec (Accès complet)

Accès à **toutes les données** : consommation, facturation, pointes, crédits hivernaux

1. **Paramètres** → **Appareils et services** → **+ Ajouter une intégration**
2. Recherchez **"Hydro-Québec"**
3. Choisissez **"Se connecter avec un compte"**
4. Entrez vos identifiants Hydro-Québec
5. Sélectionnez le contrat à surveiller
6. Terminé ! Les capteurs apparaissent en ~60 secondes

### Option 2 : Données publiques (Sans compte)

Uniquement les **alertes de pointe** sans identifiants

1. Suivez les étapes 1-2 ci-dessus
2. Choisissez **"Données de pointe uniquement"**
3. Sélectionnez votre tarif
4. Les alertes de pointe sont actives !

### Configuration du calendrier (Recommandé pour fiabilité maximale)

Le calendrier augmente la fiabilité de vos automatisations :

**Étape 1 : Créer un calendrier local**

1. **Paramètres** → **Intégrations** → **+ Ajouter**
2. Recherchez **"Calendrier local"** (Local Calendar)
3. Créez un calendrier (ex: "HQ Pointes")
4. [Documentation HA](https://www.home-assistant.io/integrations/local_calendar/)

**Étape 2 : Activer dans Hydro-Québec**

1. **Hydro-Québec** → **Options** (⋮) → **Configurer**
2. Cochez **"Synchroniser vers calendrier"**
3. Sélectionnez votre calendrier
4. Les événements sont synchronisés automatiquement !

> **Astuce** : Vous pouvez créer des événements manuellement si l'API est indisponible

**Création manuelle d'événements** (fallback en cas de problème) :

Consultez la section [Tester vos blueprints](#tester-vos-blueprints) pour des exemples d'événements pour DCPC et DPC.

---

## Blueprints

Automatisations prêt-à-l'emploi pour gérer les périodes de pointe.

### Blueprint Crédits hivernaux (DCPC)

Pour les utilisateurs du tarif D avec Crédits hivernaux (CPC).

[![Importer le blueprint](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fhydroqc%2Fhydroqc-ha%2Fblob%2Fmain%2Fblueprints%2Fwinter-credits-calendar.yaml)

**Fonctionnalités** :
- Pré-chauffage avant pointes critiques (délai configurable)
- Actions distinctes pointes critiques vs régulières
- Gestion des périodes d'ancrage (matin et soir)
- Exécution parallèle pour fiabilité
- Filtres automatiques par tarif et criticité

### Blueprint Flex-D (DPC)

Pour les utilisateurs du tarif Flex-D (DPC).

[![Importer le blueprint](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fhydroqc%2Fhydroqc-ha%2Fblob%2Fmain%2Fblueprints%2Fflex-d-calendar.yaml)

**Fonctionnalités** :
- Pré-chauffage configurable
- Actions de début et fin de pointe
- Exécution parallèle pour fiabilité
- Filtres DPC uniquement

> **Utilisateurs de blueprints existants** : Réimportez vos blueprints pour bénéficier des dernières améliorations (notifications persistantes, meilleure gestion des erreurs).

### Tester vos blueprints

Après avoir importé un blueprint et créé votre automatisation, **nous recommandons fortement de créer un événement de test** dans votre calendrier pour valider que tout fonctionne correctement.

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


### Comprendre les paramètres des blueprints

#### Délai avant début pointe critique (Pre-critical peak start offset)

- **Par défaut** : `-00:01:00` (1 minute avant)
- **Utilité** : Permet à vos appareils de se stabiliser avant la pointe
- **Exemple** : Pointe à 18:00 → actions à 17:59

#### Actions en parallèle (Parallel action calls)

Les actions s'exécutent simultanément plutôt que séquentiellement.

**Avantage** : Si une action échoue, les autres continuent !

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

#### Délai aléatoire en fin de pointe (Random delay on critical peak end)

- **Par défaut** : 30 secondes à 5 minutes
- **Raison** : Évite une surcharge du réseau électrique
- **Impact** : Des milliers d'appareils ne redémarrent pas simultanément
- **Recommandation** : Conservez ce délai pour être un bon citoyen du réseau

---

## Capteurs disponibles

### Capteurs de compte (Mode authentifié uniquement)

| Capteur | Description |
|---------|-------------|
| **Solde** | Solde actuel du compte |
| **Période de facturation** | Jour actuel, durée, facture projetée |
| **Consommation** | Moyenne quotidienne, total, projection |
| **Coût** | Moyenne du coût par kWh, facture quotidienne |
| **Température** | Température moyenne pour la période |
| **Panne** | Panne prochaine/actuelle avec détails |

### Capteurs spécifiques aux tarifs

<details>
<summary><strong>Tarif DCPC (Crédits hivernaux)</strong></summary>

- Crédit hivernal cumulé
- Crédit hivernal projeté
- Heures de début/fin ancrage/pointe
- Performance de pointe d'hier
- Indicateurs de pointe critique
- Alertes de préchauffage

</details>

<details>
<summary><strong>Tarif DPC (Flex-D)</strong></summary>

- Détail de la période DPC actuelle
- Heures de début/fin prochaine pointe
- Heure de début du préchauffage
- Nombre d'heures critiques
- Nombre de jours hivernaux
- Alertes de pointe critique

</details>

<details>
<summary><strong>Tarifs DT / DPC</strong></summary>

- Consommation aux prix supérieur/inférieur
- Économie/perte nette vs Tarif D

</details>

---

## FAQ

<details>
<summary><strong>Échec de connexion</strong></summary>

- Vérifiez vos identifiants sur [Hydro-Québec](https://session.hydroquebec.com/)
- Vérifiez les caractères spéciaux dans le mot de passe
- Assurez-vous que le compte a des contrats actifs

</details>

<details>
<summary><strong>Aucune donnée n'apparaît</strong></summary>

- Attendez 60 secondes pour la première mise à jour
- Vérifiez les journaux : **Paramètres** → **Système** → **Journaux**
- Vérifiez que le portail Hydro-Québec est en ligne

</details>

<details>
<summary><strong>Capteurs indisponibles</strong></summary>

- Certains capteurs sont saisonniers (crédits hivernaux : déc-mars)
- Vérifiez si votre tarif supporte le capteur
- Consultez les journaux du coordinateur

</details>

<details>
<summary><strong>Calendrier ne se synchronise pas</strong></summary>

- Vérifiez que le calendrier local est installé
- Vérifiez que le calendrier est sélectionné dans les options
- Redémarrez l'intégration après configuration
- Consultez les journaux pour erreurs de validation

</details>

---

## Migration depuis hydroqc2mqtt

Vous utilisez déjà le Add-on ou hydroqc2mqtt ?

- **Installation en parallèle possible** - Testez en toute sécurité  
- **Noms de capteurs identiques** - Seul le préfixe change  
- **Nouveaux blueprints calendrier** - Plus fiables que les versions antérieures  

**Étapes de migration** :

1. Installez l'intégration en parallèle
2. Testez vos automatisations avec les nouveaux capteurs
3. **Remplacez vos anciens blueprints** par les nouveaux blueprints calendrier de ce dépôt
   - Les blueprints hydroqc2mqtt utilisaient les capteurs binaires (approche moins fiable)
   - Les nouveaux blueprints utilisent le calendrier (approche "ceinture et bretelles")
   - Supprimez vos anciennes automatisations basées sur les anciens blueprints
   - Importez les nouveaux blueprints (liens d'import dans la section [Blueprints](#blueprints))
4. Une fois satisfait, désactivez l'ancien système

---

## Développement

Vous souhaitez contribuer ? Consultez [CONTRIBUTING.md](CONTRIBUTING.md) pour :

- Configuration de l'environnement de développement
- Directives de contribution
- Documentation des tests
- Conventions de code

---

## Ressources

- **Documentation** : [hydroqc.ca](https://hydroqc.ca)
- **Problèmes** : [GitHub Issues](https://github.com/hydroqc/hydroqc-ha/issues)
- **Code source** : [Dépôt GitHub](https://github.com/hydroqc/hydroqc-ha)
- **Changelog** : [CHANGELOG.md](CHANGELOG.md)

## Projets connexes

- **hydroqc2mqtt** : Démon MQTT (prédécesseur de cette intégration)
- **Hydro-Quebec-API-Wrapper** : [Bibliothèque Python](https://github.com/hydroqc/Hydro-Quebec-API-Wrapper) sous-jacente

---

## Licence

Ce projet est sous licence **AGPL-3.0** - consultez le fichier [LICENSE](LICENSE) pour plus de détails.

## Crédits

Développé avec passion par l'[équipe Hydroqc](https://hydroqc.ca)

<p align="center">
  <strong>Non affilié ni approuvé par Hydro-Québec</strong>
</p>

---

<p align="center">
  <sub>Si cette intégration vous aide à économiser sur vos factures d'électricité, pensez à mettre une étoile sur GitHub !</sub>
</p>
