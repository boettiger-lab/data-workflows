#!/bin/bash
# Orchestrate WDPA data processing workflow
# Usage: ./orchestrate.sh [all|parquet|pmtiles|hex|repartition|cleanup]

set -e

NAMESPACE="biodiversity"

# Function to wait for a job to complete
wait_for_job() {
    local job_name=$1
    local timeout=${2:-3600}  # Default 1 hour timeout
    local elapsed=0
    local interval=30
    
    echo "Waiting for job $job_name to complete..."
    
    while [ $elapsed -lt $timeout ]; do
        status=$(kubectl get job "$job_name" -n "$NAMESPACE" -o jsonpath='{.status.conditions[?(@.type=="Complete")].status}' 2>/dev/null || echo "")
        failed=$(kubectl get job "$job_name" -n "$NAMESPACE" -o jsonpath='{.status.conditions[?(@.type=="Failed")].status}' 2>/dev/null || echo "")
        
        if [ "$status" = "True" ]; then
            echo "✓ Job $job_name completed successfully"
            return 0
        elif [ "$failed" = "True" ]; then
            echo "✗ Job $job_name failed"
            kubectl logs "job/$job_name" -n "$NAMESPACE" --tail=50
            return 1
        fi
        
        sleep $interval
        elapsed=$((elapsed + interval))
        echo "  Still waiting... (${elapsed}s elapsed)"
    done
    
    echo "✗ Timeout waiting for job $job_name"
    return 1
}

# Function to delete job if it exists
delete_job_if_exists() {
    local job_name=$1
    if kubectl get job "$job_name" -n "$NAMESPACE" &>/dev/null; then
        echo "Deleting existing job $job_name..."
        kubectl delete job "$job_name" -n "$NAMESPACE"
    fi
}

# Function to run parquet generation
run_parquet() {
    echo "=== Step 1: Generate Parquet from GDB ==="
    delete_job_if_exists "wdpa-convert"
    kubectl apply -f wdpa/convert-job.yaml -n "$NAMESPACE"
    wait_for_job "wdpa-convert" 7200  # 2 hour timeout for large conversion
}

# Function to run pmtiles generation
run_pmtiles() {
    echo "=== Step 2: Generate PMTiles from GDB ==="
    delete_job_if_exists "wdpa-pmtiles"
    kubectl apply -f wdpa/pmtiles-job.yaml -n "$NAMESPACE"
    wait_for_job "wdpa-pmtiles" 7200  # 2 hour timeout
}

# Function to run hex generation
run_hex() {
    echo "=== Step 3: Generate H3 Hexes ==="
    delete_job_if_exists "wdpa-hex"
    kubectl apply -f wdpa/hex-job.yaml -n "$NAMESPACE"
    wait_for_job "wdpa-hex" 14400  # 4 hour timeout for hex processing
}

# Function to run repartitioning
run_repartition() {
    echo "=== Step 4: Repartition Data ==="
    delete_job_if_exists "wdpa-repartition"
    kubectl apply -f wdpa/repartition-job.yaml -n "$NAMESPACE"
    
    if wait_for_job "wdpa-repartition" 3600; then
        echo "Repartitioning successful, cleaning up chunks directory..."
        cleanup_chunks
    else
        echo "Repartitioning failed, keeping chunks directory for debugging"
        return 1
    fi
}

# Function to cleanup chunks directory
cleanup_chunks() {
    echo "=== Cleanup: Removing chunks directory from S3 ==="
    
    # Use mc (minio client) or aws cli to remove chunks
    if command -v mc &> /dev/null; then
        mc rm --recursive --force s3/public-wdpa/chunks/ 2>/dev/null || true
        echo "✓ Chunks directory removed (mc)"
    elif command -v aws &> /dev/null; then
        aws s3 rm s3://public-wdpa/chunks/ --recursive --endpoint-url https://s3-west.nrp-nautilus.io 2>/dev/null || true
        echo "✓ Chunks directory removed (aws)"
    else
        echo "⚠ Neither mc nor aws cli found, skipping cleanup"
        echo "  Run manually: mc rm --recursive --force s3/public-wdpa/chunks/"
    fi
}

# Function to run full workflow
run_all() {
    echo "======================================"
    echo "WDPA Data Processing Workflow"
    echo "======================================"
    echo ""
    
    # Run parquet and pmtiles in parallel since pmtiles now reads from GDB
    echo "Starting parquet and pmtiles generation in parallel..."
    run_parquet &
    PARQUET_PID=$!
    
    run_pmtiles &
    PMTILES_PID=$!
    
    # Wait for both to complete
    wait $PARQUET_PID
    PARQUET_STATUS=$?
    
    wait $PMTILES_PID
    PMTILES_STATUS=$?
    
    if [ $PARQUET_STATUS -ne 0 ]; then
        echo "✗ Parquet generation failed, aborting workflow"
        exit 1
    fi
    
    if [ $PMTILES_STATUS -ne 0 ]; then
        echo "⚠ PMTiles generation failed, but continuing with hex processing"
    fi
    
    # Run hex generation (requires parquet)
    run_hex || {
        echo "✗ Hex generation failed, aborting workflow"
        exit 1
    }
    
    # Run repartitioning (which includes cleanup on success)
    run_repartition || {
        echo "✗ Repartitioning failed"
        exit 1
    }
    
    echo ""
    echo "======================================"
    echo "✓ Workflow completed successfully!"
    echo "======================================"
}

# Main script logic
case "${1:-all}" in
    all)
        run_all
        ;;
    parquet)
        run_parquet
        ;;
    pmtiles)
        run_pmtiles
        ;;
    hex)
        run_hex
        ;;
    repartition)
        run_repartition
        ;;
    cleanup)
        cleanup_chunks
        ;;
    *)
        echo "Usage: $0 [all|parquet|pmtiles|hex|repartition|cleanup]"
        echo ""
        echo "Commands:"
        echo "  all         - Run complete workflow (default)"
        echo "  parquet     - Generate parquet from GDB only"
        echo "  pmtiles     - Generate PMTiles from GDB only"
        echo "  hex         - Generate H3 hexes only"
        echo "  repartition - Repartition hex data (includes cleanup on success)"
        echo "  cleanup     - Remove chunks directory from S3"
        exit 1
        ;;
esac
