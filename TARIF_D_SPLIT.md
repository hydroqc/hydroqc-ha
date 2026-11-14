# Tarif D : séparation prix bas / prix élevé

Le tarif D d'Hydro-Québec (incluant le tarif D avec l'option Crédits hivernaux, DCPC)
facture l'électricité à deux prix :

- **Prix bas** : les premiers `40 kWh × nombre de jours` consommés pendant une période de
  facturation. Pour une période typique de 62 jours, cela représente 2 480 kWh.
- **Prix élevé** : toute la consommation au-delà de ce seuil.

L'intégration sépare la consommation horaire du tarif D en deux flux pour le tableau de bord
Énergie de Home Assistant, comme elle le fait déjà pour les tarifs DT et DPC (biénergie), pour
lesquels l'API d'Hydro-Québec fournit directement les deux flux.

---

## Ce que vous obtenez

### Tableau de bord Énergie

Deux nouveaux flux de consommation, en plus du total :

- **Low Price Hourly Consumption** : consommation au prix bas
- **High Price Hourly Consumption** : consommation au prix élevé

### Trois capteurs (tarifs D et DCPC seulement)

| Capteur | Description |
|---------|-------------|
| **Seuil Bas Prix** | Allocation totale au prix bas pour la période en cours (40 kWh × jours) |
| **Bas Prix Restant** | kWh encore disponibles au prix bas pour la période en cours |
| **Budget Quotidien Bas Prix** | Moyenne quotidienne restante avant d'atteindre le seuil |

### Service `hydroqc.resplit_tarif_d_history`

Recalcule les flux prix bas et prix élevé à partir de tout l'historique de consommation totale
déjà présent dans Home Assistant. Voir [Faut-il lancer le recalcul ?](#faut-il-lancer-le-recalcul-)

### Option : capteur de durée de la période de facturation

Dans les options de l'intégration, le champ **Capteur de durée de période de facturation
(optionnel)** permet de choisir le capteur qui suit la durée de vos périodes de facturation
(par exemple le capteur **Durée période facturation** de l'intégration). Seul le service de
recalcul s'en sert, pour connaître les vraies dates de début des périodes passées.

---

## Faut-il lancer le recalcul ?

### Nouvelle installation

**Non.** L'importation de l'historique de consommation sépare déjà chaque heure en prix bas et
prix élevé au fur et à mesure, et la synchronisation quotidienne fait de même pour les jours
suivants.

### Mise à jour depuis une version antérieure

**Oui, une seule fois.** Les versions précédentes n'écrivaient que le flux total pour le tarif D.
Après la mise à jour, la synchronisation quotidienne écrit les deux nouveaux flux pour les jours à
venir, mais l'historique déjà importé n'a pas encore de séparation. Lancez le service une fois
après la mise à jour et le redémarrage de Home Assistant :

1. Allez dans **Outils de développement → Actions**
2. Cherchez `hydroqc.resplit_tarif_d_history`
3. Sous **Cibles**, choisissez une entité ou l'appareil de votre contrat (par exemple
   `maison (DCPC)`)
4. Cliquez sur **Exécuter l'action**

Le recalcul se fait en arrière-plan et peut prendre plusieurs minutes. Ces deux messages
apparaissent dans **Paramètres → Système → Journaux** :

```
Tarif D historical re-split STARTING — processing up to 800 days of hourly data. ...
Tarif D historical re-split COMPLETE — ... low price records, ... high price records imported. ...
```

> **Conseil :** si vous voulez utiliser le capteur de durée de la période de facturation,
> choisissez-le dans les options **avant** de lancer le recalcul.

---

## Ajouter les flux au tableau de bord Énergie

1. Ouvrez la configuration Énergie (**Paramètres → Tableaux de bord → Énergie**, ou
   **Paramètres → Énergie** selon votre version de Home Assistant)
2. Sous **Réseau électrique**, cliquez sur **Ajouter une consommation**
3. Cherchez le nom de votre contrat (par exemple `maison`). Vous verrez :
   - **Maison Low Price Hourly Consumption**
   - **Maison High Price Hourly Consumption**
   - **Maison Total Hourly Consumption** (existant)
4. Ajoutez **Low Price** et **High Price**
5. Retirez **Total** si vous ne voulez que la vue en deux couleurs, sinon la consommation sera
   comptée deux fois
6. Cliquez sur **Enregistrer**

---

## Fonctionnement

### Règle de séparation

Pour chaque période de facturation :

1. Le seuil est calculé : `40 kWh × nombre de jours de la période`
2. La consommation horaire est traitée dans l'ordre chronologique depuis le début de la période
3. Chaque heure est répartie ainsi :
   - **prix bas** : `min(kWh de l'heure, seuil restant)`
   - **prix élevé** : `max(0, kWh de l'heure − seuil restant)`
4. Le seuil restant diminue à mesure que la consommation au prix bas s'accumule
5. Une fois le seuil atteint, toute la consommation suivante va au prix élevé
6. L'allocation complète (`40 kWh × jours`) recommence au début de chaque nouvelle période

### Dates des périodes de facturation

La séparation doit savoir quand chaque période commence et finit. Les sources, par ordre de
préférence :

1. **L'historique du capteur de durée de la période de facturation** choisi dans les options :
   la source la plus précise. Elle remonte aussi loin que le recorder conserve l'historique des
   états (`purge_keep_days`, 10 jours par défaut).
2. **La période en cours du contrat** (date de début et durée) : utilisée quand il n'y a pas
   d'historique du capteur. Les jours qui précèdent la période en cours (par exemple hier, juste
   après le début d'une nouvelle période) sont rattachés à la période précédente, jamais à une
   nouvelle allocation.
3. **Une approximation de 60 jours** (`TARIF_D_HISTORY_PERIOD_DAYS = 60`) : utilisée pour les
   données plus anciennes que ce que les sources précédentes couvrent. Les périodes sont
   estimées en remontant dans le temps à partir de la plus ancienne date de début connue. Les
   vraies périodes durent généralement de 57 à 64 jours, donc l'écart reste faible, mais il
   s'accumule sur un long historique.

La synchronisation quotidienne, l'importation de l'historique et le service de recalcul
utilisent la même implémentation (`tarif_d_split.py`). Seule la source des dates de période
diffère : le recalcul lit l'historique du capteur, alors que la synchronisation et l'importation
se basent sur la période en cours du contrat.

**Limitation connue :** la plus ancienne période traitée peut n'être que partiellement présente
dans Home Assistant. Les heures d'avant le début de l'historique sont inconnues, donc cette
première période partielle reçoit une allocation complète et sa part au prix bas est
surestimée. Toutes les périodes suivantes sont exactes (ou aussi exactes que leurs dates).

### Identifiants des statistiques

La séparation écrit dans ces statistiques (même format que pour DT et DPC), ici pour un contrat
nommé `maison` :

- `hydroqc:maison_reg_hourly_consumption` : consommation au prix bas
- `hydroqc:maison_haut_hourly_consumption` : consommation au prix élevé
- `hydroqc:maison_hourly_consumption` : consommation totale (jamais modifiée)

---

## Revenir en arrière

Le flux total n'est **jamais modifié** par la séparation ni par le recalcul. Si les résultats ne
vous conviennent pas :

- Relancez `hydroqc.resplit_tarif_d_history` : il recalcule et remplace entièrement les flux prix
  bas et prix élevé à partir du total.
- Ou remettez simplement **Total** dans le tableau de bord Énergie à la place de **Low Price** et
  **High Price**.

---

## Journalisation

Pour voir le détail dans les journaux, ajoutez à `configuration.yaml` :

```yaml
logger:
  default: warning
  logs:
    custom_components.hydroqc: debug
    hydroqc: debug
```

`custom_components.hydroqc` couvre l'intégration; `hydroqc` couvre la bibliothèque qui
communique avec Hydro-Québec.

---

## Constantes

| Constante | Valeur | Description |
|-----------|--------|-------------|
| `TARIF_D_THRESHOLD_KWH_PER_DAY` | 40 | kWh par jour au prix bas. À modifier si Hydro-Québec change le seuil. |
| `TARIF_D_HISTORY_PERIOD_DAYS` | 60 | Durée approximative d'une période de facturation quand l'historique réel n'est pas disponible. |
| `CONF_BILLING_DURATION_ENTITY` | `billing_duration_entity` | Clé d'option du capteur de durée de la période de facturation. |
