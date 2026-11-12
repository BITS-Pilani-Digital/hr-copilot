#!/usr/bin/env bash
# Deploy the HR Copilot to Amazon ECS Express Mode (macOS/Linux version of deploy.ps1).
#   REGION=ap-south-1 OPENAI_API_KEY=sk-... ./deploy/deploy.sh
set -euo pipefail
export AWS_PAGER=""
REGION="${REGION:-${AWS_REGION:-ap-south-1}}"
APP="${APP:-hr-copilot}"
CHAT_MODEL="${CHAT_MODEL:-gpt-4.1-mini}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
: "${OPENAI_API_KEY:?Set OPENAI_API_KEY first}"

ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
REGISTRY="$ACCOUNT.dkr.ecr.$REGION.amazonaws.com"
IMAGE="$REGISTRY/$APP:$(date +%Y%m%d%H%M%S)"
echo "Account $ACCOUNT | Region $REGION | Image $IMAGE"

echo "[1/5] Building and pushing image"
aws ecr describe-repositories --repository-names "$APP" --region "$REGION" >/dev/null 2>&1 ||
  aws ecr create-repository --repository-name "$APP" --image-scanning-configuration scanOnPush=true --region "$REGION" >/dev/null
aws ecr get-login-password --region "$REGION" | docker login --username AWS --password-stdin "$REGISTRY"
docker build --platform linux/amd64 -t "$IMAGE" "$ROOT"
docker push "$IMAGE"

echo "[2/5] Storing OpenAI key in Secrets Manager"
SECRET="$APP/openai-api-key"
if aws secretsmanager describe-secret --secret-id "$SECRET" --region "$REGION" >/dev/null 2>&1; then
  printf '%s' "$OPENAI_API_KEY" | aws secretsmanager put-secret-value --secret-id "$SECRET" --secret-string file:///dev/stdin --region "$REGION" >/dev/null
else
  printf '%s' "$OPENAI_API_KEY" | aws secretsmanager create-secret --name "$SECRET" --secret-string file:///dev/stdin --region "$REGION" >/dev/null
fi
SECRET_ARN=$(aws secretsmanager describe-secret --secret-id "$SECRET" --region "$REGION" --query ARN --output text)

echo "[3/5] Ensuring IAM roles"
NEW_ROLE=0
ensure_role() { # name service policy-arn
  if ! aws iam get-role --role-name "$1" >/dev/null 2>&1; then
    aws iam create-role --role-name "$1" --assume-role-policy-document \
      "{\"Version\":\"2012-10-17\",\"Statement\":[{\"Effect\":\"Allow\",\"Principal\":{\"Service\":\"$2\"},\"Action\":\"sts:AssumeRole\"}]}" >/dev/null
    NEW_ROLE=1
  fi
  aws iam attach-role-policy --role-name "$1" --policy-arn "$3"
}
ensure_role ecsTaskExecutionRole ecs-tasks.amazonaws.com arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy
ensure_role ecsInfrastructureRoleForExpressServices ecs.amazonaws.com arn:aws:iam::aws:policy/service-role/AmazonECSInfrastructureRoleforExpressGatewayServices
EXEC_ROLE=$(aws iam get-role --role-name ecsTaskExecutionRole --query Role.Arn --output text)
INFRA_ROLE=$(aws iam get-role --role-name ecsInfrastructureRoleForExpressServices --query Role.Arn --output text)
aws iam put-role-policy --role-name ecsTaskExecutionRole --policy-name "$APP-read-openai-secret" --policy-document \
  "{\"Version\":\"2012-10-17\",\"Statement\":[{\"Effect\":\"Allow\",\"Action\":\"secretsmanager:GetSecretValue\",\"Resource\":\"$SECRET_ARN\"}]}"
[ "$NEW_ROLE" = 1 ] && { echo "Waiting 20s for new IAM roles to propagate"; sleep 20; }

echo "[4/5] Deploying ECS Express Mode service"
CONTAINER="{\"image\":\"$IMAGE\",\"containerPort\":8501,\"environment\":[{\"name\":\"CHAT_MODEL\",\"value\":\"$CHAT_MODEL\"}],\"secrets\":[{\"name\":\"OPENAI_API_KEY\",\"valueFrom\":\"$SECRET_ARN\"}]}"
SERVICE_ARN="arn:aws:ecs:$REGION:$ACCOUNT:service/default/$APP"
STATUS=$(aws ecs describe-express-gateway-service --service-arn "$SERVICE_ARN" --region "$REGION" \
  --query service.status.statusCode --output text 2>/dev/null || true)
if [ "$STATUS" = "ACTIVE" ]; then
  aws ecs update-express-gateway-service --service-arn "$SERVICE_ARN" --primary-container "$CONTAINER" \
    --region "$REGION" >/dev/null
else
  aws ecs create-express-gateway-service --service-name "$APP" \
    --execution-role-arn "$EXEC_ROLE" --infrastructure-role-arn "$INFRA_ROLE" \
    --primary-container "$CONTAINER" --health-check-path "/_stcore/health" \
    --cpu 1024 --memory 2048 --scaling-target "minTaskCount=1,maxTaskCount=1" --region "$REGION" >/dev/null
fi
echo "Provisioning load balancer, certificate and task (usually 4-8 minutes)..."
sleep 30
aws ecs wait services-stable --cluster default --services "$APP" --region "$REGION"

echo "[5/5] Service URL"
URL=$(aws ecs describe-express-gateway-service --service-arn "$SERVICE_ARN" --region "$REGION" \
  --query "service.activeConfigurations[0].ingressPaths[0].endpoint" --output text)
case "$URL" in http*) ;; *) URL="https://$URL" ;; esac
for _ in $(seq 30); do curl -fsS -m 10 "$URL/_stcore/health" >/dev/null 2>&1 && break; sleep 10; done
echo "Live at: $URL"
echo "Tear down when finished: aws ecs delete-express-gateway-service --service-arn $SERVICE_ARN --region $REGION (see README)"
