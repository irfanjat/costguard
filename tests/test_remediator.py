import boto3
from moto import mock_aws

from src.remediator.resources import ResourceScanner


@mock_aws
def test_detects_unattached_ebs():
    ec2 = boto3.client("ec2", region_name="us-east-1")
    ec2.create_volume(AvailabilityZone="us-east-1a", Size=10)

    scanner = ResourceScanner(regions=["us-east-1"])
    report = scanner.scan()

    ebs = [r for r in report.resources if r.resource_type == "ebs_volume"]
    assert len(ebs) == 1
    assert ebs[0].can_auto_remediate


@mock_aws
def test_attached_ebs_not_reported():
    ec2 = boto3.client("ec2", region_name="us-east-1")
    ec2.create_volume(AvailabilityZone="us-east-1a", Size=10)
    instances = ec2.run_instances(
        ImageId="ami-12345678", MinCount=1, MaxCount=1
    )
    instance_id = instances["Instances"][0]["InstanceId"]
    vols = ec2.describe_volumes()
    ec2.attach_volume(
        VolumeId=vols["Volumes"][0]["VolumeId"],
        InstanceId=instance_id,
        Device="/dev/xvda",
    )

    scanner = ResourceScanner(regions=["us-east-1"])
    report = scanner.scan()
    ebs = [r for r in report.resources if r.resource_type == "ebs_volume"]
    assert len(ebs) == 0


@mock_aws
def test_detects_unassociated_eip():
    ec2 = boto3.client("ec2", region_name="us-east-1")
    ec2.allocate_address(Domain="vpc")

    addrs = ec2.describe_addresses().get("Addresses", [])
    assert len(addrs) == 1, "moto should have created the EIP"

    scanner = ResourceScanner(regions=["us-east-1"])
    report = scanner.scan()
    eips = [r for r in report.resources if r.resource_type == "eip"]
    assert len(eips) == 1
    assert eips[0].estimated_monthly_cost == 3.60


@mock_aws
def test_no_idle_lb_with_healthy_targets():
    ec2 = boto3.client("ec2", region_name="us-east-1")
    elbv2 = boto3.client("elbv2", region_name="us-east-1")

    vpc = ec2.create_vpc(CidrBlock="10.0.0.0/16")
    vpc_id = vpc["Vpc"]["VpcId"]
    subnet = ec2.create_subnet(VpcId=vpc_id, CidrBlock="10.0.1.0/24")
    subnet_id = subnet["Subnet"]["SubnetId"]

    instances = ec2.run_instances(
        ImageId="ami-12345678", MinCount=1, MaxCount=1
    )
    instance_id = instances["Instances"][0]["InstanceId"]

    lb = elbv2.create_load_balancer(
        Name="test-lb", Subnets=[subnet_id]
    )["LoadBalancers"][0]
    tg = elbv2.create_target_group(
        Name="test-tg", Protocol="HTTP", Port=80, VpcId=vpc_id
    )["TargetGroups"][0]
    elbv2.register_targets(
        TargetGroupArn=tg["TargetGroupArn"],
        Targets=[{"Id": instance_id}],
    )
    elbv2.create_listener(
        LoadBalancerArn=lb["LoadBalancerArn"],
        Protocol="HTTP",
        Port=80,
        DefaultActions=[{
            "Type": "forward",
            "ForwardConfig": {
                "TargetGroups": [{"TargetGroupArn": tg["TargetGroupArn"]}]
            },
        }],
    )

    scanner = ResourceScanner(regions=["us-east-1"])
    report = scanner.scan()
    lbs = [r for r in report.resources if r.resource_type == "load_balancer"]
    assert len(lbs) == 0  # moto simulates health checks as healthy


@mock_aws
def test_no_stale_snapshots_within_threshold():
    ec2 = boto3.client("ec2", region_name="us-east-1")
    ec2.create_snapshot(
        Description="test",
        VolumeId=ec2.create_volume(AvailabilityZone="us-east-1a", Size=10)["VolumeId"],
    )

    scanner = ResourceScanner(regions=["us-east-1"], stale_snapshot_days=999)
    report = scanner.scan()
    snaps = [r for r in report.resources if r.resource_type == "snapshot"]
    assert len(snaps) == 0


@mock_aws
def test_scan_returns_remediation_report():
    ec2 = boto3.client("ec2", region_name="us-east-1")
    ec2.create_volume(AvailabilityZone="us-east-1a", Size=10)

    scanner = ResourceScanner(regions=["us-east-1"])
    report = scanner.scan()
    assert report.total_orphaned_count > 0
    assert report.total_estimated_savings > 0
