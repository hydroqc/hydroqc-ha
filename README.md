# Intégration Hydro-Québec pour Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![GitHub Release](https://img.shields.io/github/release/hydroqc/hydroqc-ha.svg)](https://github.com/hydroqc/hydroqc-ha/releases)
[![License](https://img.shields.io/github/license/hydroqc/hydroqc-ha.svg)](LICENSE)

Composant natif pour Home Assistant permettant de surveiller vos comptes d'électricité Hydro-Québec. Accédez aux données de consommation, informations de facturation, périodes de pointe, crédits hivernaux et notifications de pannes directement dans Home Assistant.

## Question fréquentes À LIRE ABSOLUMENT!!!

### ⚠️ Avertissement ⚠️

Ce composant est tout nouveau et n'a jamais passé l'épreuve du feu d'un événement de pointe critique hivernal. Prenez pour acquis qu'un bug peut survenir et prévoyez déclencher vos automatisations d'une autre manière au besoin. Soyez assurés que je (@mdallaire) garde l'œil ouvert pour le premier événement et vais faire mon possible pour régler d'éventuels bugs rapidement.

### Est-ce que je peux installer cette intégration en parallèle du Add-on ou hydroqc2mqtt?

Oui! Absolument, c'est la manière la plus sûre de tester. Vous pouvez aussi désactiver temporairement le add-on/hydroqc2mqtt si vous êtes satisfait du fonctionnement de l'intégration afin d'éviter les appels en double vers Hydro-Québec.

### Comment migrer mes automatisations ou les blueprints vers l'intégration?

Les capteurs disponibles sont les mêmes qu'avec le add-on ou hydroqc2mqtt. Assurez-vous de mettre à jour les entités dans les blueprints et vos automatisations au besoin.

De nouveaux blueprints sont maintenant disponibles spécifiquement pour cette intégration utilisant le calendrier intégré. Consultez la section [Blueprints d'automatisation](#blueprints-dautomatisation) pour les importer en un clic.

## Fonctionnalités

- ✅ **Intégration complète du compte** : Solde, consommation, données de facturation
- ✅ **Plusieurs tarifs** : D, DT, DPC (Flex-D), M, M-GDP, DCPC (Crédits hivernaux)
- ✅ **Surveillance des périodes de pointe** : Alertes de pointe critique et notifications de préchauffage en temps réel
- ✅ **Suivi des crédits hivernaux** : Crédits cumulés et projetés (tarif DCPC)
- ✅ **Notifications de pannes** : Informations sur les pannes prochaines/actuelles avec détails
- ✅ **Mode pointes uniquement** : Surveillez les pointes sans identifiants de compte
- ✅ **Support multi-contrats** : Ajoutez plusieurs contrats (un par entrée de configuration)

## Tarifs supportés

| Tarif | Description | Fonctionnalités |
|-------|-------------|-----------------|
| **D** | Tarif résidentiel D | Consommation et facturation standard |
| **D + CPC** | Tarif D avec Crédits hivernaux | Périodes de pointe, crédits hivernaux, pointes critiques |
| **DT** | Tarif double énergie | Suivi de la consommation aux prix supérieur/inférieur |
| **DPC** | Flex-D | Tarification dynamique, gestion des pointes critiques |


## Installation

### Via HACS (Recommandé)

#### Prérequis

Assurez-vous que [HACS](https://hacs.xyz/) est installé dans votre instance Home Assistant. Si ce n'est pas déjà fait :

1. Suivez le [guide d'installation HACS](https://hacs.xyz/docs/setup/download)
2. Redémarrez Home Assistant après l'installation de HACS

#### Installation de l'intégration

**Option A : Installation en un clic**

[![Ouvrir votre instance Home Assistant et ouvrir le dépôt dans HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=hydroqc&repository=hydroqc-ha&category=integration)

Cliquez sur le badge ci-dessus pour ajouter automatiquement ce dépôt à HACS, puis :

1. Cliquez sur **"Télécharger"** (ou **"Installer"**)
2. **Redémarrez Home Assistant**

**Option B : Installation manuelle via HACS**

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

## Blueprints d'automatisation

L'intégration inclut deux blueprints pour automatiser vos réponses aux événements de pointe en utilisant le calendrier intégré :

### Blueprint Crédits hivernaux (DCPC)

Automatisation complète pour les utilisateurs du tarif D avec Crédits hivernaux (CPC). Gère les pointes critiques et régulières, ainsi que les périodes d'ancrage.

[![Ouvrir votre instance Home Assistant et afficher la prévisualisation d'un blueprint à importer.](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fhydroqc%2Fhydroqc-ha%2Fblob%2Fmain%2Fblueprints%2Fwinter-credits-calendar.yaml)

**Fonctionnalités** :
- Actions de pré-chauffage pour pointes critiques (délai configurable)
- Actions distinctes pour pointes critiques vs régulières
- Gestion des périodes d'ancrage (matin et soir)
- Exécution parallèle pour fiabilité
- Filtres automatiques par tarif et criticité

### Blueprint Flex-D (DPC)

Automatisation pour les utilisateurs du tarif Flex-D (DPC). Toutes les pointes DPC sont critiques par nature.

[![Ouvrir votre instance Home Assistant et afficher la prévisualisation d'un blueprint à importer.](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fhydroqc%2Fhydroqc-ha%2Fblob%2Fmain%2Fblueprints%2Fflex-d-calendar.yaml)

**Fonctionnalités** :
- Actions de pré-chauffage configurables
- Actions de début et fin de pointe
- Exécution parallèle pour fiabilité
- Filtres automatiques pour événements DPC critiques uniquement

> **Note** : Ces blueprints nécessitent l'activation du calendrier dans les options de l'intégration. Les événements sont créés automatiquement à partir des données de pointe.

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

## Développement

Consultez [CONTRIBUTING.md](CONTRIBUTING.md) pour la configuration du développement, les directives de contribution, et la documentation complète des tests.

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
