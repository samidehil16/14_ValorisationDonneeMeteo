# Valorisation Donnée Météo — CI/CD, Observabilité, Docker Hardened

![CI/CD Pipeline](https://github.com/samidehil16/14_ValorisationDonneeMeteo/actions/workflows/ci-tp.yml/badge.svg)

Fork pédagogique du projet **Data For Good — Saison 14**. Ce README documente l'intégralité du travail réalisé pour le TP DevOps/SecOps : pipeline CI/CD complète, monitoring pull-based, et durcissement de l'image Docker.

---

## Sommaire

1. [Architecture de la stack](#architecture-de-la-stack)
2. [Récapitulatif des livrables](#récapitulatif-des-livrables)
3. [Livrable 1 — Pipeline CI/CD](#livrable-1--pipeline-cicd)
4. [Livrable 2 — Pipeline Testing (break/fix)](#livrable-2--pipeline-testing-breakfix)
5. [Livrable 3 — Monitoring Prometheus + Grafana](#livrable-3--monitoring-prometheus--grafana)
6. [Livrable 4 — Docker Hardened Images](#livrable-4--docker-hardened-images-dhi)
7. [Sécurité applicative (Trivy + SBOM + OpenVEX + Scorecard)](#sécurité-applicative-trivy--sbom--openvex--scorecard)
8. [Reproductibilité — démarrage en local](#reproductibilité--démarrage-en-local)
9. [Structure du projet](#structure-du-projet)
10. [Workflow Data For Good (existant)](#workflow-data-for-good-existant)

---

## Architecture de la stack

```
                       ┌─────────────────┐
                       │     nginx       │  port hôte 80 → conteneur 8080
                       │  (unprivileged) │
                       └────┬───────┬────┘
                            │       │
                  /         │       │  /api/v1/*
             ┌──────────────▼──┐ ┌──▼──────────────────┐
             │  frontend Nuxt  │ │   backend Django    │   /metrics
             │  (DHI Node 24)  │ │  (DHI Python 3.13)  │ ◀──────────┐
             └─────────────────┘ └─────┬───────────────┘            │
                                       │                            │
                                       │ SQL via bd_net             │ scrape 15s
                                       │                            │
                              ┌────────▼─────────┐         ┌────────┴────────┐
                              │   timescaledb    │         │   prometheus    │  port 9090
                              │  pg17 + tsdb     │         │  v3.3.0         │
                              └──────────────────┘         └────────┬────────┘
                                                                    │
                                                                    │ datasource
                                                            ┌───────▼────────┐
                                                            │    grafana     │  port 3001
                                                            │   v11.3.1      │
                                                            └────────────────┘
```

- **Réseau Docker** : `app_net` pour le trafic applicatif, `bd_net` pour la BDD (isolation réseau).
- **Sécurité commune** à tous les services : `read_only: true`, `cap_drop: [ALL]`, `security_opt: [no-new-privileges:true]`, `tmpfs` ciblés, limites mémoire (`deploy.resources.limits.memory`).

---

## Récapitulatif des livrables

| # | Livrable demandé | Statut | Emplacement |
|---|---|---|---|
| 1.1 | Pipeline CI/CD fonctionnel | ✅ | [.github/workflows/ci-tp.yml](.github/workflows/ci-tp.yml) |
| 1.2 | Badge dans le README | ✅ | ligne 3 ci-dessus |
| 1.3 | Image Docker | ✅ | `ghcr.io/samidehil16/14_valorisationdonneemeteo-{backend,frontend}:latest` |
| 1.4 | Test report | ✅ | CI artifact `backend-test-report` (JUnit XML + coverage) |
| 1.5 | Scan code report | ✅ | CI artifact `scorecard-report` (SARIF + JSON natif) |
| 1.6 | Trivy report | ✅ | CI artifact `security-reports` (table + JSON) + `docker-image-reports` |
| 1.7 | OpenVEX file | ✅ | CI artifact `security-reports/vex.openvex.json` (16 statements) |
| 2.1 | Casser un test → CI catch | ✅ | branche `tp/pipeline-test-demo`, run [#24990510013](https://github.com/samidehil16/14_ValorisationDonneeMeteo/actions/runs/24990510013) |
| 2.2 | Fixer le test → CI passe | ✅ | run [#24990866309](https://github.com/samidehil16/14_ValorisationDonneeMeteo/actions/runs/24990866309) |
| 3.1 | Prometheus UI avec metrics | ✅ | service `prometheus` dans [docker-compose.dev.yml](docker-compose.dev.yml) |
| 3.2 | Grafana dashboard | ✅ | provisioning [grafana/](grafana/) |
| 4.1 | DHI Hardened Images | ✅ | [backend/Dockerfile](backend/Dockerfile), [frontend/Dockerfile](frontend/Dockerfile) |

---

## Livrable 1 — Pipeline CI/CD

### Vue d'ensemble du workflow

Fichier : [.github/workflows/ci-tp.yml](.github/workflows/ci-tp.yml). La pipeline se découpe en **5 stages** explicitement numérotés dans le YAML :

```
Stage 1 — backend     ─┐
                       ├─→ Stage 3 — security-scan ─┬─→ Stage 4 — scorecard (main only)
Stage 2 — frontend    ─┘                            └─→ Stage 5 — build-and-push (main only)
```

Le DAG est exprimé via les `needs:` entre jobs — ce qui permet à GitHub Actions de paralléliser ce qui peut l'être (`backend` et `frontend` tournent en parallèle) et de skipper proprement les jobs en aval si un job amont échoue (cf. [Livrable 2](#livrable-2--pipeline-testing-breakfix)).

### Stages présents (cf. consigne du TP)

| Stage demandé par la consigne | Job(s) qui l'implémente | Détails |
|---|---|---|
| **Install dependencies** | `backend`, `frontend` | `uv sync --extra dev` (Python) / `npm ci --legacy-peer-deps` (Node) |
| **Run tests** | `backend`, `frontend` | `pytest --cov --junitxml` / `vitest --project unit` |
| **Run linter** | `backend`, `frontend` | `ruff check .` / `eslint --ext .js,.ts,.vue .` |
| **Run security scan** | `security-scan` (+ `scorecard`) | Trivy fs (table+JSON), SBOM CycloneDX, OpenVEX, OSSF Scorecard |
| **Build Docker image** | `build-and-push` | `docker/build-push-action@v5` sur `./backend` et `./frontend` |
| **Push to registry (main only)** | `build-and-push` | `if: github.ref == 'refs/heads/main'` → `ghcr.io/...` |

### Choix techniques notables

- **Cache npm/uv** : `actions/setup-node@v4` avec `cache: 'npm'` et `cache-dependency-path: frontend/package-lock.json`. Côté backend, `uv` est volontairement rapide et la couche Docker utilise `--mount=type=cache` (BuildKit) pour réutiliser le cache entre builds.
- **Gating `main only`** : seuls le push d'image (et l'envoi du SARIF Scorecard via `publish_results`) sont conditionnés à la branche par défaut. Les autres jobs tournent sur **toutes** les branches/PRs pour fournir un retour rapide aux contributeurs.
- **Permissions minimales** par job (`permissions:` au niveau du job) — limiter l'effet d'une compromission éventuelle (principe du least privilege, prérequis de la check `Token-Permissions` du Scorecard).

### Artifacts uploadés

| Job | Artifact | Contenu |
|---|---|---|
| `backend` | `backend-test-report` | `coverage.xml` + `test-results.xml` (JUnit) |
| `frontend` | `frontend-test-report` | dossier `coverage/` |
| `security-scan` | `security-reports` | `trivy-report.{txt,json}`, `sbom-cyclonedx.json`, `vex.openvex.json` |
| `scorecard` | `scorecard-report` | `scorecard-results.sarif` + `scorecard-results.json` |
| `build-and-push` | `docker-image-reports` | `trivy-{backend,frontend}-image.txt` (scan des images pushées) |

---

## Livrable 2 — Pipeline Testing (break/fix)

La consigne demande explicitement de démontrer que la CI **catch** un test cassé puis **passe** quand il est fixé. La démonstration est faite sur une branche dédiée `tp/pipeline-test-demo` pour ne pas polluer `main`.

### Étape 1 — casser un test

Modification minimale et lisible dans [backend/weather/tests/unit/test_date_range.py](backend/weather/tests/unit/test_date_range.py) :

```diff
 def test_iter_days_intersecting_inclusive_single_day():
     out = list(iter_days_intersecting(dt.date(2024, 1, 1), dt.date(2024, 1, 1)))
-    assert out == [dt.date(2024, 1, 1)]
+    # INTENTIONAL BREAK for TP pipeline-testing demo (CI must catch this)
+    assert out == [dt.date(2024, 1, 2)]
```

**Run CI** : [#24990510013](https://github.com/samidehil16/14_ValorisationDonneeMeteo/actions/runs/24990510013) — ❌ FAIL en 41 s.

Sortie pytest qui prouve la détection :

```
FAILED weather/tests/unit/test_date_range.py::test_iter_days_intersecting_inclusive_single_day
assert [datetime.date(2024, 1, 1)] == [datetime.date(2024, 1, 2)]
At index 0 diff: datetime.date(2024, 1, 1) != datetime.date(2024, 1, 2)
```

**Comportement de gating** : tous les jobs en aval (`security-scan`, `scorecard`, `build-and-push`) sont automatiquement **skipped** par GitHub Actions parce qu'ils sont `needs: [backend]` (ou transitivement). On a bien un portail qualité — pas d'image Docker buildée tant que les tests rouges.

### Étape 2 — fixer le test

Reverse de la modification. **Run CI final tout vert** : [#24990866309](https://github.com/samidehil16/14_ValorisationDonneeMeteo/actions/runs/24990866309) — ✅ SUCCESS.

> Note : sur le run intermédiaire [#24990585022](https://github.com/samidehil16/14_ValorisationDonneeMeteo/actions/runs/24990585022), les tests passaient bien mais le job `scorecard` a échoué pour une raison externe au test : `ossf/scorecard-action` refuse de tourner sur autre chose que la branche par défaut (« only the default branch is supported »). On a corrigé en ajoutant `if: github.ref == 'refs/heads/main'` au job `scorecard` (commit `6689ce5`).

---

## Livrable 3 — Monitoring Prometheus + Grafana

### Architecture pull-based

Prometheus scrape les targets toutes les 15 secondes (cf. [prometheus/prometheus.yml](prometheus/prometheus.yml)). Pas d'agent côté application : le backend Django expose simplement un endpoint HTTP `/metrics` que Prometheus interroge.

### Exposition `/metrics` côté Django

Trois éléments suffisent — voir [backend/config/urls.py](backend/config/urls.py) :

1. `django-prometheus` ajouté à `INSTALLED_APPS`
2. Middlewares `BeforeMiddleware` (en première position) et `AfterMiddleware` (en dernière) → instrumente automatiquement toutes les vues
3. Route `path("", include("django_prometheus.urls"))` → expose `/metrics` au format Prometheus exposition

Métriques par défaut récupérées :
- `django_http_requests_total_by_method_total` — compteur par méthode HTTP
- `django_http_responses_total_by_status_total` — compteur par status code
- `django_http_requests_latency_including_middlewares_seconds_bucket` — histogramme de latence (avec middlewares)
- `process_resident_memory_bytes` — RSS du process gunicorn

### Configuration Prometheus

```yaml
scrape_configs:
  - job_name: "prometheus"
    static_configs:
      - targets: ["localhost:9090"]
  - job_name: "backend"
    metrics_path: /metrics
    static_configs:
      - targets: ["backend:8000"]
```

Le service `backend` est résolu via le DNS Docker du réseau `app_net` — pas besoin de port hôte exposé.

### Provisioning Grafana — full IaC

Tout est déclaratif dans [grafana/](grafana/), monté en lecture seule dans le conteneur. **Aucun clic** dans l'UI à refaire après un `docker compose down -v` :

```
grafana/
├── provisioning/
│   ├── datasources/
│   │   └── prometheus.yml          ← datasource Prometheus auto-créée
│   └── dashboards/
│       └── default.yml             ← provider config, charge tous les *.json
└── dashboards/
    └── django-overview.json        ← dashboard Django avec 4 panels
```

### Dashboard *Django Backend Overview*

| Panel | Requête PromQL |
|---|---|
| Request rate by method | `sum by (method) (rate(django_http_requests_total_by_method_total[5m]))` |
| Responses by status code | `sum by (status) (rate(django_http_responses_total_by_status_total[5m]))` |
| Latency p50 / p95 / p99 | `histogram_quantile(0.95, sum by (le) (rate(...latency..._bucket[5m])))` |
| Backend memory (RSS) | `process_resident_memory_bytes{job="backend"}` |

### Validation end-to-end

Trafic généré via 25 requêtes réparties sur 30 s (mix `200`/`301`/`400`/`404`) → métriques visibles côté Prometheus :

```
status=200  count=277
status=400  count=10
status=404  count=10
```

Et côté Grafana : pic d'activité visible, latence p95 ≈ 9.95 ms, RSS ≈ 65 MB.

---

## Livrable 4 — Docker Hardened Images (DHI)

### Pourquoi DHI

Les images `python:3.13-slim` et `node:24-alpine` classiques contiennent un shell, un package manager, et des binaires utiles pour le build mais inutiles en runtime — autant de surface d'attaque. Les **Docker Hardened Images** (`dhi.io/...`) sont des images **distroless** signées, scannées en continu, sans shell ni package manager dans la variante runtime. C'est la même philosophie que [`gcr.io/distroless`](https://github.com/GoogleContainerTools/distroless) mais maintenue par Docker Inc.

### Stratégie multi-stage

Backend ([backend/Dockerfile](backend/Dockerfile)) :

```Dockerfile
# Build stage : variante -dev (a un shell, peut utiliser uv)
FROM dhi.io/python:3.13-debian13-dev AS builder
COPY --from=ghcr.io/astral-sh/uv:0.10.0 /uv /uvx /bin/
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-install-project
COPY . .
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked

# Runtime stage : distroless, no shell, no pkg manager
FROM dhi.io/python:3.13-debian13
COPY --from=builder --chown=nonroot:nonroot /app /app
ENTRYPOINT ["gunicorn", "config.wsgi:application", ...]
```

Bénéfices :
- **Toolchain absente** de l'image runtime → pas de `pip install` possible si compromise
- **Pas de shell** → un attaquant qui obtiendrait RCE ne peut pas pivoter avec `bash`
- **Run as `nonroot`** par défaut (utilisateur built-in dans l'image DHI distroless)
- **BuildKit cache mounts** (`--mount=type=cache`) → rebuilds incrémentaux rapides

Frontend ([frontend/Dockerfile](frontend/Dockerfile)) : même pattern avec `dhi.io/node:24-debian13-{dev,}`.

### Hardening au niveau Compose

[docker-compose.dev.yml](docker-compose.dev.yml) applique le même socle de durcissement à **tous les services** :

```yaml
read_only: true
tmpfs: [/tmp]
security_opt: [no-new-privileges:true]
cap_drop: [ALL]
deploy.resources.limits.memory: 256M
```

Cas particuliers :
- `nginx` est passé en **`nginxinc/nginx-unprivileged`** (port 8080 dans le conteneur) parce que l'image officielle nginx tourne en root pour binder le port 80.
- `prometheus` tourne avec `user: "nobody"`.
- `timescaledb` garde quelques capabilities (`CHOWN`, `DAC_OVERRIDE`, `FOWNER`, `SETGID`, `SETUID`) parce que PostgreSQL en a besoin pour gérer ses fichiers de données.

### Authentification CI

Les bases `dhi.io/...` exigent des credentials Docker Hub. Le job `build-and-push` utilise donc deux logins (cf. [.github/workflows/ci-tp.yml#L182-L194](.github/workflows/ci-tp.yml#L182-L194)) :

```yaml
- name: Login to ghcr.io          # pour pousser l'image finale
  uses: docker/login-action@v3
  with: { registry: ghcr.io, username: ${{ github.actor }}, password: ${{ secrets.GITHUB_TOKEN }} }

- name: Login to dhi.io           # pour tirer les bases hardened
  uses: docker/login-action@v3
  with: { registry: dhi.io, username: ${{ secrets.DHI_USERNAME }}, password: ${{ secrets.DHI_TOKEN }} }
```

Les secrets `DHI_USERNAME` et `DHI_TOKEN` sont configurés dans `Settings → Secrets → Actions` du repo. Le PAT Docker Hub doit avoir le scope *Public Repo Read* et le compte doit avoir activé l'accès au catalog DHI (gratuit).

---

## Sécurité applicative (Trivy + SBOM + OpenVEX + Scorecard)

### Trivy — vulnérabilités

Deux scans dans la pipeline :

1. **Filesystem** (job `security-scan`) — Trivy parcourt le code source et les manifests (`pyproject.toml`, `package-lock.json`) pour détecter les CVE dans les dépendances.
2. **Image Docker** (job `build-and-push`) — Trivy scanne les images poussées sur `ghcr.io` pour détecter les CVE qui auraient été introduites par les bases ou pendant le build.

Sévérité filtrée à `HIGH,CRITICAL`. Sortie en table (lecture humaine) **et** JSON (consommation outillée — sert d'input au générateur VEX).

### SBOM — CycloneDX

Le job `security-scan` génère aussi un **SBOM** au format CycloneDX 1.5 (`sbom-cyclonedx.json`). Format standard ECMA → consommable par tout outil de supply-chain (Dependency-Track, Grype, etc.).

### OpenVEX — Vulnerability Exploitability eXchange

Le squelette « `statements: []` » initial n'apportait aucune information. Il a été remplacé par un vrai document OpenVEX v0.2.0 généré par [scripts/generate_vex.py](scripts/generate_vex.py) à partir du `trivy-report.json` :

- **1 statement par CVE détectée**
- `vulnerability.@id` = CVE ID
- `products[].@id` = `purl` (Package URL) extrait de Trivy (ex: `pkg:pypi/django@5.2.10`)
- `status` = `affected` pour toutes (l'artefact contient bien la version vulnérable au moment du scan ; passer à `fixed` ou `not_affected` exige soit un upgrade, soit une justification documentée — cf. spec OpenVEX)
- `action_statement` = version upstream qui corrige la CVE, quand Trivy la connaît

Exemple de statement généré :

```json
{
  "vulnerability": {"@id": "CVE-2026-1207", "name": "CVE-2026-1207"},
  "products": [{"@id": "pkg:pypi/django@5.2.10"}],
  "status": "affected",
  "timestamp": "2026-04-27T14:35:48.000Z",
  "action_statement": "Upstream fix available in: 6.0.2, 5.2.11, 4.2.28"
}
```

Le fichier final contient **16 statements** couvrant `django`, `tornado`, etc.

### OSSF Scorecard

Le job `scorecard` lance l'action `ossf/scorecard-action@v2.4.0` avec **deux formats de sortie** :

- **SARIF** (`scorecard-results.sarif`) → publié vers GitHub Code Scanning. Ne contient que les **violations** (1 finding ici, sur `Branch-Protection`).
- **JSON natif** (`scorecard-results.json`) → contient les **18 checks** avec leur score 0-10 et leur raison. Plus exploitable pour un livrable.

Score agrégé actuel : **2.7 / 10**. Faible, mais cohérent pour un fork sans politique de branche, sans signing, et avec des PRs courtes. Les axes les plus rentables pour remonter le score :

- `Token-Permissions` — déjà en bonne voie (permissions explicites par job)
- `Security-Policy` — ajouter `SECURITY.md`
- `Pinned-Dependencies` — pin par SHA des actions GitHub
- `Branch-Protection` — protéger `main` (PR review requis, status checks bloquants)

---

## Reproductibilité — démarrage en local

### Prérequis

- Docker Desktop ≥ 4.30 (pour BuildKit et `docker compose v2`)
- Compte Docker Hub avec accès au catalog DHI (gratuit après opt-in)
- `gh` CLI si tu veux récupérer les artifacts CI

### Lancer la stack complète

```bash
# 1. S'authentifier auprès de dhi.io (une seule fois)
docker login dhi.io
# Username: <ton login Docker Hub>
# Password: <PAT Docker Hub>

# 2. Build + start de tous les services
docker compose -f docker-compose.dev.yml up -d --build

# 3. Vérifier
curl -fsS http://localhost/api/v1/stations             # frontale via nginx
curl -fsS http://localhost:9090/-/healthy              # Prometheus OK
open  http://localhost:9090                            # Prometheus UI
open  http://localhost:3001                            # Grafana (admin/admin)
```

### Lancer les tests en local

```bash
# Backend (Python, uv)
cd backend && uv sync --extra dev && uv run pytest

# Frontend (Node, npm)
cd frontend && npm ci --legacy-peer-deps && npm run test:ci
```

### Récupérer les artifacts d'un run CI

```bash
RUN_ID=$(gh run list --repo samidehil16/14_ValorisationDonneeMeteo \
           --workflow=ci-tp.yml --branch main --status success \
           --limit 1 --json databaseId --jq '.[0].databaseId')

gh run download $RUN_ID --repo samidehil16/14_ValorisationDonneeMeteo \
  --name security-reports                              # Trivy + SBOM + VEX
gh run download $RUN_ID --repo samidehil16/14_ValorisationDonneeMeteo \
  --name scorecard-report                              # Scorecard SARIF + JSON
gh run download $RUN_ID --repo samidehil16/14_ValorisationDonneeMeteo \
  --name backend-test-report                           # JUnit + coverage
gh run download $RUN_ID --repo samidehil16/14_ValorisationDonneeMeteo \
  --name docker-image-reports                          # Trivy sur images Docker
```

---

## Structure du projet

```
.
├── .github/workflows/
│   └── ci-tp.yml                           # Pipeline CI/CD (5 stages)
├── backend/
│   ├── Dockerfile                          # multi-stage DHI Python
│   ├── .dockerignore
│   ├── config/urls.py                      # routing Django + /metrics
│   └── weather/                            # app métier (API, tests)
├── frontend/
│   ├── Dockerfile                          # multi-stage DHI Node
│   ├── .dockerignore
│   └── app/                                # Nuxt 4
├── grafana/                                # provisioning IaC
│   ├── provisioning/datasources/
│   ├── provisioning/dashboards/
│   └── dashboards/django-overview.json
├── prometheus/
│   └── prometheus.yml                      # scrape config
├── nginx/
│   └── nginx.conf                          # reverse proxy
├── scripts/
│   └── generate_vex.py                     # Trivy JSON → OpenVEX
├── docker-compose.dev.yml                  # stack hardened complète
└── README.md                               # ce fichier
```

---

## Workflow Data For Good (existant)

> Cette section conserve les conventions du projet upstream Data For Good Saison 14.

Lire les bonnes pratiques en détail : [Branches et commits — Workflow de contribution](https://outline.services.dataforgood.fr/doc/onboarding-dev-OFGKWOcxOn).

### Convention de branches

```
feat/scope/<description>      # nouvelle fonctionnalité
fix/scope/<description>       # correction de bug
docs/<sujet>                  # documentation
refactor/<sujet>              # refactoring
chore/<sujet>                 # maintenance
test/<sujet>                  # tests
```

### Convention de commits

Format `<type>: (<scope>:)? <description>`. Exemples :

```
feat: itn: ajoute le composant carte météo
fix: ecarts-normales: corrige l'affichage des températures négatives
docs: readme: documentation des livrables TP
test: parser: ajoute tests unitaires
chore: npm: met à jour les dépendances
```

### Pre-commit hooks

```bash
pip install pre-commit
pre-commit install
pre-commit run --all-files     # exécution manuelle
```

Outils utilisés :
- **Backend** : [Ruff](https://github.com/astral-sh/ruff) (lint + format), [nbstripout](https://github.com/kynan/nbstripout) (purge des notebooks)
- **Frontend** : ESLint + Prettier
- **Commun** : check merge conflicts, trim whitespace, fix end-of-line

### Pull Requests

- Une PR = une fonctionnalité ou un fix
- Au moins une review avant merge
- Merge en **Squash and merge** sur GitHub pour garder un historique linéaire
- Ne jamais pusher directement sur `main`
