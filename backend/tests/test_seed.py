from sqlalchemy import func, select

from app.database import Database
from app.engines import (
    ANALYSIS_SCHEMA_VERSION,
    ENGINE_VERSION,
    GRAPH_VERSION,
    GRAPH_VERSION_NOT_APPLICABLE,
    RCA_SCORING_POLICY_VERSION,
    RISK_SCORING_POLICY_VERSION,
)
from app.models import ChangeRecord, IncidentRecord, Scenario
from app.seed import seed_database


def test_seed_is_idempotent(tmp_path) -> None:
    database = Database(f"sqlite:///{(tmp_path / 'seed.db').as_posix()}")
    database.create_schema()
    session = database.session_factory()
    try:
        seed_database(session)
        seed_database(session)

        assert session.scalar(
            select(func.count()).select_from(Scenario)
        ) == 3
        assert session.scalar(
            select(func.count()).select_from(ChangeRecord)
        ) == 3
        assert session.scalar(
            select(func.count()).select_from(IncidentRecord)
        ) == 3
        assert session.scalar(
            select(func.count())
            .select_from(Scenario)
            .where(Scenario.is_active.is_(True))
        ) == 1

        for incident in session.scalars(select(IncidentRecord)).all():
            assert incident.analysis_schema_version == ANALYSIS_SCHEMA_VERSION
            assert incident.engine_version == ENGINE_VERSION
            assert incident.scoring_policy_version == RCA_SCORING_POLICY_VERSION
            assert incident.graph_version == GRAPH_VERSION_NOT_APPLICABLE
            evidence_ids = {item["id"] for item in incident.evidence}
            hypothesis_ids = {item["id"] for item in incident.hypotheses}

            assert [item["rank"] for item in incident.hypotheses] == [1, 2, 3]
            for hypothesis in incident.hypotheses:
                assert set(hypothesis["evidence_ids"]) <= evidence_ids
                assert set(hypothesis["counter_evidence_ids"]) <= evidence_ids
            for evidence in incident.evidence:
                assert set(evidence["supports"]) <= hypothesis_ids
                assert set(evidence["contradicts"]) <= hypothesis_ids
                assert not (
                    set(evidence["supports"]) & set(evidence["contradicts"])
                )
        for change in session.scalars(select(ChangeRecord)).all():
            assert change.analysis_schema_version == ANALYSIS_SCHEMA_VERSION
            assert change.engine_version == ENGINE_VERSION
            assert change.scoring_policy_version == RISK_SCORING_POLICY_VERSION
            assert change.graph_version == GRAPH_VERSION

        historical = session.get(ChangeRecord, "chg-checkout-timeout")
        assert historical is not None
        historical.engine_version = "legacy-unversioned"
        session.commit()
        seed_database(session)
        assert (
            session.get(ChangeRecord, "chg-checkout-timeout").engine_version
            == "legacy-unversioned"
        )
    finally:
        session.close()
        database.dispose()
