"""Command line entry point: python -m ai_discovery scan --mode mock --clouds aws gcp azure"""

import argparse
from contextlib import nullcontext
from pathlib import Path
import boto3

from ai_discovery.collectors.aws import AWSCollector
from ai_discovery.collectors.azure import AzureCollector
from ai_discovery.collectors.base import ScanScope
from ai_discovery.collectors.gcp import GCPCollector
from ai_discovery.config import get_settings
from botocore.exceptions import BotoCoreError, ClientError
from ai_discovery.demo.fake_account import ACCOUNT_ID, HOME_REGION, OTHER_REGION, build_messy_account
from ai_discovery.demo.fixture_apis import (
    AZURE_REGION,
    AZURE_SUBSCRIPTION,
    GCP_PROJECT,
    GCP_REGION,
    DemoAzureApi,
    DemoGCPApi,
)
from ai_discovery.governance.register import ApprovedRegister, load_register
from ai_discovery.llm.factory import build_model_specs, build_router
from ai_discovery.llm.report import build_cost_report
from ai_discovery.pipeline.scan import ScanSummary, ScanTarget, run_scan_targets

CLOUDS = ["aws", "gcp", "azure"]


def _print_summary(summary: ScanSummary, clouds: list[str], mode: str) -> None:
    print(f"Scan {summary.scan_id}")
    print(f"  clouds         : {', '.join(clouds)}")
    if mode == "mock":
        fixtures = [cloud for cloud in clouds if cloud != "aws"]
        print("  data source    : aws = moto (fake AWS)"
              + (f", {', '.join(fixtures)} = fixtures" if fixtures else ""))
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


def _mock_targets(clouds: list[str]) -> list[ScanTarget]:
    targets = []
    if "aws" in clouds:
        scope = ScanScope(account_id=ACCOUNT_ID, regions=[HOME_REGION, OTHER_REGION])
        targets.append(ScanTarget(AWSCollector(), scope))
    if "gcp" in clouds:
        scope = ScanScope(account_id=GCP_PROJECT, regions=[GCP_REGION])
        targets.append(ScanTarget(GCPCollector(DemoGCPApi()), scope))
    if "azure" in clouds:
        scope = ScanScope(account_id=AZURE_SUBSCRIPTION, regions=[AZURE_REGION])
        targets.append(ScanTarget(AzureCollector(DemoAzureApi()), scope))
    return targets


def _run_mock_scan(clouds: list[str], register: ApprovedRegister, router) -> ScanSummary:
    if "aws" in clouds:
        # Imported here so moto is only needed in mock mode.
        from moto import mock_aws

        fake_aws = mock_aws()
    else:
        fake_aws = nullcontext()

    with fake_aws:
        if "aws" in clouds:
            build_messy_account()
        return run_scan_targets(_mock_targets(clouds), register, router)


def _run_live_scan(
    account_id: str, regions: list[str], register: ApprovedRegister, router
) -> ScanSummary:
    scope = ScanScope(account_id=account_id, regions=regions)
    return run_scan_targets([ScanTarget(AWSCollector(), scope)], register, router)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ai_discovery")
    commands = parser.add_subparsers(dest="command", required=True)

    scan = commands.add_parser("scan", help="run one discovery scan")
    scan.add_argument("--mode", choices=["mock", "live"], default="mock")
    scan.add_argument("--clouds", nargs="+", choices=CLOUDS, default=["aws"])
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
        summary = _run_mock_scan(args.clouds, register, router)
    else:
        if args.clouds != ["aws"]:
            raise SystemExit("live mode supports only aws. GCP and Azure have no live adapter yet.")
        if not args.account_id or not args.regions:
            raise SystemExit("live mode needs --account-id and --regions")
        summary = _run_live_scan(args.account_id, args.regions, register, router)

        for message in summary.gap_messages:
            print(f"  GAP            : {message}")
        if summary.resources_seen == 0 and summary.scopes_with_gaps:
            print("  WARNING        : nothing was discovered and some scopes failed. Check permissions.")

    _print_summary(summary, args.clouds, args.mode)
    _print_cost_report(router)

def _verify_account(expected: str) -> None:
    """Refuse to scan if the credentials belong to a different account than --account-id."""
    try:
        actual = boto3.Session().client("sts").get_caller_identity()["Account"]
    except (ClientError, BotoCoreError) as error:
        raise SystemExit(f"could not verify AWS credentials: {type(error).__name__}")
    if actual != expected:
        raise SystemExit(
            f"credentials belong to account {actual}, but --account-id is {expected}. Refusing to scan."
        )


if __name__ == "__main__":
    main()