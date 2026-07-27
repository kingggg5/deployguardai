# คู่มือผู้ใช้และเดโม DeployGuard AI

> สถานะ: **คู่มือ runnable synthetic MVP** — Dashboard รันที่ `http://127.0.0.1:4300` และ FastAPI ที่ `http://127.0.0.1:8100` ขั้นตอน desktop/mobile, API/CORS และ feedback flow ผ่านการตรวจแล้ว ข้อมูลทั้งหมดเป็น synthetic

## DeployGuard ช่วยตอบอะไร

DeployGuard ไม่ได้ตอบว่า “ควร deploy หรือไม่” แบบอัตโนมัติ แต่ช่วยให้ผู้ตรวจ change และผู้สืบสวน incident เห็น:

- คะแนนความเสี่ยงมาจากข้อมูลใด
- service ใดอยู่ใน blast radius
- เหตุการณ์เกิดก่อนและหลัง deploy อย่างไร
- hypothesis ใดมี evidence และ counter-evidence อะไร
- ควรตรวจสอบอะไรต่อ
- มนุษย์มี verdict อย่างไร

## คำสำคัญ

| คำ | ความหมาย |
|---|---|
| Risk dimension | ปัจจัยย่อยที่มีน้ำหนักและเหตุผลชัดเจน |
| Blast radius | service/dependency ที่อาจได้รับผลกระทบตาม graph |
| Evidence | ข้อมูลที่ตรวจสอบย้อนกลับได้ เช่น metric, trace หรือ event |
| Counter-evidence | ข้อมูลที่ลดความน่าเชื่อถือของ hypothesis |
| Hypothesis | สาเหตุที่เป็นไปได้ ไม่ใช่ข้อสรุปอัตโนมัติ |
| Verify next | ขั้นตอนถัดไปเพื่อยืนยันหรือหักล้าง |
| Human verdict | confirmed, rejected หรือ partial cause |
| Synthetic demo | ข้อมูลจำลองแบบ reproducible ไม่ใช่ production |

## เริ่มระบบบน Windows

Prerequisites:

- Python 3.12+
- Node.js และ npm
- PowerShell

จาก project root:

```powershell
.\scripts\run-dev.ps1
```

สคริปต์จะ:

1. สร้าง `backend\.venv` หากยังไม่มี
2. ติดตั้ง backend requirements
3. ติดตั้ง frontend packages หากยังไม่มี `node_modules`
4. เปิด FastAPI ที่ port `8100`
5. เปิด Angular ที่ port `4300`
6. เขียน PID และ logs ไว้ใน `.runtime`

เปิด:

- Dashboard: <http://127.0.0.1:4300>
- API docs: <http://127.0.0.1:8100/docs>
- Health: <http://127.0.0.1:8100/api/v1/health>

หาก dependencies พร้อมแล้ว:

```powershell
.\scripts\run-dev.ps1 -SkipInstall
```

หยุดระบบ:

```powershell
.\scripts\stop-dev.ps1
```

## ก่อนเริ่มเดโม

ตรวจรายการต่อไปนี้:

- หน้า Overview แสดง `Synthetic demo`
- API response มี `data_mode: "synthetic"`
- มี 3 scenarios: Checkout retry storm, Catalog cache regression และ Guarded auth key rotation
- `/api/v1/health` ตอบว่า application และ database พร้อม
- ไม่มี GitHub token, cluster credential หรือ production telemetry ที่จำเป็นต่อเดโม

หากป้าย synthetic หาย ให้หยุดเดโมและถือเป็น content-integrity defect

## Demo walkthrough

### 1. เลือก scenario

เปิด Change rail แล้วเลือก scenario ที่ต้องการ Scenario ควรระบุ:

- scenario ID และ version
- changed service
- injected symptom/fault
- expected evidence
- root-cause label สำหรับ evaluation

ผลที่คาดหวัง: Overview เปลี่ยนแบบ deterministic และยังแสดง `Synthetic demo`

API contract:

```http
GET /api/v1/scenarios
POST /api/v1/scenarios/{scenario_id}/activate
```

Endpoint ทั้งสอง implement แล้วและครอบคลุมใน backend/frontend tests

### 2. อ่าน Change queue

เลือก change ที่กำลังตรวจ แล้วอ่าน:

- repository, branch และ commit SHA
- files/lines changed
- changed services
- deployment status/environment
- flags เช่น config change หรือ retry policy

อย่าตีความจำนวนบรรทัดเพียงตัวเดียวว่าเสี่ยง คะแนนรวมต้องเปิดดู contribution ทุก dimension

### 3. ตรวจ Risk ledger

Risk ledger แสดงคะแนน 0–100, level, data quality และ dimensions

สำหรับแต่ละ dimension ให้ถาม:

1. weight ถูกกำหนดไว้ชัดเจนหรือไม่
2. reason สอดคล้องกับข้อมูลหรือไม่
3. evidence ID เปิดดูได้หรือไม่
4. data quality ต่ำเพราะข้อมูลใดหาย
5. recommendation เป็นคำแนะนำให้ตรวจ ไม่ใช่คำสั่ง deploy

คะแนนสูงแต่ data quality ต่ำควรแสดง uncertainty เด่นกว่าความมั่นใจ

### 4. ตรวจ Blast radius

Topology เป็น artifact หลักของหน้าจอ:

- node แสดง service/database/queue/external dependency
- hop distance แสดงระยะจาก changed service
- impact score แสดงลำดับตรวจ ไม่ใช่ความแน่นอนของ failure
- edge แสดง relation และ confidence

ใช้ keyboard เลือก service ได้ และต้องมี text summary สำหรับผู้ใช้ screen reader

### 5. เปิด Evidence X-ray

สลับ `Evidence X-ray` เพื่อเปลี่ยน annotation จาก operational state เป็น evidence และ score contribution โดยตำแหน่ง graph ต้องไม่กระโดด

ตรวจว่า:

- node/edge ทุกตัวที่ถูก highlight มี evidence ID
- evidence มี source, timestamp, quality และ service ID
- สีไม่ใช่สัญญาณเพียงอย่างเดียว

### 6. Replay incident

Incident recorder เรียง deploy, symptom, alert, mitigation, recovery และ feedback ตาม UTC timestamp

เมื่อกด replay:

- time cursor เคลื่อนตามลำดับ
- affected edge สว่างตาม causal order ที่ scenario กำหนด
- reduced-motion mode ต้องข้าม animation และแสดง final state ทันที

การอยู่ใกล้กันทางเวลาเป็น correlation ไม่ใช่ causation โดยอัตโนมัติ

### 7. เปรียบเทียบ hypotheses

แต่ละแถวต้องมี:

- rank และ confidence
- cause service/cause
- evidence IDs
- counter-evidence IDs
- reasoning
- next verification step
- human verdict status

เริ่มจาก Top 1 แต่ต้องอ่าน counter-evidence และ Top 2–3 ก่อนบันทึก verdict

### 8. บันทึก human verdict

เลือก:

- `confirmed` — หลักฐานยืนยัน hypothesis
- `rejected` — หลักฐานหักล้าง
- `partial` — เป็นหนึ่งในหลายสาเหตุ

เพิ่ม note ที่อ้าง evidence หรือการตรวจสอบจริง Feedback ต้อง append ใหม่และไม่เปลี่ยน evidence/rank ย้อนหลัง

API shape ตาม contract:

```json
{
  "hypothesis_id": "hyp-payment-timeout",
  "verdict": "confirmed",
  "note": "Trace replay confirmed timeout before the retry fan-out."
}
```

### 9. สรุปเดโม

เดโมที่สมบูรณ์ควรสรุปได้ภายใน 6–8 นาที:

1. change ใดถูกวิเคราะห์
2. dimension ใดเพิ่มความเสี่ยง
3. blast radius ไปถึง service ใด
4. incident timeline เปลี่ยนหลัง deploy อย่างไร
5. hypothesis ใดมีหลักฐานมากที่สุดและมีข้อโต้แย้งอะไร
6. มนุษย์ตรวจและบันทึก verdict อย่างไร

## Analyze-change API example

```json
{
  "title": "Tighten checkout timeout and retry policy",
  "repository": "acme/checkout-platform",
  "author": "narin",
  "files_changed": 11,
  "lines_added": 286,
  "lines_deleted": 74,
  "changed_services": ["checkout-api", "payment-adapter"],
  "flags": ["config-change", "retry-policy"],
  "test_coverage": 0.72,
  "rollback_ready": true,
  "observability_score": 0.84,
  "previous_failures": 1
}
```

ส่ง payload ไปยัง `POST http://127.0.0.1:8100/api/v1/changes/analyze` ระบบจะคำนวณ risk 6 dimensions และ BFS blast radius แล้ว persist ผลลงฐานข้อมูล ตัวอย่างนี้เป็น synthetic input ไม่ใช่ลูกค้าหรือเหตุการณ์จริง

## Troubleshooting

### เปิดระบบแล้วเข้า UI/API ไม่ได้

- รันจาก project root ด้วย `.\scripts\run-dev.ps1`
- ตรวจ `.runtime\backend.stderr.log` และ `.runtime\frontend.stderr.log`
- ตรวจ process จาก PID ใน `.runtime\backend.pid` และ `.runtime\frontend.pid`
- ทดสอบ health โดยตรงที่ `http://127.0.0.1:8100/api/v1/health`
- ใช้ `.\scripts\stop-dev.ps1` ก่อนเริ่มใหม่หากมี process เก่าค้าง

### Port 4300 หรือ 8100 ถูกใช้งาน

```powershell
Get-NetTCPConnection -LocalPort 4300,8100 -ErrorAction SilentlyContinue
```

หยุด DeployGuard instance เดิมด้วย `.\scripts\stop-dev.ps1` หรือหยุด process ที่ครอบครอง port ก่อนเริ่มใหม่ สคริปต์ปัจจุบันใช้ port คงที่

### `/api/v1/health` เชื่อมต่อไม่ได้

- ตรวจ backend process และ base URL
- ตรวจว่า path มี `/api/v1`
- ตรวจ `database: "ready"` ใน health response
- ตรวจ `backend\deployguard.db` และ backend error log

### UI ว่างแต่ API ทำงาน

- ตรวจ browser network และ error envelope
- ตรวจ response ตรง API contract
- ตรวจ CORS/base URL configuration
- empty state ต้องบอก recovery action ห้ามแสดงพื้นที่ว่างเฉย ๆ

### Scenario ให้ผลไม่เหมือนเดิม

- ยืนยันว่าเลือก scenario ID เดิม
- หยุดระบบแล้วสำรองฐานข้อมูลก่อน reset:

```powershell
.\scripts\stop-dev.ps1
Move-Item .\backend\deployguard.db .\backend\deployguard.db.bak
.\scripts\run-dev.ps1 -SkipInstall
```

- ตรวจว่ามีการแก้ scoring weights หรือ embedded seed specs หรือไม่
- ถือเป็น deterministic-regression bug

### คะแนนดูมั่นใจแต่ evidence หาย

ถือเป็น release blocker คะแนนทุก dimension ต้องมี evidence ID และ data-quality marker

### Graph วนหรือช้า

- ตรวจ maximum hop
- ตรวจ visited-node/cycle protection
- ตรวจ index ของ source/target/type
- ใช้ textual fallback ระหว่างแก้ graph rendering

### Feedback หายหลัง refresh

- ตรวจว่า feedback endpoint สำเร็จ
- ตรวจ database transaction
- ตรวจว่า refresh ยังใช้ SQLite file เดิม
- feedback ถูก persist ใน `incident_feedback` ไม่ใช่ UI-only state

### CORS error

ค่า default รองรับ:

- `http://127.0.0.1:4300`
- `http://localhost:4300`

หากเปลี่ยน frontend origin ให้กำหนด `CORS_ORIGINS` ก่อนเริ่ม backend เช่น:

```powershell
$env:CORS_ORIGINS = 'http://127.0.0.1:4400,http://localhost:4400'
.\scripts\run-dev.ps1 -SkipInstall
```

### Docker Compose

`docker compose config` ผ่านแล้ว แต่ image build ยังไม่ถูกยืนยันใน environment ล่าสุดเพราะ Docker Linux daemon ไม่พร้อม หากต้องการทดสอบ container path ให้เปิด Linux containers ก่อน แล้วรัน:

```powershell
docker compose config
docker compose build
docker compose up
```

อย่ารายงานว่า Docker deployment ผ่านจน `build`, healthchecks และ browser flow ใน container environment ผ่านจริง

### Mobile ใช้งาน graph ยาก

Mobile ต้องใช้ single active workspace และ persistent context switcher ไม่ย่อ desktop split panes ทั้งชุด

### Animation ทำให้เวียนหัว

เปิด reduced-motion ในระบบปฏิบัติการ Incident replay ต้องแสดง final state โดยไม่ animate

## Demo integrity checklist

- [ ] แสดงป้าย Synthetic demo ตลอด workflow
- [ ] ไม่กล่าวอ้าง production accuracy หรือ customer outcome
- [ ] ไม่กล่าวว่า GitHub/OTel/LLM เชื่อมต่อแล้ว
- [ ] เปิด risk dimension และ evidence ได้
- [ ] เปิด counter-evidence ได้
- [ ] แสดง uncertainty/data quality
- [ ] บันทึก human verdict ได้
- [ ] ไม่มีปุ่ม deploy/rollback/remediate
- [ ] keyboard และ reduced-motion flow ใช้งานได้

## สถานะการตรวจล่าสุด

- Backend: 13 tests ผ่าน
- Frontend: 7 tests ผ่าน และ Angular production build ผ่าน
- Production dependency audit: 0 vulnerabilities
- Browser: desktop/mobile flow และ feedback interaction ผ่าน
- API: 10 routes และ CORS local origins ผ่าน
- Compose: configuration ผ่าน
- Docker image build: ยังไม่ตรวจ เพราะ Linux daemon ไม่พร้อม
- GitHub, OTel, auth/tenancy, migrations, public/real benchmarks และ LLM: ยังไม่ implement
