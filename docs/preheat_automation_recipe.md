# Guide d'automatisation : Pré-chauffage et gestion des pointes Hydro-Québec (Tarif Flex D / Crédits hivernaux)

Ce guide présente les meilleures pratiques pour automatiser le **pré-chauffage**, le **stockage thermique** (chauffe-eau, plinthes électriques) et le **délestage** lors des événements de pointe d'Hydro-Québec dans Home Assistant.

---

## 1. Pourquoi utiliser les déclencheurs calendrier plutôt que le capteur binaire seul ?

Le capteur binaire de pointe critique (`binary_sensor.hydroqc_*_critical_peak_in_progress`) passe à `on` uniquement au moment précis où la pointe débute (6 h 00 ou 16 h 00). Si vous attendez ce changement d'état pour agir, il est trop tard pour accumuler de la chaleur au tarif réduit.

L'intégration `hydroqc` expose directement vos événements de pointe dans une entité calendrier (`calendar.hydroqc_*`). Home Assistant permet d'utiliser un **décalage négatif (`offset`)** sur les déclencheurs calendrier afin de lancer le pré-chauffage plusieurs heures avant le début de la pointe :

```yaml
triggers:
  - trigger: calendar
    event: start
    entity_id: calendar.hydroqc_pointes
    offset: "-02:00:00"   # Se déclenche exactement 2 heures AVANT le début de la pointe
```

Ce déclencheur s'active automatiquement :
* À **4 h 00** pour une pointe matinale (6 h 00 – 9 h 00 ou 6 h 00 – 10 h 00).
* À **14 h 00** pour une pointe du soir (16 h 00 – 20 h 00).
* **Uniquement les jours où une pointe est confirmée par Hydro-Québec.**

---

## 2. Stratégie recommandée en 3 phases

### Phase 1 : Pré-chauffage (2 h avant la pointe)
* **Thermostats (Sinopé, Mysa, Stelpro, etc.)** : Augmenter temporairement la consigne de **+1,5 °C à +2,0 °C** (ex. 23,0 °C) afin d'accumuler de l'énergie thermique dans la masse du bâtiment (planchers, murs, mobilier).
* **Chauffe-eau (contrôleur 240 V / 50 A type Sinopé Calypso RM3500ZB/WF)** : S'assurer que le relais est **ACTIVÉ (`on`)** pour que le réservoir atteigne sa température maximale avant la coupure.
* **Échangeur d'air (VRC / VRE)** : Faire fonctionner la ventilation pour renouveler l'air intérieur et évacuer l'humidité avant la mise en veille.

### Phase 2 : Pendant la pointe critique (Délestage)
* **Thermostats** : Abaisser la consigne à **18,0 °C – 18,5 °C** (l'inertie thermique maintient le confort tout en empêchant les plinthes de s'allumer pendant le tarif élevé de > 0,50 $/kWh en Flex D).
* **Chauffe-eau** : **COUPER (`off`)** le contrôleur du chauffe-eau (économie de 3 000 W à 4 500 W). Un réservoir bien isolé de 40 à 60 gallons perd moins de 0,5 °C à 1 °C par heure.
* **Échangeur d'air** : Mettre à l'arrêt ou en mode recirculation pour éviter d'introduire de l'air extérieur à -20 °C dans la maison.
* **Charges secondaires** : Reporter la recharge du véhicule électrique, le sèche-linge et le chauffage des dépendances.

### Phase 3 : Fin de pointe (Reprise progressive)
* **Délai aléatoire (30 s à 5 min)** : Attendre un court délai aléatoire avant de réactiver les gros appareils afin d'éviter un appel de puissance simultané sur le réseau.
* **Thermostats** : Rétablir la consigne normale (**21,0 °C – 21,5 °C**).
* **Chauffe-eau et ventilation** : Rétablir l'alimentation normale (`on`).

---

## 3. Utiliser les Blueprints officiels ou une automatisation YAML

Ce dépôt inclut deux blueprints prêts à l'emploi qui intègrent déjà les déclencheurs calendrier, le délai de pré-chauffage et le délai aléatoire de fin de pointe :
* **Tarif Flex D (DPC)** : [`blueprints/flex-d-calendar.yaml`](../blueprints/flex-d-calendar.yaml)
* **Crédits hivernaux (CPC)** : [`blueprints/winter-credits-calendar.yaml`](../blueprints/winter-credits-calendar.yaml)

Pour tester votre configuration sans attendre une vraie pointe, utilisez le service intégré `hydroqc.create_peak_event` pour générer un événement de test dans votre calendrier.

### Exemple d'automatisation YAML personnalisée

```yaml
alias: "Hydro-Québec : Pré-chauffage avant pointe (T-2h)"
description: "Augmente les thermostats et active le chauffe-eau 2 heures avant une pointe."
mode: restart
triggers:
  - trigger: calendar
    event: start
    entity_id: calendar.hydroqc_pointes
    offset: "-02:00:00"
actions:
  - parallel:
      - action: climate.set_temperature
        target:
          entity_id:
            - climate.thermostat_salon
            - climate.thermostat_chambres
        data:
          temperature: 23.0
      - action: switch.turn_on
        target:
          entity_id: switch.chauffe_eau
      - action: notify.notify
        data:
          title: "⚡ Hydro-Québec : Pré-chauffage actif"
          message: "Pré-chauffage démarré (23 °C) en prévision de la pointe à venir."
```

---

## 4. Bonnes pratiques : Éviter les déclenchements intempestifs (`unavailable` → `off`)

Si vous créez des automatisations personnalisées basées sur l'état du capteur binaire de pointe (par exemple pour rétablir l'éclairage ou le chauffage à la fin d'une pointe), **spécifiez toujours `from: "on"` en plus de `to: "off"`** :

```yaml
triggers:
  - trigger: state
    entity_id: binary_sensor.hydroqc_maison_critical_peak_in_progress
    from: "on"
    to: "off"
```

> **Pourquoi est-ce important ?**  
> Si vous omettez `from: "on"`, votre automatisation de fin de pointe se déclenchera chaque fois que l'entité passe de `unavailable` (ou `unknown`) à `off` — notamment lors d'un redémarrage de Home Assistant ou d'un rechargement de l'intégration en pleine journée.
