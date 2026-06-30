# Sentinel Platform

Real-time Network Security Analytics Platform that ingests live Palo Alto firewall syslog, performs behavioral risk scoring, and automatically blocks high-risk IPs through closed-loop remediation.

## Architecture

```
PA-3220 (TAP) → syslog (UDP 514) → Vector → Redpanda → ClickHouse → Risk Engine → Grafana
                                                                          ↓
                                                                    /blocklist (EDL)
                                                                          ↓
                                                                    Palo Alto → BLOCK
```

## How It Works

1. **Ingest** — Vector receives ~500 syslog events/minute from a production Palo Alto PA-3220 via UDP 514, parses the non-standard CSV format using custom VRL transforms
2. **Stream** — Redpanda (Kafka-compatible) buffers parsed events into `firewall.raw` and `firewall.parsed` topics
3. **Store** — ClickHouse (columnar DB) stores 200K+ events in `sentinel.firewall_events` for fast analytical queries
4. **Score** — Risk Engine (FastAPI) calculates per-IP risk scores using behavioral signals — not traditional IPS signatures, which aren't available in TAP mode:
   - Suspicious port access (445, 139, 135, 3389, 23) with weighted scoring
   - Port scan detection (20+ unique ports → +30 points)
   - Unknown application ratio (>30% → +15 points)
   - Risk levels: **OK** (<40) · **WARNING** (40-69) · **ALERT** (≥70)
5. **Visualize** — Grafana dashboards display real-time traffic patterns, risk scores, and alert timelines
6. **Remediate** — IPs scoring ≥70 are exposed via `/blocklist` endpoint in Palo Alto EDL format → Dynamic Address Group → Security Policy → automatic block

## Tech Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| Ingestion | Vector | Syslog receiver + VRL parsing |
| Streaming | Redpanda | Event buffering (Kafka-compatible) |
| Storage | ClickHouse (Altinity Operator) | Columnar analytics DB |
| Scoring | FastAPI (Python) | Behavioral risk engine |
| Visualization | Grafana | Real-time dashboards |
| Firewall | Palo Alto PA-3220 | Source + enforcement via EDL |
| Orchestration | k3d (Kubernetes) | 1 server + 2 agent nodes |
| GitOps | ArgoCD | 7 apps, automated sync + self-heal |
| CI/CD | GitHub Actions | Security scanning + image signing |
| Policy | Kyverno | Image verification + security policies |

## GitOps — ArgoCD

All 7 applications are managed through ArgoCD with automated sync and self-healing:

| Application | Source | Namespace |
|-------------|--------|-----------|
| risk-engine | Git manifest | sentinel |
| clickhouse | Git manifest | data |
| redpanda | Helm (multi-source) | redpanda |
| vector | Helm (multi-source) | vector |
| grafana | Helm (multi-source) | monitoring |
| grafana-dashboards | Git manifest | monitoring |
| kyverno-policies | Git manifest | kyverno |

## DevSecOps Pipeline

GitHub Actions CI/CD runs on every push to `risk-engine/` or manual dispatch:

```
gitleaks (secret scan) → bandit (Python SAST) → docker build → trivy (CVE scan) → cosign sign (keyless) → push ghcr.io
```

- **Secret scanning** — Gitleaks detected a real credential committed to the repo early in development, which was migrated to Kubernetes secrets
- **Image signing** — Cosign keyless signing via Sigstore (Fulcio + Rekor transparency log), verified by GitHub Actions OIDC identity
- **Image verification** — Kyverno `verify-image-signature` policy validates cosign signatures for every pod in the `sentinel` namespace

## Kyverno Policies

Four Kyverno controllers enforce security policies in Audit mode:

| Policy | Purpose |
|--------|---------|
| `disallow-latest-tag` | Prevents `:latest` tag usage |
| `require-non-root` | Enforces non-root container execution |
| `require-resources` | Mandates CPU/memory resource limits |
| `verify-image-signature` | Validates cosign keyless signatures (sentinel namespace) |

> **Production recommendation:** Set `validationFailureAction: Enforce` to block non-compliant workloads.

## Project Structure

```
sentinel-platform/
├── .github/workflows/risk-engine-ci.yaml    # CI/CD pipeline
├── argocd/apps/                             # ArgoCD application manifests
│   ├── clickhouse.yaml
│   ├── redpanda.yaml
│   ├── vector.yaml
│   ├── grafana.yaml
│   ├── grafana-dashboards.yaml
│   ├── risk-engine.yaml
│   └── kyverno-policies.yaml
├── platform/
│   ├── clickhouse/clickhouse.yaml           # ClickHouse operator manifest
│   ├── grafana/                             # Grafana Helm values + dashboard ConfigMap
│   └── kyverno/                             # Kyverno policies (verify-image, security)
├── risk-engine/
│   ├── main.py                              # FastAPI risk scoring engine
│   ├── Dockerfile
│   ├── k8s-deploy.yaml                      # Deployment + Service manifest
│   └── requirements.txt
├── dashboards/firewall-overview.json        # Grafana dashboard definition
├── local/k3d/                               # k3d cluster config + local values
├── forward.sh                               # Port-forward helper script
└── stop-forward.sh
```

## Local Setup

### Prerequisites

- Docker (with cgroup v2 enabled)
- k3d
- kubectl
- Helm
- cosign

### Cluster

```bash
# Create k3d cluster (config includes NodePort mapping for syslog UDP 514)
k3d cluster create sentinel --config local/k3d/k3d-config.yaml

# Label and taint agent nodes for data workloads
kubectl label node k3d-sentinel-agent-{0,1} workload=data
kubectl taint node k3d-sentinel-agent-{0,1} workload=data:NoSchedule
```

### Access

```bash
# Start port-forwards (Grafana:3000, ArgoCD:8090, Risk Engine:8000, Redpanda Console:8081)
./forward.sh

# Stop all port-forwards
./stop-forward.sh
```

| Service | URL | Credentials |
|---------|-----|-------------|
| Grafana | http://localhost:3000 | admin / (see `grafana-admin` secret) |
| ArgoCD | http://localhost:8090 | admin / (see `argocd-initial-admin-secret`) |
| Risk Engine | http://localhost:8000/health | — |

### Risk Engine API

```bash
# Health check
curl http://localhost:8000/health

# Get risk assessment for all source IPs
curl http://localhost:8000/risk

# Get active alerts (score ≥ 70)
curl http://localhost:8000/alerts

# EDL blocklist (Palo Alto-compatible plain text)
curl http://localhost:8000/blocklist
```

## Key Engineering Decisions

**Behavioral scoring over signature-based detection** — The PA-3220 runs in TAP mode, meaning no inline traffic inspection and no DENY events. Traditional IPS signature matching doesn't apply. The risk engine uses behavioral signals (suspicious port access patterns, port scanning, unknown application ratios) to identify threats regardless of deployment mode.

**Unified secret management** — Early in development, a password mismatch across ClickHouse, Vector, Risk Engine, and Grafana caused cascading "Forbidden" errors. All components now reference a single Kubernetes secret per namespace, eliminating drift.

**VRL custom parsing** — Palo Alto syslog doesn't follow standard CSV conventions. Vector's built-in CSV parser couldn't handle it, so the pipeline uses raw UDP socket ingestion with manual VRL field extraction using `split` and `index`.

**Cosign keyless signing** — No private keys to manage. Image signatures are tied to the GitHub Actions OIDC identity and recorded in the Sigstore transparency log (Rekor).

## Lessons Learned

1. **cgroup v2 migration** — k3d failed silently on cgroup v1. Root cause analysis led to GRUB configuration change and reboot.
2. **GitOps secret drift** — A placeholder password propagated through ArgoCD sync, breaking 4 components simultaneously. Taught the importance of treating secrets as first-class infrastructure.
3. **Gitleaks catching real credentials** — The DevSecOps pipeline proved its value by detecting an actual committed password, not just a theoretical risk.
4. **Port-forward lifecycle management** — CLOSE_WAIT zombie processes accumulated over time, requiring a dedicated cleanup script.

## Roadmap

- [ ] Multi-environment setup (dev/staging/prod)
- [ ] Enforce mode for Kyverno policies
- [ ] Prometheus metrics + alerting
- [ ] Horizontal scaling for Risk Engine

## Author

**Yamen Mehdizade** — Network Security Engineer | PCNSE (3x) · PCNSC · CCNP · CCNA

Open to senior Cloud/Network Security Engineering roles in Austria and Switzerland.

[LinkedIn](https://linkedin.com/in/yamenmehdizade) · [GitHub](https://github.com/yamenmehdizade)
