# TP — CI/CD, Monitoring & Docker Hardened Images

Trace étape par étape du travail réalisé pour respecter les trois pages du sujet, dans l'ordre du PDF.

## Récapitulatif des livrables

| Livrable demandé | Statut | Où ? |
|---|---|---|
| Functional CI/CD pipeline | ✅ | [.github/workflows/ci-tp.yml](.github/workflows/ci-tp.yml) |
| Badge CI dans README | ✅ | [README.md ligne 3](README.md#L3) |
| Docker image | ✅ | `ghcr.io/samidehil16/14_valorisationdonneemeteo-{backend,frontend}:latest` |
| Test report | ✅ | CI artifact `backend-test-report` (JUnit XML + coverage XML) |
| Scan code report | ✅ | [reports/scorecard.json](reports/scorecard.json) + artifact `scorecard-report` |
| Trivy report | ✅ | CI artifacts `security-reports` (txt + json) et `docker-image-reports` |
| VEX file | ⚠️ squelette OpenVEX | CI artifact `security-reports/vex.openvex.json` |
| Pipeline testing (break/fix) | ✅ | branche `tp/pipeline-test-demo` (runs ci-dessous) |
| Prometheus UI avec metrics | ✅ | service `prometheus` dans [docker-compose.dev.yml](docker-compose.dev.yml) |
| Grafana dashboard | ✅ | service `grafana` + provisioning [grafana/](grafana/) |
| DHI Hardened Images | ✅ | [backend/Dockerfile](backend/Dockerfile), [frontend/Dockerfile](frontend/Dockerfile) |

---

## Page 1 — Basic Pipeline Creation (40 min)

### 1. Création de `.github/workflows/ci-tp.yml`

Fichier : [.github/workflows/ci-tp.yml](.github/workflows/ci-tp.yml)

### 2. Stages présents

| Stage demandé | Job(s) | Détails |
|---|---|---|
| Install dependencies | `backend`, `frontend` | `uv sync --extra dev` (Python) / `npm ci` (Node) |
| Run tests | `backend`, `frontend` | pytest (avec coverage + JUnit XML) / vitest |
| Run linter | `backend`, `frontend` | `ruff check` / `npm run lint` |
| Run security scan | `security-scan` | Trivy fs (table + JSON) + SBOM CycloneDX + OpenVEX + OSSF Scorecard (SARIF + JSON) |
| Build Docker image | `build-and-push` | `docker/build-push-action@v5` sur backend/ et frontend/ |
| Push to registry (main only) | `build-and-push` | `if: github.ref == 'refs/heads/main'` → ghcr.io |

Extrait du gating « main only » :

```yaml
build-and-push:
  runs-on: ubuntu-24.04
  needs: [security-scan]
  if: github.ref == 'refs/heads/main'
```

---

## Page 1 — Pipeline Testing (15 min)

Demonstration faite sur une branche dédiée pour ne pas polluer `main` : **`tp/pipeline-test-demo`**.

### Étape 1 — Casser un test intentionnellement

- **Fichier modifié** : [backend/weather/tests/unit/test_date_range.py](backend/weather/tests/unit/test_date_range.py)
- **Commit** : `471ba3a` — *test: pipeline-testing: intentionally break a test for TP demo*
- **CI run** : [#24990510013](https://github.com/samidehil16/14_ValorisationDonneeMeteo/actions/runs/24990510013) — ❌ **FAIL en 41s**
- **Étape qui a catch l'erreur** : `backend → Run tests`
- **Sortie pytest** :
  ```
  FAILED weather/tests/unit/test_date_range.py::test_iter_days_intersecting_inclusive_single_day
  assert [datetime.date(2024, 1, 1)] == [datetime.date(2024, 1, 2)]
  At index 0 diff: datetime.date(2024, 1, 1) != datetime.date(2024, 1, 2)
  ```
- **Conséquence** : tous les jobs en aval (`security-scan`, `scorecard`, `build-and-push`) ont été skip — la CI a fait son travail de portail qualité.

### Étape 2 — Fixer le test

- **Commit** : `e5f4c1e` — *test: pipeline-testing: revert intentional break (CI verified failure)*
- **Run avec test fixé** : [#24990585022](https://github.com/samidehil16/14_ValorisationDonneeMeteo/actions/runs/24990585022) — ✅ tests backend (39s) et frontend (29s) **passés**, security-scan ✅. Le job `scorecard` a échoué sur cette branche pour une raison externe au test : l'action `ossf/scorecard-action` refuse les branches autres que `main` (« only the default branch is supported »).
- **Correctif CI** : commit `6689ce5` sur `main` ajoute `if: github.ref == 'refs/heads/main'` au job `scorecard` pour qu'il ne tourne que sur la branche par défaut.
- **Run final tout vert** (après merge du correctif sur la branche demo) : [#24990866309](https://github.com/samidehil16/14_ValorisationDonneeMeteo/actions/runs/24990866309) — ✅ **SUCCESS**

### Étape 3 — Badge CI dans le README

```markdown
![CI/CD Pipeline](https://github.com/samidehil16/14_ValorisationDonneeMeteo/actions/workflows/ci-tp.yml/badge.svg)
```

Visible en haut de [README.md](README.md).

---

## Page 2 — Basic metrics pull architecture

### 1. Lancer le docker-compose

```bash
docker compose -f docker-compose.dev.yml up -d
```

Stack démarrée : `timescaledb`, `backend`, `frontend`, `nginx`, `prometheus`, `grafana`.

### 2. Prometheus

- **Image** : `prom/prometheus:v3.3.0`
- **UI** : http://localhost:9090
- **Config** : [prometheus/prometheus.yml](prometheus/prometheus.yml)
- **Targets configurés** :
  - `prometheus` (auto-scrape sur `localhost:9090`)
  - `backend` (sur `backend:8000/metrics`)

### 3. Endpoint `/metrics` exposé

Côté Django (backend) :
- Package `django-prometheus` ajouté à `INSTALLED_APPS`
- Middleware `BeforeMiddleware` / `AfterMiddleware` ajoutés en première et dernière position de `MIDDLEWARE`
- Route `path("", include("django_prometheus.urls"))` dans [backend/config/urls.py](backend/config/urls.py)

Vérification : `curl http://localhost:8000/metrics` retourne les métriques au format Prometheus exposition.

### 4. Grafana — installation et provisioning

- **Image** : `grafana/grafana:11.3.1`
- **UI** : http://localhost:3001 (login `admin` / `admin`)
- **Port mapping** : `3001:3000` côté hôte (3000 réservé au frontend Nuxt en dev)

#### Datasource auto-provisionnée

[grafana/provisioning/datasources/prometheus.yml](grafana/provisioning/datasources/prometheus.yml) — Grafana lit ce fichier au démarrage et crée la datasource `Prometheus` (uid=`prometheus`) pointant vers `http://prometheus:9090` sur le réseau Docker `app_net`.

#### Dashboard auto-provisionné

- Provider config : [grafana/provisioning/dashboards/default.yml](grafana/provisioning/dashboards/default.yml)
- Dashboard JSON : [grafana/dashboards/django-overview.json](grafana/dashboards/django-overview.json) — **Django Backend Overview**, 4 panels :
  1. Request rate by method (`rate(django_http_requests_total_by_method_total[5m])`)
  2. Responses by status code (`rate(django_http_responses_total_by_status_total[5m])`)
  3. Request latency p50 / p95 / p99 (`histogram_quantile` sur `django_http_requests_latency_including_middlewares_seconds_bucket`)
  4. Backend memory RSS (`process_resident_memory_bytes`)

Tout passe par fichiers : `docker compose down -v` n'efface jamais la conf.

---

## Page 3 — Docker Hardened Images

### 1. Bases DHI utilisées

| Service | Build stage (avec shell + toolchain) | Runtime stage (distroless) |
|---|---|---|
| Backend Python | `dhi.io/python:3.13-debian13-dev` | `dhi.io/python:3.13-debian13` |
| Frontend Node  | `dhi.io/node:24-debian13-dev`     | `dhi.io/node:24-debian13`     |

Voir [backend/Dockerfile](backend/Dockerfile) et [frontend/Dockerfile](frontend/Dockerfile).

### 2. Production-readiness

- **Multi-stage** : la toolchain (uv, npm) reste dans le `builder`. L'image finale ne contient que l'app + ses deps runtime.
- **Pas de shell, pas de package manager** dans l'image runtime (DHI distroless) → réduction massive de la surface d'attaque.
- **Run as nonroot** : les images DHI distroless tournent par défaut en utilisateur `nonroot`.
- **Cache mounts BuildKit** sur `~/.cache/uv` et `~/.npm` pour accélérer les rebuilds.
- **`.dockerignore`** ([backend/.dockerignore](backend/.dockerignore), [frontend/.dockerignore](frontend/.dockerignore)) pour minimiser le build context.

### 3. Authentification dans la CI

Les bases DHI nécessitent un login Docker Hub. Step ajouté dans le job `build-and-push` :

```yaml
- name: Login to dhi.io (Docker Hardened Images)
  uses: docker/login-action@v3
  with:
    registry: dhi.io
    username: ${{ secrets.DHI_USERNAME }}
    password: ${{ secrets.DHI_TOKEN }}
```

Secrets configurés dans : *GitHub → Settings → Secrets → Actions* :
- `DHI_USERNAME` — login Docker Hub
- `DHI_TOKEN` — Docker Hub Personal Access Token

### 4. Compose hardened (bonus cohérent avec DHI)

Tous les services dans [docker-compose.dev.yml](docker-compose.dev.yml) ont :
- `security_opt: [no-new-privileges:true]`
- `cap_drop: [ALL]`
- `read_only: true` (avec `tmpfs` ciblé pour les emplacements qui doivent être writable)
- Limites mémoire (`deploy.resources.limits.memory`)
- nginx en `nginxinc/nginx-unprivileged` (port 8080 dans le conteneur, exposé en 80 côté hôte)

---

## Reproductibilité

```bash
# 1. (CI seulement) login DHI — secrets GitHub déjà configurés
# 1.bis (local) login DHI avec ton compte Docker Hub :
docker login dhi.io

# 2. Lancer la stack complète
docker compose -f docker-compose.dev.yml up -d

# 3. Vérifier les services
curl -fsS http://localhost:8000/metrics | head            # /metrics exposé
open http://localhost:9090                                # Prometheus UI
open http://localhost:3001                                # Grafana (admin/admin)

# 4. Lancer les tests en local (équivalent CI backend + frontend)
cd backend && uv sync --extra dev && uv run pytest
cd frontend && npm ci --legacy-peer-deps && npm run test:ci
```

## Récupérer les artifacts de CI

```bash
# Dernier run CI/CD Pipeline sur main
RUN_ID=$(gh run list --repo samidehil16/14_ValorisationDonneeMeteo \
           --workflow=ci-tp.yml --branch main --status success \
           --limit 1 --json databaseId --jq '.[0].databaseId')

# Test report
gh run download $RUN_ID --repo samidehil16/14_ValorisationDonneeMeteo --name backend-test-report

# Trivy + SBOM + VEX
gh run download $RUN_ID --repo samidehil16/14_ValorisationDonneeMeteo --name security-reports

# Scorecard (SARIF + JSON)
gh run download $RUN_ID --repo samidehil16/14_ValorisationDonneeMeteo --name scorecard-report

# Trivy scans des images Docker pushées
gh run download $RUN_ID --repo samidehil16/14_ValorisationDonneeMeteo --name docker-image-reports
```
