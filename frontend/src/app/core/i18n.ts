export type Language = 'th' | 'en';

export const TRANSLATIONS: Record<Language, Record<string, string>> = {
  th: {
    // Header & Navigation
    app_title: 'DeployGuard AI',
    app_subtitle: 'ระบบวิเคราะห์ความเสี่ยงและการสืบสวนสาเหตุการล่ม (RCA Ledger)',
    synthetic_demo: 'โหมดจำลองระบบ (Synthetic demo)',
    open_incidents: 'เหตุการณ์ล่มที่เปิดอยู่',
    high_risk_changes: 'รายการ PR เสี่ยงสูง',
    evidence_quality: 'ความสมบูรณ์ของหลักฐาน',
    tab_investigation: 'สืบสวนสาเหตุ (RCA)',
    tab_change_risk: 'วิเคราะห์ความเสี่ยง PR',
    tab_dora: 'ตัวชี้วัด DORA',
    tab_scenarios: 'ห้องจำลองสถานการณ์',
    theme_light: 'โหมดสว่าง',
    theme_dark: 'โหมดมืด',
    evidence_xray: 'โหมด X-ray หลักฐาน',

    // Page 1: RCA Investigation
    rca_tag: 'พื้นที่ทำงานวิเคราะห์และสืบสวนสาเหตุของ incident (RCA Workspace)',
    topology_title: 'ผังความเชื่อมโยงระบบ (Service Topology)',
    operational_surface_view: 'มุมมองพื้นผิวการทำงานระบบ (Operational Surface)',
    evidence_contribution_view: 'มุมมองการกระจายน้ำหนักหลักฐาน (Evidence Contribution X-Ray)',
    legend_changed: 'มีการแก้ไข',
    legend_impacted: 'ได้รับผลกระทบ',
    legend_active_path: 'เส้นทางผลกระทบ',
    registered_nodes: 'โหนดระบบที่ลงทะเบียน',
    dependency_relations: 'ความสัมพันธ์แบบพึ่งพา',
    geometry_locked: 'ตำแหน่งโหนดคงที่ระหว่างโหมด Surface และ X-ray',

    evidence_inspector_title: 'ตัวตรวจสอบหลักฐาน (Evidence Inspector)',
    telemetry_rows: 'รายการข้อมูล Telemetry',
    target_hypothesis: 'สมมติฐานเป้าหมาย',
    target_topology_node: 'โหนดระบบที่เลือก',
    no_evidence_linked: 'ไม่มีหลักฐานเชื่อมโยง',
    select_node_or_hypothesis: 'เลือกโหนดระบบหรือสมมติฐานเพื่อดูข้อมูลหลักฐานที่เกี่ยวข้อง',

    incident_replay_title: 'การเล่นย้อนหลังลำดับเหตุการณ์ (Incident Replay)',
    replay_incident_btn: 'เล่นย้อนหลังเหตุการณ์',
    pause_replay_btn: 'หยุดชั่วคราว',
    events_registered: 'รายการเหตุการณ์ที่บันทึก',
    services_affected: 'บริการที่ได้รับผลกระทบ',

    rca_hypotheses_title: 'RCA Top-3 hypotheses',
    rca_hypotheses_desc: 'สมมติฐานสาเหตุรากเหง้า 3 อันดับแรกที่ผ่านการประเมินจากหลักฐาน',
    confidence: 'ความมั่นใจ (Confidence)',
    next_step: 'ขั้นตอนถัดไป:',

    record_verdict_title: 'บันทึกคำตัดสินจากการสืบสวนโดยผู้เชี่ยวชาญ',
    verdict_placeholder: 'ระบุโน้ตสรุปผลการสืบสวนก่อนบันทึกคำตัดสิน...',
    confirm_cause: 'ยืนยันว่าเป็นสาเหตุหลัก',
    mark_partial: 'ระบุว่าเป็นสาเหตุบางส่วน',
    reject_hypothesis: 'ปฏิเสธสมมติฐานนี้',

    // Page 2: Change Risk Analyzer
    change_risk_tag: 'ระบบประเมินความเสี่ยง PULL REQUEST และขอบเขตผลกระทบ (BLAST RADIUS)',
    risk_score_title: 'การประเมินคะแนนความเสี่ยง (Risk Score Assessment)',
    computed_risk_index: 'ดัชนีความเสี่ยงคำนวณแบบ Deterministic',
    risk_level_tag: 'ระดับความเสี่ยง',
    data_quality_label: 'คุณภาพข้อมูลหลักฐาน:',
    pre_deploy_recommendations: 'คำแนะนำก่อนการปรับปรุงระบบ (Pre-Deploy Recommendations)',

    pr_details_title: 'รายละเอียด Pull Request',
    commit_sha: 'Commit SHA',
    deployment_status: 'สถานะการปรับปรุงระบบ',
    files_changed: 'จำนวนไฟล์ที่แก้ไข',
    lines_added_deleted: 'บรรทัดเพิ่ม / ลบ',
    risk_flags: 'แฟล็กความเสี่ยง (Risk Flags)',

    weighted_dimensions_title: 'มิติความเสี่ยงที่ถ่วงน้ำหนัก (Weighted Risk Dimensions)',
    weighted_dimensions_desc: 'รายละเอียดปัจจัยที่มีผลต่อการคำนวณคะแนนความเสี่ยง',
    weight_label: 'น้ำหนัก:',

    // Page 3: DORA Metrics
    dora_tag: 'ตัวชี้วัดประสิทธิภาพและการกู้คืนระบบ (ENGINEERING RELIABILITY METRICS)',
    dora_title: 'แดชบอร์ดวัดผล DORA Performance',
    deployment_frequency: 'ความถี่ในการปล่อยระบบ (DEPLOYMENT FREQUENCY)',
    change_lead_time: 'ระยะเวลาจาก Commit ถึง Prod (CHANGE LEAD TIME)',
    change_failure_rate: 'อัตราความล้มเหลวของการปล่อยระบบ (CHANGE FAILURE RATE)',
    mttr_label: 'ระยะเวลาเฉลี่ยในการกู้คืนระบบ (MTTR)',
    high_velocity: 'ความเร็วสูง (High Velocity)',
    elite_efficiency: 'ประสิทธิภาพระดับสูง (Elite Efficiency)',
    low_risk_profile: 'ความเสี่ยงต่ำ (Low Risk)',
    fast_recovery: 'กู้คืนรวดเร็ว (Fast Recovery)',
    based_on_releases: 'คำนวณจากการปล่อยอัปเดตระบบ production',
    avg_commit_to_rollout: 'ระยะเวลาเฉลี่ยตั้งแต่ Commit จนถึงการ Deploy',
    failure_incident_prop: 'สัดส่วนการปล่อยระบบที่ทำให้เกิด Incident',
    avg_mttr_desc: 'ระยะเวลาเฉลี่ยจาก SLO Breach จนถึงการกู้คืน',

    // Page 4: Scenario Lab
    scenario_lab_tag: 'เมทริกซ์จำลองสถานการณ์และข้อมูลทดลอง (SYNTHETIC SCENARIO LAB)',
    scenario_lab_title: 'ห้องทดลองสถานการณ์จำลอง (Scenario Lab Matrix)',
    registered_labs: 'รายการสถานการณ์จำลอง',
    active_scenario_badge: 'สถานการณ์ที่ใช้อยู่',
    activate_scenario_btn: 'เปิดใช้งานสถานการณ์นี้',
    activating_lab: 'กำลังเปิดใช้งาน...',
    current_active_lab: 'สถานการณ์ปัจจุบัน'
  },
  en: {
    // Header & Navigation
    app_title: 'DeployGuard AI',
    app_subtitle: 'Evidence-backed change risk & incident investigation ledger',
    synthetic_demo: 'Synthetic Demo Mode',
    open_incidents: 'Open Incidents',
    high_risk_changes: 'High Risk PRs',
    evidence_quality: 'Evidence Quality',
    tab_investigation: 'RCA Investigation',
    tab_change_risk: 'Change Risk Analyzer',
    tab_dora: 'DORA Metrics',
    tab_scenarios: 'Scenario Lab',
    theme_light: 'Light Mode',
    theme_dark: 'Dark Mode',
    evidence_xray: 'Evidence X-Ray',

    // Page 1: RCA Investigation
    rca_tag: 'RCA & SERVICE INCIDENT INVESTIGATION WORKSPACE',
    topology_title: 'Registered Service Topology',
    operational_surface_view: 'Operational Surface View',
    evidence_contribution_view: 'Evidence Contribution X-Ray View',
    legend_changed: 'Changed',
    legend_impacted: 'Impacted',
    legend_active_path: 'Active Path',
    registered_nodes: 'registered nodes',
    dependency_relations: 'dependency relations',
    geometry_locked: 'Geometry locked between Surface / X-ray',

    evidence_inspector_title: 'Evidence Inspector',
    telemetry_rows: 'Telemetry Rows',
    target_hypothesis: 'Target Hypothesis',
    target_topology_node: 'Target Node',
    no_evidence_linked: 'No evidence linked',
    select_node_or_hypothesis: 'Select a topology node or hypothesis to inspect related telemetry evidence.',

    incident_replay_title: 'Incident Replay & Sequence',
    replay_incident_btn: 'Replay Incident',
    pause_replay_btn: 'Pause Replay',
    events_registered: 'registered events',
    services_affected: 'affected services',

    rca_hypotheses_title: 'RCA Top-3 hypotheses',
    rca_hypotheses_desc: 'Ranked, evidence-backed root cause hypotheses',
    confidence: 'Confidence',
    next_step: 'Next Step:',

    record_verdict_title: 'Record Human Verdict for Hypothesis',
    verdict_placeholder: 'Add mandatory investigation notes before recording verdict...',
    confirm_cause: 'Confirm Cause',
    mark_partial: 'Mark Partial Cause',
    reject_hypothesis: 'Reject Hypothesis',

    // Page 2: Change Risk Analyzer
    change_risk_tag: 'PULL REQUEST RISK & BLAST RADIUS ANALYZER',
    risk_score_title: 'Risk Score Assessment',
    computed_risk_index: 'Computed deterministic risk index',
    risk_level_tag: 'RISK LEVEL',
    data_quality_label: 'Data Quality:',
    pre_deploy_recommendations: 'Pre-Deploy Recommendations',

    pr_details_title: 'Pull Request Details',
    commit_sha: 'Commit SHA',
    deployment_status: 'Deployment Status',
    files_changed: 'Files Changed',
    lines_added_deleted: 'Lines Added / Deleted',
    risk_flags: 'Risk Flags',

    weighted_dimensions_title: 'Weighted Risk Dimensions',
    weighted_dimensions_desc: 'Breakdown of factors contributing to the risk score',
    weight_label: 'Weight:',

    // Page 3: DORA Metrics
    dora_tag: 'ENGINEERING PRODUCTIVITY & RELIABILITY METRICS',
    dora_title: 'DORA Performance Dashboard',
    deployment_frequency: 'DEPLOYMENT FREQUENCY',
    change_lead_time: 'CHANGE LEAD TIME',
    change_failure_rate: 'CHANGE FAILURE RATE',
    mttr_label: 'MEAN TIME TO RESTORE (MTTR)',
    high_velocity: 'High Velocity',
    elite_efficiency: 'Elite Efficiency',
    low_risk_profile: 'Low Risk Profile',
    fast_recovery: 'Fast Recovery',
    based_on_releases: 'Based on production release markers',
    avg_commit_to_rollout: 'Average elapsed time from commit SHA to deployment rollout',
    failure_incident_prop: 'Proportion of deployments triggering an incident investigation',
    avg_mttr_desc: 'Average duration between SLO breach and resolution verdict',

    // Page 4: Scenario Lab
    scenario_lab_tag: 'SYNTHETIC SCENARIOS & REPRODUCIBLE DATA MATRIX',
    scenario_lab_title: 'Scenario Lab Matrix',
    registered_labs: 'Registered Labs',
    active_scenario_badge: 'Active Scenario',
    activate_scenario_btn: 'Activate Scenario',
    activating_lab: 'Activating Lab...',
    current_active_lab: 'Current Active Lab'
  }
};
