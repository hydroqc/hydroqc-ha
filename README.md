# Intégration Hydro-Québec pour Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![GitHub Release](https://img.shields.io/github/release/hydroqc/hydroqc-ha.svg)](https://github.com/hydroqc/hydroqc-ha/releases)
[![License](https://img.shields.io/github/license/hydroqc/hydroqc-ha.svg)](LICENSE)

Composant natif pour Home Assistant permettant de surveiller vos comptes d'électricité Hydro-Québec. Accédez aux données de consommation, informations de facturation, périodes de pointe, crédits hivernaux et notifications de pannes directement dans Home Assistant.

## Fonctionnalités

- ✅ **Intégration complète du compte** : Solde, consommation, données de facturation
- ✅ **Plusieurs tarifs** : D, DT, DPC (Flex-D), M, M-GDP, DCPC (Crédits hivernaux)
- ✅ **Surveillance des périodes de pointe** : Alertes de pointe critique et notifications de préchauffage en temps réel
- ✅ **Suivi des crédits hivernaux** : Crédits cumulés et projetés (tarif DCPC)
- ✅ **Notifications de pannes** : Informations sur les pannes prochaines/actuelles avec détails
- ✅ **Mode pointes uniquement** : Surveillez les pointes sans identifiants de compte
- ✅ **Support multi-contrats** : Ajoutez plusieurs contrats (un par entrée de configuration)
- ✅ **Bilingue** : Support complet en français et anglais

## Tarifs supportés

| Tarif | Description | Fonctionnalités |
|-------|-------------|-----------------|
| **D** | Tarif résidentiel D | Consommation et facturation standard |
| **D + CPC** | Tarif D avec Crédits hivernaux | Périodes de pointe, crédits hivernaux, pointes critiques |
| **DT** | Tarif double énergie | Suivi de la consommation aux prix supérieur/inférieur |
| **DPC** | Flex-D | Tarification dynamique, gestion des pointes critiques |
| **M** | Tarif petite entreprise M | Suivi de la consommation commerciale |
| **M-GDP** | Tarif M avec Gestion de la puissance | Commercial avec gestion de la demande |

## Développement

Consultez [CONTRIBUTING.md](CONTRIBUTING.md) pour la configuration du développement et les directives.

### Démarrage rapide avec Dev Container

1. Installez [VS Code](https://code.visualstudio.com/) et [Docker](https://www.docker.com/)
2. Installez l'extension [Dev Containers](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-containers)
3. Ouvrez ce dépôt dans VS Code
4. Appuyez sur `F1` → "Dev Containers: Reopen in Container"
5. Attendez la fin de la configuration (2-3 minutes la première fois)
6. Exécutez `just start` pour lancer Home Assistant

Le conteneur de développement inclut tous les outils requis : Python 3.13, uv, ruff, mypy, pytest, docker-in-docker et le shell fish.

### Tests

Le projet inclut une suite de tests complète couvrant les tests unitaires et d'intégration.

#### Exécution rapide des tests

```bash
# Exécuter tous les tests
uv run pytest

# Exécuter avec couverture
just test-cov

# Exécuter la suite de tests complète (lint + format + vérification de types + tests)
just ci
```

#### Commandes de test courantes

```bash
# Tests unitaires uniquement
uv run pytest tests/unit/

# Tests d'intégration uniquement
uv run pytest tests/integration/

# Fichier de test spécifique
uv run pytest tests/unit/test_coordinator.py

# Sortie détaillée
uv run pytest -v

# Afficher les instructions print
uv run pytest -s
```

#### Qualité du code

```bash
# Linting
uv run ruff check custom_components/

# Correction automatique des problèmes de linting
uv run ruff check --fix custom_components/

# Formatage du code
uv run ruff format custom_components/

# Vérification des types (mode strict)
uv run mypy custom_components/hydroqc/
```

Consultez [tests/README.md](tests/README.md) pour la documentation détaillée des tests.

## Installation

### Via HACS (Recommandé)

#### Prérequis

Assurez-vous que [HACS](https://hacs.xyz/) est installé dans votre instance Home Assistant. Si ce n'est pas déjà fait :

1. Suivez le [guide d'installation HACS](https://hacs.xyz/docs/setup/download)
2. Redémarrez Home Assistant après l'installation de HACS

#### Installation de l'intégration

1. Ouvrez **HACS** dans Home Assistant
2. Cliquez sur **Intégrations**
3. Cliquez sur les **3 points** dans le coin supérieur droit
4. Sélectionnez **"Dépôts personnalisés"**
5. Ajoutez l'URL du dépôt : `https://github.com/hydroqc/hydroqc-ha`
6. Sélectionnez la catégorie : **Intégration**
7. Cliquez sur **"Ajouter"**
8. Recherchez **"Hydro-Québec"** dans la liste des intégrations HACS
9. Cliquez sur l'intégration **Hydro-Québec**
10. Cliquez sur **"Télécharger"** (ou **"Installer"**)
11. **Redémarrez Home Assistant**

> **Note** : Après le redémarrage, vous devrez encore configurer l'intégration (voir section Configuration ci-dessous).

### Installation manuelle

1. Téléchargez la dernière version depuis [GitHub Releases](https://github.com/hydroqc/hydroqc-ha/releases)
2. Extrayez le dossier `hydroqc` dans votre répertoire `custom_components`
3. Redémarrez Home Assistant

## Configuration

### Option 1 : Avec compte Hydro-Québec (Accès complet)

1. Allez dans **Paramètres** → **Appareils et services**
2. Cliquez sur **+ Ajouter une intégration**
3. Recherchez **Hydro-Québec**
4. Sélectionnez **"Se connecter avec un compte Hydro-Québec"**
5. Entrez vos identifiants :
   - **Nom d'utilisateur** : Votre courriel Hydro-Québec
   - **Mot de passe** : Votre mot de passe Hydro-Québec
   - **Nom du contrat** : Nom convivial (ex: "Maison", "Chalet")
6. Sélectionnez le contrat à surveiller dans la liste
7. Terminé ! Les capteurs apparaîtront dans ~60 secondes

### Option 2 : Données de pointe uniquement (Aucun compte requis)

Parfait pour les utilisateurs qui souhaitent uniquement des alertes de période de pointe sans fournir d'identifiants :

1. Suivez les étapes 1-3 ci-dessus
2. Sélectionnez **"Données de pointe uniquement (aucun compte requis)"**
3. Configurez :
   - **Nom du contrat** : Nom convivial
   - **Tarif** : Votre tarif d'électricité (D, DT, DPC, etc.)
   - **Option de tarif** : CPC si applicable, ou Aucune
4. Terminé ! Les capteurs de pointe apparaîtront

### Configuration multi-contrats

Pour surveiller plusieurs contrats (ex: maison + chalet) :

1. Ajoutez l'intégration une fois pour chaque contrat
2. Chacun apparaîtra comme un appareil séparé
3. Tous les capteurs groupés sous leurs appareils respectifs

## Capteurs disponibles

### Capteurs de compte (Mode authentifié uniquement)

- **Solde** : Solde actuel du compte
- **Période de facturation** : Jour actuel, durée, facture projetée
- **Consommation** : Moyenne quotidienne, total, projection
- **Coût** : Moyenne du coût par kWh, moyenne de la facture quotidienne
- **Température** : Température moyenne pour la période
- **Panne** : Panne prochaine/actuelle avec attributs

### Capteurs spécifiques aux tarifs

#### Tarifs DT / DPC
- Consommation aux prix supérieur/inférieur
- Économie/perte nette vs Tarif D

#### Spécifiques au DPC (Flex-D)
- Détail de la période DPC actuelle
- Heures de début/fin de la prochaine pointe
- Heure de début du préchauffage
- Nombre d'heures critiques
- Nombre de jours hivernaux
- Alertes de pointe critique (aujourd'hui/demain)

#### Spécifiques au DCPC (Crédits hivernaux)
- Crédit hivernal cumulé
- Crédit hivernal projeté
- Heures de début/fin de l'ancrage/pointe suivant
- Performance de pointe d'hier (crédits, consommation)
- Indicateurs de pointe critique
- Alertes de préchauffage

### Capteurs de pointe (Tous les modes)

Disponibles même en mode pointes uniquement :
- États des périodes de pointe
- Avertissements de pointe critique
- Notifications de préchauffage
- Calendriers de pointes à venir

## Exemples d'automatisations

### Alerte de pointe critique

```yaml
automation:
  - alias: "Alerte de pointe critique"
    trigger:
      - platform: state
        entity_id: binary_sensor.maison_pointe_critique_matin_aujourd_hui
        to: "on"
    action:
      - service: notify.mobile_app
        data:
          title: "⚡ Pointe critique aujourd'hui"
          message: "Réduisez la consommation d'électricité entre 6h-9h"
```

### Notification de préchauffage

```yaml
automation:
  - alias: "Début du préchauffage"
    trigger:
      - platform: state
        entity_id: binary_sensor.maison_prechauffage_en_cours
        to: "on"
    action:
      - service: climate.set_temperature
        target:
          entity_id: climate.thermostat
        data:
          temperature: 22  # Préchauffage avant la pointe
```

## Dépannage

### Échec de connexion
- Vérifiez vos identifiants sur le [site web d'Hydro-Québec](https://session.hydroquebec.com/)
- Vérifiez les caractères spéciaux dans le mot de passe
- Assurez-vous que le compte a des contrats actifs

### Aucune donnée n'apparaît
- Attendez 60 secondes pour la première mise à jour
- Vérifiez les journaux de Home Assistant : Paramètres → Système → Journaux
- Vérifiez que le portail Hydro-Québec est en ligne

### Capteurs indisponibles
- Certains capteurs ne sont actifs que pendant des saisons spécifiques (crédits hivernaux)
- Vérifiez si votre plan tarifaire supporte le capteur
- Vérifiez que le coordinateur se met à jour (consultez les journaux)

## Support

- **Problèmes** : [GitHub Issues](https://github.com/hydroqc/hydroqc-ha/issues)
- **Documentation** : [hydroqc.ca](https://hydroqc.ca)
- **Code source** : [Dépôt GitHub](https://github.com/hydroqc/hydroqc-ha)

## Projets connexes

- **hydroqc2mqtt** : Démon MQTT (prédécesseur de cette intégration)
- **Hydro-Quebec-API-Wrapper** : La bibliothèque Python sous-jacente

## Licence

Ce projet est sous licence AGPL-3.0 - consultez le fichier [LICENSE](LICENSE) pour plus de détails.

## Crédits

Développé par l'[équipe Hydroqc](https://hydroqc.ca)

---

**Non affilié ni approuvé par Hydro-Québec**
