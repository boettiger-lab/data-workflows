#!/usr/bin/env python3
"""
PreToolUse safety guard — Claude Code, boettiger-lab/data-workflows.

Blocks (exit 2) destructive Bash commands that target RECOVERY COPIES (the MinIO
backup / source.coop mirror) or are catastrophic at the cluster/bucket level.
This is the bypass-proof backstop for running Claude in
--dangerously-skip-permissions (YOLO): PreToolUse hooks still fire and can block
even when permission prompts are skipped.

SCOPE / LIMITS: this matches command-STRING patterns. It reliably stops
ACCIDENTS; it is NOT a boundary against obfuscation (base64, indirection,
wrapper scripts). The real boundary is credential + namespace isolation — see
boettiger-lab/geo-agent-ops/DATA_WORKFLOWS_HARDENING.md. Keep both layers.

Deliberately does NOT block normal workflow ops: kubectl delete job / -f,
rclone purge/delete on an nrp: SUBPATH (staging), rclone copy/ls/sync FROM a
backup, aws s3 rm of a single key, rm -rf under /tmp.
"""
import json
import re
import sys

try:
    data = json.load(sys.stdin)
except Exception:
    sys.exit(0)

if data.get("tool_name") != "Bash":
    sys.exit(0)

cmd = (data.get("tool_input") or {}).get("command") or ""
if not cmd.strip():
    sys.exit(0)


def has(pattern):
    return re.search(pattern, cmd, re.IGNORECASE)


def block(reason):
    sys.stderr.write(
        "BLOCKED by data-workflows safety hook: %s.\n"
        "Protects recovery copies / cluster from accidental destruction "
        "(geo-agent-ops/DATA_WORKFLOWS_HARDENING.md).\n"
        "If intentional, run it directly in a terminal outside Claude.\n" % reason
    )
    sys.exit(2)


# --- Backup / mirror destruction (the recovery copies) ---
if has(r"\brclone\s+(purge|delete|deletefile|rmdir|rmdirs)\b.*\b(minio:|source:|opendata\.source\.coop)"):
    block("rclone destructive op against the MinIO backup / source.coop mirror")
if has(r"\brclone\s+sync\b.*\b(minio:|source:|opendata\.source\.coop)"):
    block("rclone sync targeting the MinIO backup / source.coop mirror (mirrors deletes)")

# --- Wiping an ENTIRE canonical NRP bucket (staging subpaths are allowed) ---
if has(r"""\brclone\s+(purge|delete|rmdirs?)\s+["']?nrp:[A-Za-z0-9._-]+["']?(\s|;|&|\||$)"""):
    block("rclone purge/delete of a whole nrp: bucket root (use a subpath for staging)")

# --- S3 bucket-level destruction on ANY endpoint ---
if has(r"\baws\s+s3\s+rb\b"):
    block("aws s3 rb (remove bucket)")
if has(r"\baws\s+s3api\s+delete-bucket\b"):
    block("aws s3api delete-bucket")
if has(r"\baws\s+s3\s+rm\b.*--recursive"):
    block("aws s3 rm --recursive (mass delete)")
# MinIO/rustfs client: `mc` and `rc` (rustfs's drop-in for mc — same verbs).
if has(r"\b(mc|rc)\s+rb\b"):
    block("mc/rc rb (remove bucket)")
if has(r"\b(mc|rc)\s+rm\b.*(--recursive|--force|\s-r\b)"):
    block("mc/rc rm --recursive/--force (mass delete)")
if has(r"\b(mc|rc)\s+mirror\b.*(--remove|--overwrite)"):
    block("mc/rc mirror --remove/--overwrite (destructive mirror)")

# --- Catastrophic kubernetes ops (normal `delete job` / `delete -f` allowed) ---
if has(r"\bkubectl\b.*\bdelete\b"):
    if has(r"\bdelete\s+(ns|namespaces?)\b"):
        block("kubectl delete namespace")
    if has(r"\bdelete\s+(pvc|persistentvolumeclaims?|pv|persistentvolumes?)\b"):
        block("kubectl delete of a PVC/PV (data loss)")
    if has(r"(-n|--namespace)[=\s]+(rook|kube-system|boettiger-lab)\b"):
        block("kubectl delete in a protected namespace (rook / kube-system / boettiger-lab)")
    if has(r"\bdelete\b.*--all\b"):
        block("kubectl delete --all (mass delete)")

# --- Filesystem catastrophe (belt-and-suspenders; Claude has a built-in guard too) ---
if has(r"""\brm\s+-[A-Za-z]*(rf|fr)[A-Za-z]*\s+["']?(/|~|\$HOME)["']?(\s|;|&|\||$)"""):
    block("rm -rf of / or $HOME")

sys.exit(0)
