#!/usr/bin/env bash
set -euo pipefail

usage() {
    echo "Usage: $0 <environment> <url> <schedule-expression>"
    echo ""
    echo "  environment:  dev | staging | prod"
    echo "  url:          URL to screenshot"
    echo "  schedule:     CloudWatch schedule expression"
    echo ""
    echo "Examples:"
    echo "  $0 dev https://example.com 'rate(1 hour)'"
    echo "  $0 prod https://example.com 'cron(0 */6 * * ? *)'"
    exit 1
}

if [[ $# -lt 3 ]]; then
    usage
fi

ENV="$1"
URL="$2"
SCHEDULE="$3"

if [[ ! "$ENV" =~ ^(dev|staging|prod)$ ]]; then
    echo "Error: environment must be one of: dev, staging, prod"
    exit 1
fi

REGION="${AWS_DEFAULT_REGION:-$(aws configure get region 2>/dev/null || echo "us-east-1")}"
STACK_NAME="chrombda-${ENV}"

# Get the Lambda ARN from the stack
FUNCTION_ARN=$(aws cloudformation describe-stacks \
    --stack-name "${STACK_NAME}" \
    --region "${REGION}" \
    --query "Stacks[0].Outputs[?OutputKey=='FunctionArn'].OutputValue" \
    --output text)

if [[ -z "$FUNCTION_ARN" || "$FUNCTION_ARN" == "None" ]]; then
    echo "Error: could not find chrombda function in stack ${STACK_NAME}"
    exit 1
fi

# Derive a rule name from the URL
URL_HASH=$(echo -n "$URL" | sha256sum | cut -c1-12)
RULE_NAME="chrombda-${ENV}-${URL_HASH}"

echo "==> Creating schedule rule: ${RULE_NAME}"
echo "    URL:      ${URL}"
echo "    Schedule: ${SCHEDULE}"
echo "    Function: ${FUNCTION_ARN}"

aws events put-rule \
    --name "${RULE_NAME}" \
    --schedule-expression "${SCHEDULE}" \
    --state ENABLED \
    --region "${REGION}"

TARGETS=$(jq -cn \
    --arg id "$RULE_NAME" \
    --arg arn "$FUNCTION_ARN" \
    --arg url "$URL" \
    '[{Id: $id, Arn: $arn, Input: ({source: "aws.events", detail: {url: $url}} | tostring)}]')

aws events put-targets \
    --rule "${RULE_NAME}" \
    --targets "${TARGETS}" \
    --region "${REGION}"

echo ""
echo "==> Done! Rule '${RULE_NAME}' created."
echo "    To remove: aws events remove-targets --rule ${RULE_NAME} --ids ${RULE_NAME} && aws events delete-rule --name ${RULE_NAME}"
