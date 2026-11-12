<#
Remove everything deploy.ps1 created that costs money (service, load balancer, image repo, secret, build resources).
The shared ECS IAM roles are free and left in place for reuse.      .\deploy\teardown.ps1 -Region ap-south-1
#>
param(
    [string]$Region = $(if ($env:AWS_REGION) { $env:AWS_REGION } else { "ap-south-1" }),
    [string]$AppName = "hr-copilot"
)
$env:AWS_PAGER = ""
$Account = (aws sts get-caller-identity --query Account --output text).Trim()
$ServiceArn = "arn:aws:ecs:${Region}:${Account}:service/default/$AppName"

Write-Host "Deleting ECS Express service (also removes its load balancer, certificate, target groups and security groups)..."
aws ecs delete-express-gateway-service --service-arn $ServiceArn --region $Region | Out-Null
Write-Host "Deleting ECR repository and images..."
aws ecr delete-repository --repository-name $AppName --force --region $Region | Out-Null
Write-Host "Deleting secret..."
aws secretsmanager delete-secret --secret-id "$AppName/openai-api-key" --force-delete-without-recovery --region $Region | Out-Null
aws iam delete-role-policy --role-name ecsTaskExecutionRole --policy-name "$AppName-read-openai-secret" 2>$null

# Only present if you deployed with -UseCodeBuild
Write-Host "Deleting CodeBuild project, build bucket and role (if any)..."
aws codebuild delete-project --name "$AppName-build" --region $Region 2>$null | Out-Null
aws s3 rb "s3://$AppName-build-$Account-$Region" --force --region $Region 2>$null | Out-Null
aws iam delete-role-policy --role-name "$AppName-codebuild-role" --policy-name "$AppName-codebuild" 2>$null
aws iam delete-role --role-name "$AppName-codebuild-role" 2>$null

Write-Host "Done. The service takes a few minutes to drain. CloudWatch log groups for $AppName are kept; delete them in the console if you like."
