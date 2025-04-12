#!/bin/bash

# Default values for flags
DO_INDEX_MANAGEMENT=false
DO_INGESTION=false
DO_SEARCH=false

# Parse command line arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    --prepare-index)
      DO_INDEX_MANAGEMENT=true
      shift
      ;;
    --ingest)
      DO_INGESTION=true
      shift
      ;;
    --search)
      DO_SEARCH=true
      shift
      ;;
    --endpoint)
      ENDPOINT="$2"
      shift 2
      ;;
    *)
      echo "Unknown option: $1"
      echo "Usage: $0 [--prepare-index] [--ingest] [--endpoint ENDPOINT]"
      exit 1
      ;;
  esac
done

# Use environment variable for endpoint if not provided as argument
if [ -z "$ENDPOINT" ]; then
  if [ -n "$AOSS_ENDPOINT" ]; then
    ENDPOINT="$AOSS_ENDPOINT"
    echo "Using endpoint from AOSS_ENDPOINT environment variable: $ENDPOINT"
  else
    echo "Error: Endpoint is required either as --endpoint argument or AOSS_ENDPOINT environment variable"
    echo "Usage: $0 [--prepare-index] [--ingest] [--endpoint ENDPOINT]"
    exit 1
  fi
fi

# Check if at least one operation is requested
if [ "$DO_INDEX_MANAGEMENT" = false ] && [ "$DO_INGESTION" = false ] && [ "$DO_SEARCH" == false ]; then
  echo "Error: Specify at least one operation (--prepare-index or --ingest)"
  echo "Usage: $0 [--prepare-index] [--ingest] [--endpoint ENDPOINT]"
  exit 1
fi


TIMESTAMP=$(date +%Y%m%d_%H%M%S)
# Configuration - use environment variables if available, otherwise use defaults
# TOTAL_VECTORS=${TOTAL_VECTORS:-10000000}         # Total vectors to ingest
TOTAL_VECTORS=${TOTAL_VECTORS:-10000000}         # Total vectors to ingest
BATCH_SIZE=${BATCH_SIZE:-1000000}                # Vectors per batch
SLEEP_TIME=${SLEEP_TIME:-120}                     # Sleep time in seconds between batches
PARAMS_FILE=${PARAMS_FILE:-"case2_100M_128d_params.json"}
DISTRIBUTION_VERSION=${DISTRIBUTION_VERSION:-"2.17.0-beta"}
AWS_REGION=${AWS_REGION:-"us-east-1"}
SCENARIO_BASE=${SCENARIO:-"10M_128D_217beta"}
SCENARIO="${SCENARIO_BASE}_${TIMESTAMP}"  # Add timestamp to scenario name
VERSION_TAG=${VERSION_TAG:-"217-beta"}

echo "Configuration:"
echo "ENDPOINT: $ENDPOINT"
echo "TOTAL_VECTORS: $TOTAL_VECTORS"
echo "BATCH_SIZE: $BATCH_SIZE"
echo "PARAMS_FILE: $PARAMS_FILE"
echo "DISTRIBUTION_VERSION: $DISTRIBUTION_VERSION"
echo "AWS_REGION: $AWS_REGION"

# Use the exact client options that work in your command
CLIENT_OPTIONS="max_retries:5,retry_on_timeout:true,retry_on_error:True,timeout:900,use_ssl:True,verify_certs:True,region:$AWS_REGION,amazon_aws_log_in:environment"

# Function to update the parameters file with new offset and batch size
update_params() {
  local offset=$1
  local batch_size=$2

  # Create a temporary file with updated parameters
  jq ".starting_offset = $offset | .target_index_num_vectors = $batch_size" $PARAMS_FILE > tmp.json
  mv tmp.json $PARAMS_FILE

  echo "Updated parameters: starting_offset=$offset, target_index_num_vectors=$batch_size"
}

# Function to check index status
check_index_status() {
#   ada credentials update --account=875378785276 --role=Admin --once
  echo "Checking index status..."
  awscurl --service aoss "${ENDPOINT}/_cat/indices?v"
}

OSB_START_TIME=$(TZ=America/Los_Angeles date "+%Y-%m-%d %H:%M:%S PDT")
# Handle index preparation (delete and create)
if [ "$DO_INDEX_MANAGEMENT" = true ]; then
  echo "==================================================================="
  echo "Preparing index (delete and create)"
  echo "==================================================================="

  results_file="$HOME/${SCENARIO}_prepare_index.out"
  # Use direct command execution without variable expansion for the base command
  opensearch-benchmark execute-test \
    --workload=vectorsearch \
    --target-hosts=$ENDPOINT:443 \
    --client-options="$CLIENT_OPTIONS" \
    --workload-params=$PARAMS_FILE \
    --test-procedure=knn-no-train-test-small \
    --include-tasks="delete-target-index,create-target-index" \
    --pipeline=benchmark-only \
    --kill-running-processes \
    --workload-repository=$HOME/opensearch-benchmark-workloads \
    --distribution-version=$DISTRIBUTION_VERSION \
    --user-tag="operation:prepare-index,scenario:$SCENARIO,version:$VERSION_TAG" \
    --results-file="$results_file"

  # Check status after index creation
  check_index_status
  echo "⏳ Sleeping 20 seconds to allow result file to flush..."
  sleep 20
  OSB_START_TIME="$OSB_START_TIME" python3 ingest_metadata.py "$PARAMS_FILE" "$results_file" "$SCENARIO"

  echo "Index preparation complete"
  echo "==================================================================="
fi

# Handle data ingestion
if [ "$DO_INGESTION" = true ]; then
  echo "Starting data ingestion process..."

  # Main loop to process batches
  for ((offset=0; offset<TOTAL_VECTORS; offset+=BATCH_SIZE)); do
    batch_num=$((offset/BATCH_SIZE + 1))
    total_batches=$((TOTAL_VECTORS/BATCH_SIZE))

    echo "==================================================================="
    echo "Starting batch $batch_num of $total_batches (offset: $offset)"
    echo "==================================================================="

    # Update parameters file
    update_params $offset $BATCH_SIZE

    # Build the results file name with the batch number
    results_file="~/${SCENARIO}_indexing_batch_${batch_num}.out"

    # Build the user tag with the batch number
    user_tag="scenario:$SCENARIO,procedure:knn-batch-ingest,version:$VERSION_TAG,batch-ingest:true,batch:${batch_num}_of_${total_batches},dataset:100M"

    echo "Executing benchmark for batch $batch_num..."
    opensearch-benchmark execute-test \
      --workload=vectorsearch \
      --target-hosts=$ENDPOINT:443 \
      --client-options="$CLIENT_OPTIONS" \
      --workload-params=$PARAMS_FILE \
      --test-procedure=knn-no-train-test-small \
      --include-tasks="custom-vector-bulk-offset" \
      --pipeline=benchmark-only \
      --kill-running-processes \
      --workload-repository=$HOME/opensearch-benchmark-workloads \
      --distribution-version=$DISTRIBUTION_VERSION \
      --user-tag="$user_tag" \
      --results-file="$results_file"

    # Check the status after completion
    check_index_status

    # Sleep between batches (if not the last batch)
    if [ $((offset + BATCH_SIZE)) -lt $TOTAL_VECTORS ]; then
      echo "Sleeping for $SLEEP_TIME seconds before starting next batch..."
      sleep $SLEEP_TIME
    fi
  done

  echo "==================================================================="
  echo "All batches completed. Final index status:"
  check_index_status
  echo "==================================================================="
fi

# Handle data ingestion
if [ "$DO_SEARCH" = true ]; then
  echo "Starting search process..."

  echo "==================================================================="
  echo "Starting search"
  echo "==================================================================="

  results_file="~/${SCENARIO}_search.out"

  opensearch-benchmark execute-test \
    --workload=vectorsearch \
    --target-hosts=$ENDPOINT:443 \
    --client-options="$CLIENT_OPTIONS" \
    --workload-params=$PARAMS_FILE \
    --test-procedure=no-train-test-aoss \
    --include-tasks="prod-queries" \
    --pipeline=benchmark-only \
    --kill-running-processes \
    --workload-repository=$HOME/opensearch-benchmark-workloads \
    --distribution-version=$DISTRIBUTION_VERSION \
    --results-file="$results_file"

    # Check the status after completion
    check_index_status
    echo "⏳ Sleeping 20 seconds to allow result file to flush..."
    sleep 20
    OSB_START_TIME="$OSB_START_TIME" python3 ingest_metadata.py "$PARAMS_FILE" "$results_file" "$SCENARIO"

  echo "==================================================================="
  echo "Search completed. Final index status:"
  check_index_status
  echo "==================================================================="
fi

echo "Script execution complete"
