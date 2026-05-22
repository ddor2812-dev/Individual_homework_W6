"""tag — add or update tags on one resource.

WHAT YOU MUST BUILD
-------------------
4 dispatch functions, one per resource type. Each accepts a resource id
and a list of `{"Key": ..., "Value": ...}` dicts, and applies the tags.

Tagging semantics across AWS services is INCONSISTENT — make sure you read
the boto3 doc page for each API before implementing.

HELPERS YOU CAN USE
-------------------
From commands._common:
  parse_kv(s) -> (k, v)

AWS APIS YOU'LL NEED
--------------------
- EC2:    ec2.create_tags(Resources=[id], Tags=[{Key,Value}, ...])
            (works for both instances and volumes — same API)
- RDS:    rds.add_tags_to_resource(ResourceName=<ARN>, Tags=[...])
            Note: you need the ARN, not the DB id. Fetch via:
              rds.describe_db_instances(DBInstanceIdentifier=id)["DBInstances"][0]["DBInstanceArn"]
- S3:     s3.put_bucket_tagging(Bucket=name, Tagging={"TagSet": [...]})
            CAUTION: put_bucket_tagging REPLACES the entire tag set.
            You MUST first get_bucket_tagging, merge with new tags, then put.
            If get_bucket_tagging raises ClientError (no existing tags),
            treat that as empty list and just put the new tags.

EXPECTED OUTPUT
---------------
    Applied 2 tag(s) to ec2 i-0abc: Owner=alice, Application=HealthBot

VERIFY MANUALLY (no test file for this command)
-----------------------------------------------
    ./costctl.py tag ec2 --id <real-id> --set Owner=alice
    ./costctl.py list ec2 --tag Owner=alice
    # Should appear in the list.

USEFUL COMBO
------------
    ./costctl.py tag ec2 \\
      --id $(./costctl.py list ec2 --missing-tag Application | awk 'NR==4{print $1}') \\
      --set Application=HealthBot
"""
import boto3

from commands._common import parse_kv


def _to_tags(set_args):
    """Convert ['k1=v1', 'k2=v2'] to [{'Key':'k1','Value':'v1'}, ...]."""
    tags = []
    for s in set_args:
        k, v = parse_kv(s)
        tags.append({"Key": k, "Value": v})
    return tags


def _tag_ec2(rid, tags):
    ec2 = boto3.client("ec2")
    ec2.create_tags(Resources=[rid], Tags=tags)


def _tag_rds(rid, tags):
    rds = boto3.client("rds")
    res = rds.describe_db_instances(DBInstanceIdentifier=rid)
    arn = res["DBInstances"][0]["DBInstanceArn"]
    rds.add_tags_to_resource(ResourceName=arn, Tags=tags)


def _tag_s3(rid, tags):
    s3 = boto3.client("s3")
    existing_tags = []
    try:
        res = s3.get_bucket_tagging(Bucket=rid)
        existing_tags = res.get("TagSet", [])
    except Exception:
        pass

    merged_dict = {t["Key"]: t["Value"] for t in existing_tags}
    for t in tags:
        merged_dict[t["Key"]] = t["Value"]

    merged_tags = [{"Key": k, "Value": v} for k, v in merged_dict.items()]
    s3.put_bucket_tagging(Bucket=rid, Tagging={"TagSet": merged_tags})


def _tag_volume(rid, tags):
    ec2 = boto3.client("ec2")
    ec2.create_tags(Resources=[rid], Tags=tags)


DISPATCH = {
    "ec2": _tag_ec2,
    "rds": _tag_rds,
    "s3": _tag_s3,
    "volume": _tag_volume,
}


def run(args):
    """Entry point.

    Args set by argparse:
        args.type  — one of "ec2", "rds", "s3", "volume"
        args.id    — resource identifier
        args.set   — list[str], each "key=value"
    """
    tags = _to_tags(args.set)
    DISPATCH[args.type](args.id, tags)
    tags_str = ", ".join(f"{t['Key']}={t['Value']}" for t in tags)
    print(f"Applied {len(tags)} tag(s) to {args.type} {args.id}: {tags_str}")

