"""cost — show cost of resources matching a tag, over the last N days.

WHAT YOU MUST BUILD
-------------------
A function that:
  1. Queries Cost Explorer (`ce.get_cost_and_usage`) for the last N days
  2. Filters by a tag (e.g. Application=HealthBot)
  3. Groups by SERVICE dimension
  4. Sums per-service costs across the date range
  5. Prints services sorted descending by cost, plus a TOTAL row

HELPERS YOU CAN USE
-------------------
From commands._common:
  parse_kv(s) -> (k, v)             # "Application=HealthBot" -> tuple

AWS APIS YOU'LL NEED
--------------------
ce = boto3.client("ce")
ce.get_cost_and_usage(
    TimePeriod={"Start": "YYYY-MM-DD", "End": "YYYY-MM-DD"},
    Granularity="DAILY",
    Metrics=["UnblendedCost"],
    Filter={"Tags": {"Key": "<tag_key>", "Values": ["<tag_value>"]}},
    GroupBy=[{"Type": "DIMENSION", "Key": "SERVICE"}],
)

The response has `ResultsByTime` (one entry per day), each with `Groups` —
each group has `Keys=[service_name]` and `Metrics={"UnblendedCost":{"Amount":"1.23"}}`.

EXPECTED OUTPUT FORMAT
----------------------
    Cost for Application=HealthBot over last 7 days (2026-05-14 → 2026-05-21):
    ------------------------------------------------------------
      Amazon Elastic Compute Cloud - Compute        $    8.42
      Amazon Relational Database Service             $    5.18
      ...
    ------------------------------------------------------------
      TOTAL                                          $   13.80

GOTCHAS
-------
- Cost data lags 8–24h. If --days 1 returns nothing, try --days 7.
- Tag filter requires that you have ACTIVATED cost allocation tags in Billing.
- Amount field is a STRING in the response — cast to float before summing.

VERIFY MANUALLY (no test file for this command)
-----------------------------------------------
    ./costctl.py cost --tag Application=<your-app> --days 7

The first time you run this, double-check against the AWS Console
(Cost Management → Cost Explorer → filter by same tag + same range).
Output should match within a few cents.
"""
import boto3
from collections import defaultdict
from datetime import date, timedelta

from commands._common import parse_kv


def run(args):
    """Entry point.

    Args set by argparse:
        args.tag   — "key=value" string (REQUIRED)
        args.days  — int, default 7
    """
    tag_key, tag_value = parse_kv(args.tag)

    end_date = date.today()
    start_date = end_date - timedelta(days=args.days)

    start_str = start_date.strftime("%Y-%m-%d")
    end_str = end_date.strftime("%Y-%m-%d")

    ce = boto3.client("ce")

    res = ce.get_cost_and_usage(
        TimePeriod={"Start": start_str, "End": end_str},
        Granularity="DAILY",
        Metrics=["UnblendedCost"],
        Filter={"Tags": {"Key": tag_key, "Values": [tag_value]}},
        GroupBy=[{"Type": "DIMENSION", "Key": "SERVICE"}],
    )

    costs = defaultdict(float)
    for day_result in res.get("ResultsByTime", []):
        for group in day_result.get("Groups", []):
            service = group["Keys"][0]
            amount = float(group["Metrics"]["UnblendedCost"]["Amount"])
            costs[service] += amount

    sorted_services = sorted(costs.items(), key=lambda x: x[1], reverse=True)
    total_cost = sum(costs.values())

    yesterday_str = (end_date - timedelta(days=1)).strftime("%Y-%m-%d")
    print(f"Cost for {args.tag} over last {args.days} days ({start_str} → {yesterday_str}):")
    print("-" * 60)
    for service, cost in sorted_services:
        print(f"  {service:<46}${cost:>9.2f}")
    print("-" * 60)
    print(f"  {'TOTAL':<46}${total_cost:>9.2f}")

