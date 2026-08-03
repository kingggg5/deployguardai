import { DoraMetrics, IncidentFeedback, Overview, ScenarioSummary } from './core/models/deployguard.models';

export const doraMetricsFixture: DoraMetrics = {
  period: 'Last 30 Days',
  deployment_frequency_per_week: 7.0,
  change_lead_time_minutes: 90,
  change_failure_rate: 0.042,
  mean_time_to_restore_minutes: 18.0,
  deployment_rework_rate: 0.02,
  total_deployments: 28,
  total_incidents: 1
};

export const scenarioFixtures: ScenarioSummary[] = [
  {
    id: 'checkout-latency',
    name: 'Checkout latency',
    description: 'A checkout deploy increases database latency.',
    repository: 'acme/commerce',
    data_mode: 'synthetic',
    is_active: true,
    active_change_id: 'chg-checkout',
    active_incident_id: 'inc-checkout'
  },
  {
    id: 'queue-backlog',
    name: 'Queue backlog',
    description: 'A worker release creates a processing backlog.',
    repository: 'acme/workers',
    data_mode: 'synthetic',
    is_active: false,
    active_change_id: 'chg-queue',
    active_incident_id: 'inc-queue'
  }
];

export function makeOverview(
  scenarioId = 'checkout-latency',
  feedback: IncidentFeedback[] = []
): Overview {
  const queueScenario = scenarioId === 'queue-backlog';
  const changeId = queueScenario ? 'chg-queue' : 'chg-checkout';
  const incidentId = queueScenario ? 'inc-queue' : 'inc-checkout';

  return {
    generated_at: '2026-07-26T12:00:00Z',
    data_mode: 'synthetic',
    active_scenario_id: scenarioId,
    stats: {
      open_incidents: 1,
      high_risk_changes: 1,
      services_monitored: 3,
      evidence_quality: 0.91
    },
    active_change: {
      id: changeId,
      scenario_id: scenarioId,
      data_mode: 'synthetic',
      analysis_schema_version: '1.0.0',
      engine_version: '1.0.0',
      scoring_policy_version: 'risk-weighted-v1',
      graph_version: 'dependency-bfs-v1',
      title: queueScenario ? 'Release worker batching' : 'Tune checkout persistence',
      repository: 'acme/commerce',
      author: 'release-bot',
      commit_sha: 'abc12345def67890',
      branch: 'main',
      created_at: '2026-07-26T11:52:00Z',
      deployment_status: 'deployed',
      deployment_environment: 'production',
      changed_services: ['checkout-api'],
      files_changed: 8,
      lines_added: 120,
      lines_deleted: 24,
      flags: ['schema-touch', 'hot-path'],
      risk: {
        overall_score: 82,
        level: 'high',
        data_quality: 0.9,
        dimensions: [
          {
            key: 'blast',
            label: 'Blast radius',
            score: 82,
            weight: 0.4,
            reason: 'The changed service owns a synchronous database path.',
            evidence_ids: ['ev-trace']
          }
        ],
        recommendations: ['Verify the checkout write latency before promotion.']
      },
      blast_radius: {
        nodes: [
          {
            id: 'checkout-api',
            label: 'Checkout API',
            kind: 'service',
            team: 'Commerce',
            tier: '1',
            health: 'critical',
            impact_score: 95,
            hop_distance: 0,
            evidence_ids: ['ev-trace']
          },
          {
            id: 'orders-db',
            label: 'Orders DB',
            kind: 'database',
            team: 'Data',
            tier: '1',
            health: 'degraded',
            impact_score: 78,
            hop_distance: 1,
            evidence_ids: ['ev-db']
          },
          {
            id: 'payment-api',
            label: 'Payment API',
            kind: 'external',
            team: 'Payments',
            tier: '1',
            health: 'healthy',
            impact_score: 26,
            hop_distance: 1,
            evidence_ids: []
          }
        ],
        edges: [
          {
            source: 'checkout-api',
            target: 'orders-db',
            relation: 'writes',
            confidence: 0.98,
            active: true
          }
        ]
      }
    },
    active_incident: {
      id: incidentId,
      scenario_id: scenarioId,
      data_mode: 'synthetic',
      analysis_schema_version: '1.0.0',
      engine_version: '1.0.0',
      scoring_policy_version: 'evidence-ranker-v1',
      graph_version: 'not-applicable',
      title: queueScenario ? 'Worker queue saturation' : 'Checkout latency regression',
      severity: 'SEV-2',
      status: 'investigating',
      started_at: '2026-07-26T11:58:00Z',
      resolved_at: null,
      affected_services: ['checkout-api', 'orders-db'],
      correlated_change_id: changeId,
      summary: 'Request latency rose immediately after the registered deployment.',
      timeline: [
        {
          id: 'evt-deploy',
          timestamp: '2026-07-26T11:55:00Z',
          type: 'deploy',
          title: 'Deployment completed',
          detail: 'The checkout release reached production.',
          service_id: 'checkout-api'
        },
        {
          id: 'evt-alert',
          timestamp: '2026-07-26T11:58:00Z',
          type: 'alert',
          title: 'Latency SLO breached',
          detail: 'Checkout p95 exceeded the registered threshold.',
          service_id: 'checkout-api'
        }
      ],
      evidence: [
        {
          id: 'ev-trace',
          type: 'trace',
          source: 'otel',
          timestamp: '2026-07-26T11:58:30Z',
          summary: 'Checkout spans spend most time in order persistence.',
          value: 1240,
          quality: 0.96,
          service_id: 'checkout-api',
          supports: ['hyp-db'],
          contradicts: []
        },
        {
          id: 'ev-db',
          type: 'metric',
          source: 'postgres',
          timestamp: '2026-07-26T11:58:35Z',
          summary: 'Database lock wait time increased.',
          value: 0.82,
          quality: 0.88,
          service_id: 'orders-db',
          supports: ['hyp-db'],
          contradicts: []
        }
      ],
      hypotheses: [
        {
          id: 'hyp-db',
          rank: 1,
          cause_service: 'orders-db',
          cause: 'Order persistence lock contention',
          confidence: 0.87,
          score: 87,
          evidence_ids: ['ev-trace', 'ev-db'],
          counter_evidence_ids: [],
          reasoning: 'Trace latency and lock waits move together after the deploy.',
          next_step: 'Compare lock holders with the changed transaction.',
          status: 'likely'
        }
      ],
      feedback
    }
  };
}
