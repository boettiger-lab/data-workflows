# Data Requests

A lightweight feedback and data request form deployed at
**https://data-requests.nrp-nautilus.io/**.

Each app gets its own route (e.g. `/tpl` for the TPL California Explorer).
The root `/` serves a generic data request form. All submissions are stored
as JSON in the `public-requests` S3 bucket under `dataset-requests/`.

## Structure

```
dataset-requests/
├── app/
│   ├── app.py        # FastAPI backend (routes, S3 storage, app configs)
│   └── index.html    # HTML template (Python .format() placeholders)
└── k8s/
    ├── deployment.yaml   # Deployment with git-sync init container
    ├── service.yaml
    ├── ingress.yaml      # Host: data-requests.nrp-nautilus.io
    └── setup-bucket.yaml # One-time bucket creation
```

## Adding a new app

Add an entry to the `APPS` dict in `app/app.py`:

```python
APPS = {
    "tpl": {
        "title": "TPL California Explorer",
        "subtitle": "Help us improve the <a href=\"https://tpl-ca.nrp-nautilus.io/\">TPL California Explorer</a>. ...",
    },
    "new-app": {
        "title": "My New App",
        "subtitle": "Help us improve <a href=\"https://...\">My New App</a>. ...",
    },
}
```

The new form is then served at `https://data-requests.nrp-nautilus.io/new-app`.
Submissions include an `"app": "new-app"` field in the JSON record.

## Updating and deploying

The deployment uses a git-sync init container that clones this repo on pod
startup. To deploy changes:

1. Commit and push to `main` (via PR — branch protection is on).
2. Restart the deployment so pods pick up the new code:

```bash
kubectl rollout restart deployment/dataset-requests
kubectl rollout status deployment/dataset-requests
```

## Kubernetes resources

All resources live in the `biodiversity` namespace.

| Resource | Name |
|----------|------|
| Deployment | `dataset-requests` |
| Service | `dataset-requests` |
| Ingress | `data-requests-ingress` |

The app reads S3 credentials from the `aws` secret in the namespace.

## Viewing submissions

```bash
# Via the API
curl -s https://data-requests.nrp-nautilus.io/api/requests | jq .

# Or directly from S3
rclone ls nrp:public-requests/dataset-requests/
```
