"""Command line entry point: python -m ai_discovery scan --mode mock"""

import argparse
from ai_discovery.config import get_settings
from ai_discovery.llm.factory import build_model_specs, build_router
from ai_discovery.llm.report import build_cost_report
from pathlib import Path

from ai_discovery.collectors.aws import AWSCollector
from ai_discovery.collectors.base import ScanScope
from ai_discovery.governance.register import ApprovedRegister, load_register
from ai_discovery.pipeline.scan import ScanSummary, run_scan


def _print_summary(summary: ScanSummary) -> None:
    print(f"Scan {summary.scan_id}")
    print(f"  resources seen : {summary.resources_seen}")
    print(f"  assets stored  : {summary.assets_recorded}")
    print(f"  verdicts       : {summary.verdict_counts}")
    print(f"  scopes w/ gaps : {summary.scopes_with_gaps}")

def _print_cost_report(router) -> None:
    if router is None:
        print("  LLM            : not used")
        return
    _, large = build_model_specs(get_settings())
    report = build_cost_report(router.calls, large)
    print(f"  LLM calls      : {report.total_calls} {report.calls_by_tier}")
    print(f"  escalated      : {report.escalated_calls}")
    print(f"  outcomes       : {report.outcomes}")
    print(f"  LLM cost       : ${report.total_cost_usd:.5f}")
    print(f"  if all large   : ${report.all_large_cost_usd:.5f} (estimate)")


def _run_mock_scan(register: ApprovedRegister, router) -> ScanSummary:
    # Imported here so moto is only needed when running in mock mode.
    from moto import mock_aws

    from ai_discovery.demo.fake_account import (
        ACCOUNT_ID,
        HOME_REGION,
        OTHER_REGION,
        build_messy_account,
    )

    with mock_aws():
        build_messy_account()
        scope = ScanScope(account_id=ACCOUNT_ID, regions=[HOME_REGION, OTHER_REGION])
        return run_scan(AWSCollector(), scope, register, router)


def _run_live_scan(account_id: str, regions: list[str], register: ApprovedRegister, router) -> ScanSummary:
    scope = ScanScope(account_id=account_id, regions=regions)
    return run_scan(AWSCollector(), scope, register, router)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ai_discovery")
    commands = parser.add_subparsers(dest="command", required=True)

    scan = commands.add_parser("scan", help="run one discovery scan")
    scan.add_argument("--mode", choices=["mock", "live"], default="mock")
    scan.add_argument("--register", type=Path, help="path to the approved register YAML")
    scan.add_argument("--account-id", help="AWS account id (live mode)")
    scan.add_argument("--regions", nargs="+", help="AWS regions to scan (live mode)")
    scan.add_argument("--no-llm", action="store_true", help="skip the LLM inspector")
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)

    register = load_register(args.register) if args.register else ApprovedRegister()
    router = None if args.no_llm else build_router(get_settings())

    if args.mode == "mock":
        summary = _run_mock_scan(register, router)
    else:
        if not args.account_id or not args.regions:
            raise SystemExit("live mode needs --account-id and --regions")
        summary = _run_live_scan(args.account_id, args.regions, register, router)

    _print_summary(summary)
    _print_cost_report(router)


if __name__ == "__main__":
    main()