#!/usr/bin/env python3
"""
Robust tier escalation - checks completed job and creates next tier job.
Run this manually after each tier completes. Stateless and resumable.
"""
import subprocess
import json
import yaml
import sys
from typing import Set, List

def get_failed_indices(job_name: str, namespace: str) -> Set[int]:
    """Get failed indices from a completed job."""
    result = subprocess.run(
        ["kubectl", "get", "job", job_name, "-n", namespace, "-o", "json"],
        capture_output=True,
        text=True
    )
    
    if result.returncode != 0:
        print(f"Error: Job {job_name} not found in namespace {namespace}")
        return set()
    
    job_status = json.loads(result.stdout)
    status = job_status.get("status", {})
    
    succeeded = status.get("succeeded", 0)
    failed = status.get("failed", 0)
    completions = job_status["spec"]["completions"]
    failed_indexes_str = status.get("failedIndexes", "")
    
    print(f"\nJob: {job_name}")
    print(f"Status: {succeeded}/{completions} succeeded, {failed} failed")
    
    if not failed_indexes_str:
        print("✅ All indices succeeded!")
        return set()
    
    # Parse failed indexes
    failed_completion_indices = set()
    for part in failed_indexes_str.split(","):
        part = part.strip()
        if "-" in part:
            start, end = part.split("-")
            failed_completion_indices.update(range(int(start), int(end) + 1))
        elif part:
            failed_completion_indices.add(int(part))
    
    # Get the INDEX_MAPPING from job spec to map back to original indices
    job_status_full = json.loads(result.stdout)
    containers = job_status_full.get("spec", {}).get("template", {}).get("spec", {}).get("containers", [])
    
    for container in containers:
        for env in container.get("env", []):
            if env["name"] == "INDEX_MAPPING":
                index_mapping = json.loads(env["value"])
                failed_original = {index_mapping[i] for i in failed_completion_indices 
                                 if i < len(index_mapping)}
                print(f"Mapped {len(failed_completion_indices)} completion indices to {len(failed_original)} original indices")
                print(f"Failed indices: {sorted(list(failed_original))}")
                return failed_original
    
    # Fallback: assume identity mapping (for tier 0 where there's no INDEX_MAPPING)
    print(f"⚠️  No INDEX_MAPPING found (tier 0?), using completion indices directly")
    print(f"Failed completion indices: {sorted(list(failed_completion_indices))}")
    return failed_completion_indices


def create_next_tier_job(failed_indices: Set[int], current_tier: int, 
                        config_file: str, namespace: str) -> str:
    """Create job manifest for next tier with failed indices."""
    
    with open(config_file) as f:
        config = yaml.safe_load(f)
    
    next_tier = current_tier + 1
    if next_tier >= len(config["resource_tiers"]):
        print(f"❌ No more tiers available (max tier: {len(config['resource_tiers']) - 1})")
        return None
    
    tier = config["resource_tiers"][next_tier]
    job_name = f"{config['job_name_prefix']}-tier{next_tier}"
    
    # Check if this is a full range (Tier 0)
    is_full_range = (current_tier == -1)
    
    print(f"\n🚀 Creating Tier {next_tier} job: {job_name}")
    print(f"   Memory: {tier['memory']}, CPU: {tier['cpu']}")
    print(f"   Indices to process: {len(failed_indices)}")
    if is_full_range:
        print(f"   Using direct index mapping (0-{len(failed_indices)-1})")
    
    # Build environment variables
    env_vars, use_direct = _build_env_vars(failed_indices, next_tier, config, is_full_range)
    
    # Build job manifest
    manifest = {
        "apiVersion": "batch/v1",
        "kind": "Job",
        "metadata": {
            "name": job_name,
            "namespace": namespace,
            "labels": {
                "app": config["job_name_prefix"],
                "tier": str(next_tier)
            }
        },
        "spec": {
            "completions": len(failed_indices),
            "parallelism": min(len(failed_indices), config.get("parallelism", 50)),
            "completionMode": "Indexed",
            "backoffLimitPerIndex": 0,  # Don't retry individual indices
            "podFailurePolicy": {
                "rules": [
                    {
                        "action": "Ignore",  # Ignore pod disruptions (evictions, preemptions)
                        "onPodConditions": [
                            {"type": "DisruptionTarget"}
                        ]
                    }
                    # All other failures automatically trigger FailIndex with backoffLimitPerIndex: 0
                ]
            },
            "ttlSecondsAfterFinished": config.get("ttl_seconds_after_finished", 3600),
            "template": {
                "metadata": {
                    "labels": {
                        "app": config["job_name_prefix"],
                        "tier": str(next_tier)
                    }
                },
                "spec": {
                    "restartPolicy": "Never",
                    "volumes": [{"name": "repo", "emptyDir": {}}] if config.get("init_container", {}).get("enabled") else [],
                    "containers": [{
                        "name": "worker",
                        "image": config["container_image"],
                        "imagePullPolicy": config.get("image_pull_policy", "Always"),
                        "workingDir": config.get("working_directory", "/workspace/datasets"),
                        "command": config["command"],
                        "volumeMounts": [{"name": "repo", "mountPath": "/workspace"}] if config.get("init_container", {}).get("enabled") else [],
                        "env": env_vars,
                        "resources": {
                            "requests": {"memory": tier["memory"], "cpu": tier["cpu"]},
                            "limits": {"memory": tier["memory"], "cpu": tier["cpu"]}
                        }
                    }]
                }
            }
        }
    }
    
    # Add init container if needed
    if config.get("init_container", {}).get("enabled"):
        init_config = config["init_container"]
        manifest["spec"]["template"]["spec"]["initContainers"] = [{
            "name": "git-clone",
            "image": "alpine/git:2.45.2",
            "imagePullPolicy": "IfNotPresent",
            "command": ["sh", "-lc", 
                f"git clone --depth {init_config.get('clone_depth', 1)} \"{init_config.get('repo_url')}\" /workspace/datasets"],
            "volumeMounts": [{"name": "repo", "mountPath": "/workspace"}],
            "resources": {"requests": {"cpu": "1", "memory": "1Gi"}, "limits": {"cpu": "1", "memory": "1Gi"}}
        }]
    
    # Add node affinity if needed
    if config.get("avoid_gpu_nodes"):
        manifest["spec"]["template"]["spec"]["affinity"] = {
            "nodeAffinity": {
                "requiredDuringSchedulingIgnoredDuringExecution": {
                    "nodeSelectorTerms": [{
                        "matchExpressions": [{
                            "key": "feature.node.kubernetes.io/pci-10de.present",
                            "operator": "NotIn",
                            "values": ["true"]
                        }]
                    }]
                }
            }
        }
    
    # Save manifest with literal block style for multi-line strings
    manifest_file = f"{job_name}.yaml"
    
    # Custom representer to use literal block style (|) only for long multi-line strings
    def str_representer(dumper, data):
        if '\n' in data and len(data) > 100:  # Only use literal style for long multi-line strings
            return dumper.represent_scalar('tag:yaml.org,2002:str', data, style='|')
        return dumper.represent_scalar('tag:yaml.org,2002:str', data)
    
    yaml.add_representer(str, str_representer)
    
    with open(manifest_file, "w") as f:
        yaml.dump(manifest, f, default_flow_style=False, sort_keys=False)
    
    print(f"   Saved manifest to: {manifest_file}")
    
    return manifest_file


def _build_env_vars(indices: Set[int], tier_level: int, config: dict, is_full_range: bool = False) -> List[dict]:
    """Build environment variables.
    
    Args:
        indices: Set of indices to process
        tier_level: Current tier level
        config: Configuration dict
        is_full_range: If True and indices are 0..N-1, use simpler direct mapping
    """
    # Check if this is a simple 0..N-1 range
    sorted_indices = sorted(list(indices))
    use_direct_index = is_full_range and sorted_indices == list(range(len(sorted_indices)))
    
    env_vars = [
        {
            "name": "JOB_COMPLETION_INDEX",
            "valueFrom": {
                "fieldRef": {
                    "fieldPath": "metadata.annotations['batch.kubernetes.io/job-completion-index']"
                }
            }
        },
        {
            "name": "MEMORY_TIER",
            "value": str(tier_level)
        }
    ]
    
    # Only add INDEX_MAPPING if needed
    if not use_direct_index:
        env_vars.append({
            "name": "INDEX_MAPPING",
            "value": json.dumps(sorted_indices)
        })
    
    for env in config.get("environment", []):
        if "value_from" in env:
            env_var = {"name": env["name"], "valueFrom": {}}
            if "secret" in env["value_from"]:
                env_var["valueFrom"]["secretKeyRef"] = {
                    "name": env["value_from"]["secret"]["name"],
                    "key": env["value_from"]["secret"]["key"]
                }
            env_vars.append(env_var)
        else:
            env_vars.append({"name": env["name"], "value": env["value"]})
    
    return env_vars, use_direct_index


def main():
    # Check for --init flag to create Tier 0
    if len(sys.argv) >= 3 and sys.argv[1] == "--init":
        config_file = sys.argv[2]
        namespace = sys.argv[3] if len(sys.argv) > 3 else "biodiversity"
        
        print("=" * 60)
        print("Creating Initial Tier 0 Job")
        print("=" * 60)
        
        # Load config to get total indices
        with open(config_file) as f:
            config = yaml.safe_load(f)
        
        all_indices = set(range(config["total_indices"]))
        print(f"\n📊 Total indices: {len(all_indices)}")
        
        # Create Tier 0 job
        manifest_file = create_next_tier_job(all_indices, -1, config_file, namespace)
        
        if manifest_file:
            print(f"\n📋 To launch Tier 0, run:")
            print(f"   kubectl apply -f {manifest_file}")
        
        return 0
    
    if len(sys.argv) < 4:
        print("Usage:")
        print("  Create Tier 0:    python3 tier_escalate.py --init <config.yaml> [namespace]")
        print("  Escalate failed:  python3 tier_escalate.py <completed_job_name> <current_tier> <config.yaml>")
        print("\nExamples:")
        print("  python3 tier_escalate.py --init wetlands_config.yaml")
        print("  python3 tier_escalate.py wetlands-tier0 0 wetlands_config.yaml")
        sys.exit(1)
    
    job_name = sys.argv[1]
    current_tier = int(sys.argv[2])
    config_file = sys.argv[3]
    namespace = "biodiversity"
    
    print("=" * 60)
    print("Tier Escalation Tool - Robust & Stateless")
    print("=" * 60)
    
    # Get failed indices from completed job
    failed_indices = get_failed_indices(job_name, namespace)
    
    if not failed_indices:
        print("\n✅ All done! No more indices to retry.")
        return 0
    
    # Save failed indices for reference
    indices_file = f"failed_indices_tier{current_tier}.json"
    with open(indices_file, "w") as f:
        json.dump(sorted(list(failed_indices)), f, indent=2)
    print(f"\n💾 Saved failed indices to: {indices_file}")
    
    # Create next tier job
    manifest_file = create_next_tier_job(failed_indices, current_tier, config_file, namespace)
    
    if manifest_file:
        print(f"\n📋 To apply the job, run:")
        print(f"   kubectl apply -f {manifest_file}")
        print(f"\n📊 To check progress:")
        print(f"   kubectl get job -n {namespace} -w")
        print(f"\n🔄 After completion, run this script again with tier {current_tier + 1}")
    
    return 0


if __name__ == "__main__":
    exit(main())
