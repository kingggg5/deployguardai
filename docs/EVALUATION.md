# Evaluation plan

> สถานะผลลัพธ์: **automated verification ของ synthetic MVP ผ่าน แต่ยังไม่มี real/public dataset benchmark** ตัวเลข test/build ด้านล่างเป็น engineering verification ไม่ใช่ accuracy claim

## Verified engineering results

| Check | ผลที่ยืนยันแล้ว |
|---|---|
| Backend | Regression suite is required in CI; the exact count is not an accuracy or coverage claim |
| Frontend | Regression suite and production build are required in CI |
| Angular | Production build ผ่าน |
| npm production dependencies | `npm audit --omit=dev` = 0 vulnerabilities |
| API | Investigation, workspace/RBAC, provider, webhook, telemetry และ operations flows มี integration tests |
| Deterministic engines | 6-dimension risk, BFS/cycle handling และ Top-3 RCA มี automated tests |
| Browser | Desktop/mobile flow รวม Operations service/event/incident/notification interactions ผ่าน |
| CORS | `127.0.0.1:4300` และ `localhost:4300` ผ่าน |
| Compose | `docker compose config` ผ่าน |
| Docker images | **ยังไม่ยืนยัน** เพราะ Docker Linux daemon ไม่พร้อม |

## Reproducible evidence-only benchmark

The repository includes the versioned input-and-label manifest
`scripts/evaluation/manifest-v2.json` and the runner
`scripts/evaluate_benchmarks.py`. The manifest cannot contain `prediction`,
`top_rank`, or precomputed quality metrics. The runner invokes
`app.engines.rank_hypotheses` for every episode and derives the ranking metrics
from the returned engine output. Run it with:

```powershell
python scripts/evaluate_benchmarks.py --output evaluation-results.json
```

The output records the dataset version and SHA-256, engine/scoring versions,
reference environment, per-episode rankings, failure slices, top-1/top-3
accuracy, MRR, confusion counts, citation coverage, and evidence-reference
integrity. `unsupported_claims_rate` is deliberately `null` until a human review
protocol measures it; reference integrity is not treated as a semantic
groundedness score. CI uploads the JSON artifact for review. This is a five-case
synthetic regression baseline, not a claim about public or production incident
accuracy.

ยังไม่มีผล PR-AUC, Top-K บน RCAEval, MRR บน real/public dataset, calibration หรือ production incident outcome ห้ามอนุมานผลเหล่านี้จาก automated engineering tests

## คำถามวิจัย

1. deterministic risk engine ให้ผลซ้ำและอธิบาย contribution ได้หรือไม่
2. dependency graph คำนวณ blast radius ตรงกับ topology ที่กำหนดหรือไม่
3. hypothesis ranker หา root cause ที่ label ไว้ใน Top 1/3 ได้เพียงใด
4. counter-evidence ทำให้ ranking ลดลงตามที่กำหนดหรือไม่
5. explanation อ้าง evidence ครบและไม่มี unsupported claim หรือไม่
6. ผู้ใช้ค้น evidence และบันทึก verdict ได้รวดเร็วและไม่เข้าใจ synthetic เป็น production หรือไม่

## Dataset inventory

| Dataset | ประเภท | การใช้ | สถานะ |
|---|---|---|---|
| DeployGuard embedded scenarios | Synthetic | Unit, integration, demo และ deterministic regression | Implemented: 3 scenarios + idempotent seed test |
| [RCAEval](https://github.com/phamquiluan/RCAEval) | Public benchmark | RCA Top-K/MRR และ baseline comparison | Candidate; ยังไม่ integrate |
| [RCAEval archived data](https://zenodo.org/records/14590730) | Public benchmark archive | Pinned evaluation snapshot/checksum | Candidate; ยังไม่ download |
| [OpenTelemetry Demo](https://opentelemetry.io/docs/demo/) | Public synthetic system | Controlled traces/metrics/logs และ fault scenarios | Later roadmap; event ledger ไม่ใช่ native OTLP receiver |
| Opt-in GitHub sandbox | Connected metadata | Webhook, repository sync และ Check Run reliability ไม่ใช่ accuracy claim | Integration implemented; credentialed sandbox run pending |
| Production incidents | Real/private | ไม่อยู่ใน MVP | ไม่มีข้อมูล |

RCAEval ระบุ 735 failure cases จาก 3 microservice systems และหลาย telemetry modalities แต่ต้องตรวจ license, version, checksum และ reproducibility ใน evaluation manifest ก่อนใช้งาน ห้ามนำตัวเลขจาก paper มาอ้างว่าเป็นผลของ DeployGuard

## Synthetic scenario specification

3 scenarios ที่ implement:

- `checkout-retry-storm`
- `catalog-cache-regression`
- `auth-key-rotation`

แต่ละ embedded spec มี:

- stable scenario ID
- change/deployment timestamp
- services และ dependency edges
- injected fault/symptom
- root-cause service และ indicator label
- expected affected services
- evidence และ counter-evidence
- expected next verification step
- deterministic RCA candidates/evidence

Manifest version and checksum are implemented for the current synthetic suite.
Random-seed provenance and public benchmark integration remain evaluation-
hardening work.

Fault catalog ที่เสนอ:

- CPU หรือ memory saturation
- pod/process crash
- downstream latency/timeout
- packet loss
- dependency 5xx
- database connection-pool exhaustion
- config regression
- retry amplification
- schema incompatibility
- feature-flag regression

ข้อมูลเหล่านี้ต้องแสดง `data_mode: "synthetic"` เสมอ

## Split และ leakage policy

- unit/contract fixtures แยกจาก benchmark scenarios
- train/tune/test แยกตาม scenario family, service และเวลา
- ห้ามสุ่ม event จาก incident เดียวกันข้าม split
- feature snapshot ใช้ข้อมูลไม่เกิน decision timestamp
- root-cause label และ recovery event ห้ามปรากฏใน risk features
- prompt/explanation evaluation ใช้ frozen evidence bundle
- test set เปลี่ยนได้เฉพาะเมื่อออก dataset version ใหม่

## Baselines

### Risk

1. constant/no-skill baseline
2. rule score จาก change size, previous failures และ observability
3. logistic regression เมื่อมี labeled sample เพียงพอ
4. tree-based model เป็น later comparison

MVP deterministic weighted score ต้องแข่งกับ baseline ที่ง่ายกว่า ไม่ใช่ใช้ความซับซ้อนเป็นข้อพิสูจน์คุณภาพ

### Blast radius

1. changed services only
2. unweighted breadth-first traversal
3. confidence-weighted bounded traversal

### RCA

1. random candidate order
2. anomaly magnitude only
3. graph distance only
4. anomaly-weighted graph rank
5. reproducible RCAEval baseline ที่เลือกและ pin version

### Explanation

1. deterministic template
2. bounded LLM summary เฉพาะเมื่อ evidence contract ผ่าน

ถ้า LLM ไม่ดีกว่า template ใน groundedness/usability อย่างมีนัยสำคัญ ให้คง template เป็น default

## Metrics

### Determinism and contract

- repeatability rate
- API schema conformance
- evidence-reference integrity
- seed/checksum reproducibility

### Risk

- monotonic rule tests
- PR-AUC เมื่อมี natural-prevalence labels
- ROC-AUC เป็น secondary
- Brier score
- expected calibration error
- recall ใน top risk bucket

Accuracy ไม่เหมาะกับ class imbalance และห้ามใช้เพียง metric เดียว

### Graph

- node/edge precision และ recall เทียบ expected topology
- impacted-service precision/recall
- cycle/maximum-hop correctness
- 3-hop traversal p50/p95

### RCA

- Top@1, Top@3, Top@5
- Mean Reciprocal Rank
- service-level และ indicator-level score
- counter-evidence sensitivity
- time-to-result

### Evidence and language

- evidence citation coverage
- unsupported-claim rate
- contradiction acknowledgement rate
- next-step actionability rubric
- reviewer agreement
- latency และ token cost เมื่อมี LLM

### UX/accessibility

- time to locate top hypothesis evidence
- task completion rate
- accidental interpretation of synthetic as production
- keyboard-only completion
- WCAG 2.2 AA automated/manual findings

## Acceptance gates

| Gate | Target ก่อน release | สถานะปัจจุบัน |
|---|---:|---|
| Same input ให้ risk เดิมและ safer input ให้ score ต่ำลง | Automated engine test | ✅ ผ่าน |
| Seed ซ้ำไม่เพิ่ม duplicate records | Automated seed test | ✅ ผ่าน |
| 10 API routes และ domain/validation/CORS flows | Automated API tests | ✅ ผ่าน |
| BFS decay และ cycle handling | Automated engine test | ✅ ผ่าน |
| RCA จำกัด Top 3 และลงโทษ counter-evidence | Automated engine test | ✅ ผ่าน |
| Feedback persist และอัปเดต hypothesis status | API + frontend tests | ✅ ผ่าน |
| Expected synthetic graph nodes/edges ทั้งชุด | 100% | ยังไม่มี aggregate benchmark artifact |
| Root cause อยู่ Top 3 ใน synthetic v2 suite | ≥ 90% | 100% across 5 synthetic cases; Top-1 80%, MRR 0.9 |
| Critical unsupported claims | 0 | Not measured |
| Explanation evidence-reference coverage | ≥ 95% | 100% on synthetic v2; reference integrity 100% |
| Cross-mode synthetic/connected contamination | 0 | Models and UI label data mode; credentialed sandbox evaluation pending |
| Desktop/mobile primary browser flow | Manual/browser verification | ✅ ผ่าน |
| 3-hop graph query บน reference dataset | p95 ≤ 200 ms | Not measured |
| Docker Compose definition | Parse/validation | ✅ ผ่าน |
| Docker image build/healthchecks | Successful build/run | ยังไม่ตรวจ: Linux daemon unavailable |

The engine-backed synthetic runner now reports all five maintained RCA cases and
keeps one ambiguous challenge case as a visible Top-1 failure. This verifies
regression behavior on authored fixtures only; it does not establish public
benchmark accuracy, calibration, or production incident performance.

สำหรับ public/OOD benchmark ให้รายงานค่าจริงพร้อม bootstrap confidence interval และ failure slices โดยไม่บังคับให้ผ่านตัวเลข synthetic เดียวกัน

## Evaluation protocol

1. pin code commit; เพิ่ม dataset/scenario/scoring versions ก่อน benchmark แรก
2. เริ่มจาก clean database
3. รัน contract/determinism tests
4. รัน synthetic core และ held-out suites
5. รัน public benchmark adapter ถ้ามี
6. สร้าง machine-readable JSON result
7. สร้าง report ที่มี sample counts, prevalence, confidence interval และ failures
8. ให้ reviewer ตรวจ unsupported claim แบบ blind sample
9. archive artifact โดยไม่แก้ผลย้อนหลัง

## Result-report template

```text
Commit:
Dataset/scenario version:
Evaluation date:
Environment:
Sample count:
Failure prevalence:
Baseline:
DeployGuard configuration:
Metrics with confidence intervals:
Known failure slices:
Unsupported claims:
Reproduction command:
```

จนกว่าจะมี artifact ตาม template นี้ README และ UI ต้องไม่แสดง accuracy, savings, incident-reduction หรือ benchmark claims
