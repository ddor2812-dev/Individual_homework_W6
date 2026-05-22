"""migrate-gp3 — (stretch) plan or apply gp2 → gp3 EBS migration.

WHY THIS MATTERS
----------------
gp3 is cheaper than gp2 ($0.08 vs $0.10 per GB-month) AND faster
(3000 IOPS baseline vs 3 IOPS/GB scaling). Most gp2 volumes should migrate.
EBS supports live modification — no downtime, no detach.

WHAT YOU MUST BUILD
-------------------
1. Dry-run mode (default):
   - List all gp2 volumes in the account
   - Show size, attached instance, and projected monthly savings per volume
   - Print total savings if all migrated

2. Apply mode (--apply):
   - With --volume-id: migrate just that one
   - Without --volume-id: migrate ALL gp2 volumes
   - Use ec2.modify_volume(...) — the modification runs in the background

AWS APIS YOU'LL NEED
--------------------
ec2.describe_volumes(Filters=[{"Name": "volume-type", "Values": ["gp2"]}])
ec2.modify_volume(
    VolumeId=vid,
    VolumeType="gp3",
    Iops=3000,        # baseline included free
    Throughput=125,   # baseline included free
)

After calling modify_volume, the volume goes through state transitions:
    in-use → modifying → optimizing → in-use (now gp3)
The app stays online throughout. Optimization takes ~30 min for a 100GB
volume; longer for larger volumes.

EXPECTED OUTPUT FORMAT (dry-run)
--------------------------------
    gp2 volumes (price delta $0.020/GB-month):
    ------------------------------------------------------------------------------
      vol-0abc123def456789a    100GB  attached=i-0aaa            $2.00/mo savings
      vol-0bbb456ef789012345     50GB  attached=(none)            $1.00/mo savings
    ------------------------------------------------------------------------------

    (dry-run — pass --apply --volume-id <id> to migrate one, or --apply to migrate ALL)

EXPECTED OUTPUT FORMAT (apply)
------------------------------
      → modify_volume issued for vol-0abc123def456789a (gp3, 3000 IOPS, 125 MiB/s)

    Volume(s) entering 'modifying' → 'optimizing' state. App stays online.
    Use `costctl list volume` after ~30 minutes to confirm 'in-use' + gp3.

VERIFY MANUALLY (no test file for this command)
-----------------------------------------------
    ./costctl.py migrate-gp3                           # dry-run, no side effects
    ./costctl.py migrate-gp3 --apply --volume-id vol-xxx  # migrate ONE

Pick a small volume first. Confirm via:
    ./costctl.py list volume --tag <something>
or AWS Console → EC2 → Volumes.

PRICING NOTE
------------
Constants below assume us-east-1 on-demand pricing. If your account is in
a different region, the dollar figure displayed is rough — but the migration
itself works the same anywhere.
"""
import boto3

# us-east-1 on-demand pricing per GB-month. Override if you care about exact $.
GP2_PRICE = 0.10
GP3_PRICE = 0.08


def run(args):
    """Entry point.

    Args set by argparse:
        args.apply       — bool, default False (dry-run)
        args.volume_id   — optional str, only migrate this volume when --apply
    """
    ec2 = boto3.client("ec2")

    # Fetch gp2 volumes
    res = ec2.describe_volumes(Filters=[{"Name": "volume-type", "Values": ["gp2"]}])
    volumes = res.get("Volumes", [])

    if not args.apply:
        print(f"gp2 volumes (price delta ${GP2_PRICE - GP3_PRICE:.3f}/GB-month):")
        print("-" * 78)

        total_savings = 0.0
        for vol in volumes:
            vid = vol["VolumeId"]
            size = vol["Size"]
            attachments = vol.get("Attachments", [])
            instance_id = attachments[0]["InstanceId"] if attachments else "(none)"
            attached_str = f"attached={instance_id}"

            savings = size * (GP2_PRICE - GP3_PRICE)
            total_savings += savings

            print(f"  {vid:<25}{size:>3}GB  {attached_str:<27}${savings:>4.2f}/mo savings")

        print("-" * 78)
        print()
        print("(dry-run — pass --apply --volume-id <id> to migrate one, or --apply to migrate ALL)")
        return

    # Apply mode
    target_volumes = []
    if args.volume_id:
        try:
            vol_res = ec2.describe_volumes(VolumeIds=[args.volume_id])
            vol = vol_res["Volumes"][0]
            if vol["VolumeType"] == "gp2":
                target_volumes.append(args.volume_id)
        except Exception:
            pass
    else:
        target_volumes = [v["VolumeId"] for v in volumes]

    if not target_volumes:
        print("No matching gp2 volume(s) found to migrate.")
        return

    for vid in target_volumes:
        ec2.modify_volume(
            VolumeId=vid,
            VolumeType="gp3",
            Iops=3000,
            Throughput=125
        )
        print(f"  → modify_volume issued for {vid} (gp3, 3000 IOPS, 125 MiB/s)")

    print()
    print("Volume(s) entering 'modifying' → 'optimizing' state. App stays online.")
    print("Use `costctl list volume` after ~30 minutes to confirm 'in-use' + gp3.")

