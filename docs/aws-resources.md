# What is running in AWS

Provisioned 2026-09-20 in **ap-southeast-2** (Sydney), CLI profile `sdoc`
(the account id is deliberately not written down here — this repository is public). Everything here is inside the free tier; the Elastic IP is the only
thing that costs money if the instance is ever stopped without releasing it.

| resource | id | note |
|---|---|---|
| EC2 instance | `i-0c7ff1d36649f09e3` | t3.micro, Ubuntu 24.04, 16 GB gp3 encrypted |
| Elastic IP | **54.66.241.118** | the A record points here |
| Security group | `sg-0ac5e3caa5fec55d0` | 22 from one IP only, 80 + 443 open |
| Key pair | `sdoc-key` | private half at `~/.ssh/sdoc-key.pem`, ed25519 |
| EIP allocation | `eipalloc-08b3980fbe62c6c64` | release this when tearing down, or it bills |

```bash
ssh -i ~/.ssh/sdoc-key.pem ubuntu@54.66.241.118
```

The instance is configured with 2 GB of swap (1 GB of RAM is not enough to start a
container comfortably), Docker from the official script, unattended security upgrades,
and IMDSv2 required.

## The SSH rule is pinned to one address

Port 22 is open to `161.142.153.68/32` and nothing else.
**Your home IP will change** — when ssh starts timing out, that is why:

```bash
export AWS_PROFILE=sdoc AWS_REGION=ap-southeast-2
MYIP=$(curl -s https://checkip.amazonaws.com)
aws ec2 authorize-security-group-ingress --group-id sg-0ac5e3caa5fec55d0 \
  --ip-permissions "IpProtocol=tcp,FromPort=22,ToPort=22,IpRanges=[{CidrIp=${MYIP}/32}]"
```

Do not "fix" it by opening 22 to `0.0.0.0/0`. A box on a public IP with open ssh is
found by scanners within minutes.

## The CI deploy key

GitLab CI logs in with its own ed25519 key, not the one above. The private half and the
pinned `known_hosts` are in `~/sdoc-ci-credentials/` on Daniil's laptop with a README
saying which GitLab variable each one goes in — deliberately not in this repository,
which is public. The public half is already in the server's `authorized_keys`.

If the instance is ever rebuilt, regenerate all of it: the host key changes, the pinned
`known_hosts` stops matching, and the deploy job fails at the ssh step. That is the
single most common way this breaks.

## Costs

t3.micro and 16 GB of gp3 are inside the 12-month free tier. An Elastic IP is free
**while attached to a running instance** and billed hourly when it is not — so if you
stop the instance for the night, either leave it running or release the address.

Nothing else is provisioned: no load balancer, no RDS, no NAT gateway. The three things
that quietly cost money on AWS are all absent.

## Tearing it down

```bash
export AWS_PROFILE=sdoc AWS_REGION=ap-southeast-2
aws ec2 terminate-instances --instance-ids i-0c7ff1d36649f09e3
aws ec2 wait instance-terminated --instance-ids i-0c7ff1d36649f09e3
aws ec2 release-address --allocation-id eipalloc-08b3980fbe62c6c64
aws ec2 delete-security-group --group-id sg-0ac5e3caa5fec55d0
aws ec2 delete-key-pair --key-name sdoc-key
```
