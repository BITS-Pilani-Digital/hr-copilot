<#
Deploy the HR Copilot to a public HTTPS URL with Amazon ECS Express Mode.

  Docker image -> Amazon ECR -> ECS Express Mode service (Fargate + ALB + HTTPS + autoscaling, all managed)

Prereqs: AWS CLI v2 configured (aws configure / aws sso login), OPENAI_API_KEY in $env or .env, a default VPC in the
region, and EITHER Docker running locally OR -UseCodeBuild (image is built in AWS CodeBuild, no Docker needed).
Run from the hr-copilot folder:   .\deploy\deploy.ps1 -Region ap-south-1 [-UseCodeBuild]
Re-running the script redeploys a new image to the same service.
#>
param(
    [string]$Region = $(if ($env:AWS_REGION) { $env:AWS_REGION } else { "ap-south-1" }),
    [string]$AppName = "hr-copilot",
    [string]$ChatModel = "gpt-4.1-mini",
    [switch]$UseCodeBuild
)
$ErrorActionPreference = "Stop"
$env:AWS_PAGER = ""
$Root = Split-Path $PSScriptRoot -Parent
$Tmp = New-Item -ItemType Directory -Force (Join-Path ([IO.Path]::GetTempPath()) "$AppName-deploy")

$AwsCli = (Get-Command aws -CommandType Application | Select-Object -First 1).Source  # the real CLI, not the Aws function below
function Aws { & $AwsCli @args --region $Region; if ($LASTEXITCODE) { throw "aws $($args[0]) $($args[1]) failed" } }
function AwsQuiet { & $AwsCli @args --region $Region 2>$null; $LASTEXITCODE -eq 0 }
function WriteJson($name, $obj) { $p = Join-Path $Tmp $name; $obj | ConvertTo-Json -Depth 10 | Set-Content -Encoding ascii $p; "file://$p" }

function Build-WithCodeBuild {
    # Zip the build context (same exclusions as .dockerignore), upload to S3, build + push in CodeBuild.
    $bucket = "$AppName-build-$Account-$Region"
    if (-not (AwsQuiet s3api head-bucket --bucket $bucket)) {
        Aws s3api create-bucket --bucket $bucket --create-bucket-configuration "LocationConstraint=$Region" | Out-Null
    }
    $zip = Join-Path $Tmp "source.zip"
    Remove-Item $zip -ErrorAction SilentlyContinue
    Add-Type -AssemblyName System.IO.Compression, System.IO.Compression.FileSystem
    $archive = [IO.Compression.ZipFile]::Open($zip, "Create")
    try {
        Get-ChildItem $Root -Recurse -File | ForEach-Object {
            $rel = $_.FullName.Substring($Root.Length + 1).Replace('\', '/')
            if ($rel -notmatch '^(\.env$|\.venv/|tests/|scripts/|deploy/|slides/|\.git/|\.pytest_cache/|data/requests\.json$)' -and
                $rel -notmatch '__pycache__/') {
                [void][IO.Compression.ZipFileExtensions]::CreateEntryFromFile($archive, $_.FullName, $rel)
            }
        }
    } finally { $archive.Dispose() }
    Aws s3 cp $zip "s3://$bucket/source.zip" --only-show-errors

    $role = "$AppName-codebuild-role"
    if (-not (AwsQuiet iam get-role --role-name $role)) {
        $trust = WriteJson "codebuild-trust.json" @{ Version = "2012-10-17"; Statement = @(@{
            Effect = "Allow"; Principal = @{ Service = "codebuild.amazonaws.com" }; Action = "sts:AssumeRole" }) }
        Aws iam create-role --role-name $role --assume-role-policy-document $trust | Out-Null
        $newRole = $true
    }
    $policy = WriteJson "codebuild-policy.json" @{ Version = "2012-10-17"; Statement = @(
        @{ Effect = "Allow"; Action = @("logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"); Resource = "*" },
        @{ Effect = "Allow"; Action = @("s3:GetObject", "s3:GetObjectVersion"); Resource = "arn:aws:s3:::$bucket/*" },
        @{ Effect = "Allow"; Action = "ecr:GetAuthorizationToken"; Resource = "*" },
        @{ Effect = "Allow"; Action = @("ecr:BatchCheckLayerAvailability", "ecr:InitiateLayerUpload", "ecr:UploadLayerPart",
            "ecr:CompleteLayerUpload", "ecr:PutImage", "ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer")
           Resource = "arn:aws:ecr:${Region}:${Account}:repository/$AppName" }) }
    Aws iam put-role-policy --role-name $role --policy-name "$AppName-codebuild" --policy-document $policy
    $roleArn = (Aws iam get-role --role-name $role --query Role.Arn --output text).Trim()
    if ($newRole) { Write-Host "New CodeBuild role - waiting 15s for propagation"; Start-Sleep 15 }

    $buildspec = @"
version: 0.2
phases:
  pre_build:
    commands:
      - aws ecr get-login-password --region $Region | docker login --username AWS --password-stdin $Registry
  build:
    commands:
      - docker build --platform linux/amd64 -t $Image .
  post_build:
    commands:
      - docker push $Image
"@
    $project = @{ name = "$AppName-build"; serviceRole = $roleArn
        source = @{ type = "S3"; location = "$bucket/source.zip"; buildspec = $buildspec }
        artifacts = @{ type = "NO_ARTIFACTS" }
        environment = @{ type = "LINUX_CONTAINER"; image = "aws/codebuild/standard:7.0"; computeType = "BUILD_GENERAL1_SMALL"
                         privilegedMode = $true } }
    $projectFile = WriteJson "codebuild-project.json" $project
    $exists = & $AwsCli codebuild batch-get-projects --names "$AppName-build" --region $Region --query "projects[0].name" --output text 2>$null
    if ("$exists".Trim() -eq "$AppName-build") { Aws codebuild update-project --cli-input-json $projectFile | Out-Null }
    else { Aws codebuild create-project --cli-input-json $projectFile | Out-Null }

    $buildId = (Aws codebuild start-build --project-name "$AppName-build" --query build.id --output text).Trim()
    Write-Host "CodeBuild $buildId started"
    do {
        Start-Sleep 10
        $b = Aws codebuild batch-get-builds --ids $buildId --query "builds[0].[buildStatus,currentPhase]" --output text
        Write-Host "  $b"
    } while ($b -match "IN_PROGRESS")
    if ($b -notmatch "^SUCCEEDED") { throw "CodeBuild failed - see the build logs in the CodeBuild console ($buildId)" }
}

if (-not $env:OPENAI_API_KEY -and (Test-Path (Join-Path $Root ".env"))) {
    $line = Get-Content (Join-Path $Root ".env") | Where-Object { $_ -match '^\s*OPENAI_API_KEY\s*=' } | Select-Object -First 1
    if ($line) { $env:OPENAI_API_KEY = ($line -split '=', 2)[1].Trim().Trim('"') }
}
if (-not $env:OPENAI_API_KEY) { throw "Set `$env:OPENAI_API_KEY (or add it to .env) first." }
$Account = (Aws sts get-caller-identity --query Account --output text).Trim()
$Registry = "$Account.dkr.ecr.$Region.amazonaws.com"
$Tag = Get-Date -Format "yyyyMMddHHmmss"
$Image = "$Registry/${AppName}:$Tag"
Write-Host "Account $Account | Region $Region | Image $Image" -ForegroundColor Cyan

# 1. Container registry + image
Write-Host "`n[1/5] Building and pushing image" -ForegroundColor Cyan
if (-not (AwsQuiet ecr describe-repositories --repository-names $AppName)) {
    Aws ecr create-repository --repository-name $AppName --image-scanning-configuration scanOnPush=true | Out-Null
}
if ($UseCodeBuild) {
    Build-WithCodeBuild
} else {
    Aws ecr get-login-password | docker login --username AWS --password-stdin $Registry
    if ($LASTEXITCODE) { throw "docker login failed" }
    docker build --platform linux/amd64 -t $Image $Root; if ($LASTEXITCODE) { throw "docker build failed" }
    docker push $Image; if ($LASTEXITCODE) { throw "docker push failed" }
}

# 2. OpenAI key -> Secrets Manager (never baked into the image or passed as plain env var)
Write-Host "`n[2/5] Storing OpenAI key in Secrets Manager" -ForegroundColor Cyan
$SecretName = "$AppName/openai-api-key"
$SecretFile = Join-Path $Tmp "secret.txt"
[IO.File]::WriteAllText($SecretFile, $env:OPENAI_API_KEY)
try {
    if (AwsQuiet secretsmanager describe-secret --secret-id $SecretName) {
        Aws secretsmanager put-secret-value --secret-id $SecretName --secret-string "file://$SecretFile" | Out-Null
    } else {
        Aws secretsmanager create-secret --name $SecretName --secret-string "file://$SecretFile" | Out-Null
    }
} finally { Remove-Item $SecretFile -Force }
$SecretArn = (Aws secretsmanager describe-secret --secret-id $SecretName --query ARN --output text).Trim()

# 3. IAM roles (task execution role + Express infrastructure role)
Write-Host "`n[3/5] Ensuring IAM roles" -ForegroundColor Cyan
function EnsureRole($name, $service, $policyArn) {
    if (-not (AwsQuiet iam get-role --role-name $name)) {
        $trust = WriteJson "$name-trust.json" @{ Version = "2012-10-17"; Statement = @(@{
            Effect = "Allow"; Principal = @{ Service = $service }; Action = "sts:AssumeRole" }) }
        Aws iam create-role --role-name $name --assume-role-policy-document $trust | Out-Null
        $script:NewRole = $true
    }
    Aws iam attach-role-policy --role-name $name --policy-arn $policyArn
    (Aws iam get-role --role-name $name --query Role.Arn --output text).Trim()
}
$script:NewRole = $false
$ExecRoleArn = EnsureRole "ecsTaskExecutionRole" "ecs-tasks.amazonaws.com" "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
$InfraRoleArn = EnsureRole "ecsInfrastructureRoleForExpressServices" "ecs.amazonaws.com" "arn:aws:iam::aws:policy/service-role/AmazonECSInfrastructureRoleforExpressGatewayServices"
$secretPolicy = WriteJson "secret-policy.json" @{ Version = "2012-10-17"; Statement = @(@{
    Effect = "Allow"; Action = "secretsmanager:GetSecretValue"; Resource = $SecretArn }) }
Aws iam put-role-policy --role-name ecsTaskExecutionRole --policy-name "$AppName-read-openai-secret" --policy-document $secretPolicy
if ($script:NewRole) { Write-Host "New IAM roles created - waiting 20s for propagation"; Start-Sleep 20 }

# 4. Create or update the Express Mode service
Write-Host "`n[4/5] Deploying ECS Express Mode service" -ForegroundColor Cyan
$container = WriteJson "container.json" @{
    image = $Image; containerPort = 8501
    environment = @(@{ name = "CHAT_MODEL"; value = $ChatModel })
    secrets = @(@{ name = "OPENAI_API_KEY"; valueFrom = $SecretArn })
}
$ServiceArn = "arn:aws:ecs:${Region}:${Account}:service/default/$AppName"
$status = & $AwsCli ecs describe-express-gateway-service --service-arn $ServiceArn --region $Region `
    --query "service.status.statusCode" --output text 2>$null
if ($LASTEXITCODE) { $status = "" }
if ("$status".Trim() -eq "ACTIVE") {
    Aws ecs update-express-gateway-service --service-arn $ServiceArn --primary-container $container | Out-Null
} else {
    # One task keeps Streamlit sessions and the demo JSON store consistent; raise maxTaskCount for real traffic.
    Aws ecs create-express-gateway-service --service-name $AppName `
        --execution-role-arn $ExecRoleArn --infrastructure-role-arn $InfraRoleArn `
        --primary-container $container --health-check-path "/_stcore/health" `
        --cpu 1024 --memory 2048 --scaling-target "minTaskCount=1,maxTaskCount=1" | Out-Null
}
Write-Host "Provisioning load balancer, certificate and task (usually 4-8 minutes)..."
Start-Sleep 30  # let the new deployment register before waiting on it
Aws ecs wait services-stable --cluster default --services $AppName

# 5. Wait until the public URL answers, then print it
Write-Host "`n[5/5] Service URL" -ForegroundColor Cyan
$Url = (Aws ecs describe-express-gateway-service --service-arn $ServiceArn `
    --query "service.activeConfigurations[0].ingressPaths[0].endpoint" --output text).Trim()
if ($Url -notmatch "^https?://") { $Url = "https://$Url" }
foreach ($i in 1..30) {
    try { if ((Invoke-WebRequest "$Url/_stcore/health" -UseBasicParsing -TimeoutSec 10).StatusCode -eq 200) { break } }
    catch { Start-Sleep 10 }
}
Write-Host "Live at: $Url" -ForegroundColor Green
Write-Host "Tear down when finished:  .\deploy\teardown.ps1 -Region $Region"
