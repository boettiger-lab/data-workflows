#!/usr/bin/env bash
# Build a k8s Job that uploads locally-authored STAC files to NRP.
# Usage: mk-upload-job.sh <jobname> <srcdir>   (srcdir holds files named  bucket__path__to__file.json)
set -euo pipefail
JOB=$1; SRC=$2; OUT=$3
kubectl create configmap "${JOB}-files" -n geo-workflows --from-file="$SRC" --dry-run=client -o yaml > "$OUT"
cat >> "$OUT" <<YAML
---
apiVersion: batch/v1
kind: Job
metadata:
  name: ${JOB}
  namespace: geo-workflows
spec:
  completions: 1
  parallelism: 1
  backoffLimit: 2
  ttlSecondsAfterFinished: 86400
  template:
    spec:
      restartPolicy: Never
      containers:
      - name: upload
        image: ghcr.io/boettiger-lab/datasets:latest
        imagePullPolicy: Always
        volumeMounts:
        - name: rclone-config
          mountPath: /root/.config/rclone
          readOnly: true
        - name: files
          mountPath: /files
          readOnly: true
        command:
        - bash
        - -c
        - |
          set -euo pipefail
          for f in /files/*; do
            b="\$(basename "\$f")"
            dest="\${b//__//}"
            echo "-> nrp:\$dest"
            cp -L "\$f" /tmp/staged; rclone copyto /tmp/staged "nrp:\$dest"
          done
          echo "=== upload complete ==="
        resources:
          requests: {cpu: '1', memory: 2Gi}
          limits:   {cpu: '1', memory: 2Gi}
      volumes:
      - name: rclone-config
        secret: {secretName: rclone-config}
      - name: files
        configMap: {name: ${JOB}-files}
      priorityClassName: opportunistic
YAML
echo "wrote $OUT"
