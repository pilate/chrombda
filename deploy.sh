#!/usr/bin/env bash
set -euo pipefail

STACK_PREFIX="chrombda"
ECR_REPO_NAME="chrombda"

usage() {
    echo "Usage: $0 <environment>"
    echo "  environment: dev | staging | prod"
    exit 1
}

if [[ $# -lt 1 ]]; then
    usage
fi

ENV="$1"
if [[ ! "$ENV" =~ ^(dev|staging|prod)$ ]]; then
    echo "Error: environment must be one of: dev, staging, prod"
    exit 1
fi

STACK_NAME="${STACK_PREFIX}-${ENV}"
REGION="${AWS_DEFAULT_REGION:-$(aws configure get region 2>/dev/null || echo "us-east-1")}"
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ECR_URI="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com"
IMAGE_REPO="${ECR_URI}/${ECR_REPO_NAME}"
IMAGE_TAG="${ENV}-$(git rev-parse --short HEAD 2>/dev/null || date +%Y%m%d%H%M%S)"
IMAGE_URI="${IMAGE_REPO}:${IMAGE_TAG}"

echo "==> Deploying ${STACK_NAME} in ${REGION}"
echo "    Image: ${IMAGE_URI}"

# Create ECR repository if it doesn't exist
if ! aws ecr describe-repositories --repository-names "${ECR_REPO_NAME}" --region "${REGION}" &>/dev/null; then
    echo "==> Creating ECR repository: ${ECR_REPO_NAME}"
    aws ecr create-repository \
        --repository-name "${ECR_REPO_NAME}" \
        --region "${REGION}" \
        --image-scanning-configuration scanOnPush=true
fi

# Log in to ECR
echo "==> Logging in to ECR"
aws ecr get-login-password --region "${REGION}" | \
    docker login --username AWS --password-stdin "${ECR_URI}"

# Build and push
echo "==> Building Docker image"
docker build --platform linux/amd64 --provenance=false -t "${IMAGE_URI}" .

echo "==> Pushing image to ECR"
docker push "${IMAGE_URI}"

# Deploy CloudFormation stack
echo "==> Deploying CloudFormation stack: ${STACK_NAME}"
aws cloudformation deploy \
    --stack-name "${STACK_NAME}" \
    --template-file template.yaml \
    --parameter-overrides \
        "Environment=${ENV}" \
        "ImageUri=${IMAGE_URI}" \
    --capabilities CAPABILITY_NAMED_IAM \
    --region "${REGION}"

# Print outputs
echo ""
echo "==> Deployment complete!"
aws cloudformation describe-stacks \
    --stack-name "${STACK_NAME}" \
    --region "${REGION}" \
    --query "Stacks[0].Outputs" \
    --output table
