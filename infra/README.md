# AWS backend

Implemented and tested locally; **not deployed**. This Mac has no AWS CLI, AWS
environment configuration, or `~/.aws` credentials. No account or region has been
selected and no AWS resources have been created.

`template.json` provisions a daily EventBridge rule, a Python 3.13 Lambda, immutable
DynamoDB history, direct per-retailer `CURRENT` items, a private versioned S3
bucket, and HTTPS CloudFront distribution. Only the production snapshot is
publicly readable through CloudFront. The extension still performs all retailer
matching locally; neither the collector nor the CDN receives browsing URLs.

The schedule starts disabled. The Lambda collects the explicitly reviewed
`config/retailers-live.json` mappings with at most 24 HTTP attempts, 20 pages,
one-second pacing, bounded retries, a ten-minute timeout, and one concurrent
invocation. Advertised discounts remain marked `catalog_advertised`; fees,
listing inventory, and averages are not invented. A missing retailer or failed
page aborts collection. Synthetic input is rejected by the AWS runtime.

## Local verification and package

```sh
python3 -m unittest tests/test_aws_runtime.py -v
python3 infra/package.py
cfn-lint infra/template.json
```

The ZIP includes only Python application modules and the live retailer catalog.
It excludes demos, local history, collected inputs, the Safari app and browser
assets. boto3/botocore are provided by the AWS Lambda Python runtime.

Tests use in-memory AWS doubles, not an AWS account. They cover explicit
no-inventory, partial/demo/stale rejection, immutable retry/conflict handling,
failed history/publication, initial/update publication races, current-state
monotonicity and unchanged offer expiry on retry.

## Deployment inputs and steps

Required inputs are an authenticated AWS profile, an explicitly chosen AWS region,
an existing private S3 artifact bucket in that region, a stack name, and an email
for operational/budget alerts. The deployment identity needs CloudFormation and
resource-provisioning permissions; none are stored in the extension or package.
These commands are templates: fill in the actual account-specific values first.

```sh
export AWS_PROFILE=your-profile
export AWS_REGION=your-region
export GIFTCARD_ARTIFACT_BUCKET=your-existing-private-artifact-bucket
export GIFTCARD_STACK=giftcard-discounts-test
export GIFTCARD_ALERT_EMAIL=your-alert-email

aws sts get-caller-identity
python3 infra/package.py
aws cloudformation package --template-file infra/template.json \
  --s3-bucket "$GIFTCARD_ARTIFACT_BUCKET" --s3-prefix "$GIFTCARD_STACK" \
  --output-template-file infra/packaged.json
aws cloudformation deploy --template-file infra/packaged.json \
  --stack-name "$GIFTCARD_STACK" --capabilities CAPABILITY_IAM \
  --parameter-overrides OpsEmail="$GIFTCARD_ALERT_EMAIL" EnableSchedule=false
aws cloudformation describe-stacks --stack-name "$GIFTCARD_STACK" \
  --query 'Stacks[0].Outputs'
```

Confirm the SNS email subscription. Invoke the returned `CollectorFunction`
synchronously and inspect both the AWS CLI `FunctionError` field and result file
before enabling the schedule. Fetch `SnapshotURL` and verify `demo: false`, source
timestamps, advertised discount labels, and that only configured domains appear.
Then set the extension's snapshot URL to that exact HTTPS output and run the real
Safari acceptance checklist. The CDN can retain the old snapshot for five minutes.

```sh
aws lambda invoke --function-name RETURNED_COLLECTOR_FUNCTION \
  --cli-binary-format raw-in-base64-out --payload '{}' infra/invocation.json
# After the live collection -> history -> CDN -> Safari check succeeds:
aws cloudformation deploy --template-file infra/packaged.json \
  --stack-name "$GIFTCARD_STACK" --capabilities CAPABILITY_IAM \
  --parameter-overrides OpsEmail="$GIFTCARD_ALERT_EMAIL" EnableSchedule=true
```

## Failure, cost and retention behavior

Candidates are fully normalized before history writes. Run and observation
identities are immutable. History is written before the S3 snapshot; a failed
write can leave retryable history, but never a partial published snapshot. S3
`If-Match`/`If-None-Match` conditions prevent competing invocations from replacing
a newer publication. Direct current-state keys update only after publication and
cannot move backwards. No DynamoDB scans or dynamic client read API are used.

Retries retain each observation's original time and expiry. Stale batches are
rejected. A verified complete no-inventory batch can clear offers; missing/failed
retrieval cannot. Provider exceptions can appear in Lambda error logs; response
bodies, sessions and browsing information are never deliberately logged.

Operational alerts cover Lambda errors, the failure queue, and no successful
publication for two daily periods. The latter is a daily-cadence freshness alarm;
adjust it if changing cadence. Logs expire after 14 days; failure messages after
14 days; noncurrent snapshot versions after 30 days. History and the snapshot
bucket are retained on stack deletion. Remove retained resources separately when
finished to stop their storage charges.

The stack creates an **account-wide** monthly cost budget, default USD 10, with an
email at 80% of actual spend. A budget is an alert, not a spending cap. Lambda,
DynamoDB history/PITR, S3, CloudFront, CloudWatch and alerts can incur usage charges.
History grows until explicitly archived/deleted. The rule is disabled initially
so the live smoke check controls when recurring collection begins.

## Optional GitHub deployment identity

Set all four optional parameters to enable an OIDC role:
`GitHubOidcProviderArn` (an existing GitHub OIDC provider), `GitHubRepository`
(`owner/repository`), `DeploymentExecutionRoleArn` (an existing CloudFormation
execution role), and `DeploymentArtifactBucketArn`. The role trusts only that
repository's protected `production` environment and `sts.amazonaws.com` audience.
It can manage this stack's changesets, upload under this stack's artifact prefix,
and pass only the supplied execution role to CloudFormation. Configure the GitHub
environment's approvals and use the returned `GitHubDeployRoleArn` in the workflow.
The execution role and its resource-provisioning permissions must be established
in the selected account; this template does not grant CI administrator access.

Reference for the publication primitive:
[S3 conditional writes](https://docs.aws.amazon.com/AmazonS3/latest/userguide/conditional-writes.html).
