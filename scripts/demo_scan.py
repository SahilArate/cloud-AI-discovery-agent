"""Builds a messy fake AWS account in moto and runs a full scan against Postgres.

Usage: python scripts/demo_scan.py
Needs the database running and migrated (docker compose up -d, alembic upgrade head).
"""

from pathlib import Path

from moto import mock_aws
from sqlalchemy import select

from ai_discovery.collectors.aws import AWSCollector
from ai_discovery.collectors.base import ScanScope
from ai_discovery.db.session import session_scope
from ai_discovery.db.tables import AssetObservation, ScanScopeResult
from ai_discovery.demo.fake_account import (
    ACCOUNT_ID,
    HOME_REGION,
    OTHER_REGION,
    build_messy_account,
)
from ai_discovery.governance.register import load_register
from ai_discovery.pipeline.scan import run_scan

REGISTER_PATH = Path(__file__).resolve().parent.parent / "data" / "approved_register.yaml"


def print_results(summary) -> None:
    print(f"\nScan {summary.scan_id}")
    print(f"  resources seen : {summary.resources_seen}")
    print(f"  assets stored  : {summary.assets_recorded}")
    print(f"  verdicts       : {summary.verdict_counts}")
    print(f"  scopes w/ gaps : {summary.scopes_with_gaps}")

    with session_scope() as session:
        rows = session.scalars(
            select(AssetObservation)
            .where(AssetObservation.scan_id == summary.scan_id)
            .order_by(AssetObservation.asset_key)
        ).all()

        print("\nAI inventory from this scan")
        print(f"  {'asset':<50} {'verdict':<14} {'approval':<22} {'risk':<8} owner")
        for row in rows:
            short_name = row.asset_key.split(":", 1)[1].split(":")[-1]
            owner = f"{row.owner} ({row.owner_source})" if row.owner else "unknown"
            print(
                f"  {short_name:<50} {row.ai_verdict:<14} "
                f"{row.approval_status:<22} {row.risk_tier:<8} {owner}"
            )

        gaps = session.scalars(
            select(ScanScopeResult).where(
                ScanScopeResult.scan_id == summary.scan_id,
                ScanScopeResult.status != "complete",
            )
        ).all()
        if gaps:
            print("\nCoverage gaps")
            for gap in gaps:
                print(f"  {gap.region}/{gap.service}: {gap.status} {gap.errors}")


def main() -> None:
    with mock_aws():
        build_messy_account()
        scope = ScanScope(account_id=ACCOUNT_ID, regions=[HOME_REGION, OTHER_REGION])
        summary = run_scan(AWSCollector(), scope, load_register(REGISTER_PATH))
    print_results(summary)


if __name__ == "__main__":
    main()