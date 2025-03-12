#!/bin/bash

if [ -z "$1" ]; then
    echo "Error: Secret ARN is required."
    echo "Usage: $0 <secret-arn>"
    echo "Example: $0 arn:aws:secretsmanager:region:account-id:secret:secret-name"
    exit 1
fi

SECRET_ARN="$1"

set -e  

echo "Retrieving secret with ARN: $SECRET_ARN"

SECRET_VALUE=$(aws secretsmanager get-secret-value \
  --secret-id "$SECRET_ARN" \
  --query "SecretString" \
  --output text)


export PGHOST=$(echo "$SECRET_VALUE" | jq -r '.host')
export PGPORT=$(echo "$SECRET_VALUE" | jq -r '.port')
export PGDATABASE=$(echo "$SECRET_VALUE" | jq -r '.dbname')
export PGUSER=$(echo "$SECRET_VALUE" | jq -r '.username')
export PGPASSWORD=$(echo "$SECRET_VALUE" | jq -r '.password')

export DATABASE_URL="postgresql://$PGUSER:$PGPASSWORD@$PGHOST:$PGPORT/$PGDATABASE"

echo "Environment variables set:"
echo "PGHOST=$PGHOST"
echo "PGPORT=$PGPORT"
echo "PGDATABASE=$PGDATABASE"
echo "PGUSER=$PGUSER"
echo "PGPASSWORD=********"
echo "DATABASE_URL=postgresql://$PGUSER:********@$PGHOST:$PGPORT/$PGDATABASE"

echo "Database credentials have been set as environment variables."
