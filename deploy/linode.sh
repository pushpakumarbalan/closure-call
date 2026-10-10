#!/usr/bin/env bash
# Deploy Closure Call to an Akamai Cloud (Linode) instance.
#
# Two modes:
#   ./deploy/linode.sh create        -> provision a Linode with linode-cli (Docker via StackScript-free cloud-init), then deploy
#   ./deploy/linode.sh deploy <ip>   -> rsync + docker compose up on an existing instance (root ssh)
#
# Prereqs: linode-cli (`pip install linode-cli && linode-cli configure`) for `create`; ssh key in ~/.ssh/id_ed25519.pub; backend/.env filled in.
set -euo pipefail
cd "$(dirname "$0")/.."

REGION="${LINODE_REGION:-us-ord}"          # Chicago: closest Akamai region to Kansas City
TYPE="${LINODE_TYPE:-g6-standard-2}"       # 4 GB; plenty for FastAPI + SQLite
IMAGE="${LINODE_IMAGE:-linode/ubuntu24.04}"
LABEL="${LINODE_LABEL:-closurecall}"
SSH_KEY="${SSH_KEY:-$HOME/.ssh/id_ed25519.pub}"

cloud_init() {
cat <<'EOF'
#cloud-config
package_update: true
packages: [ca-certificates, curl, rsync]
runcmd:
  - curl -fsSL https://get.docker.com | sh
  - systemctl enable --now docker
EOF
}

create() {
  command -v linode-cli >/dev/null || { echo "install linode-cli: pip install linode-cli && linode-cli configure"; exit 1; }
  [ -f "$SSH_KEY" ] || { echo "ssh public key not found at $SSH_KEY"; exit 1; }
  ROOT_PASS="$(openssl rand -base64 24)"
  echo "Creating Linode $LABEL in $REGION ($TYPE)..."
  linode-cli linodes create --region "$REGION" --type "$TYPE" --image "$IMAGE" --label "$LABEL" \
    --root_pass "$ROOT_PASS" --authorized_keys "$(cat "$SSH_KEY")" \
    --metadata.user_data "$(cloud_init | base64)" --json > /tmp/linode-create.json
  IP=$(python3 -c "import json;print(json.load(open('/tmp/linode-create.json'))[0]['ipv4'][0])")
  echo "Linode created: $IP (root password saved to /tmp/linode-root-pass)"
  echo "$ROOT_PASS" > /tmp/linode-root-pass
  echo "Waiting for SSH + Docker..."
  for i in $(seq 1 60); do
    if ssh -o StrictHostKeyChecking=no -o ConnectTimeout=5 root@"$IP" 'command -v docker' >/dev/null 2>&1; then break; fi
    sleep 10
  done
  deploy "$IP"
}

deploy() {
  IP="$1"
  [ -f backend/.env ] || { echo "backend/.env missing (copy backend/.env.example and fill in Akamai inference creds)"; exit 1; }
  echo "Syncing source to root@$IP:/opt/closurecall ..."
  rsync -az --delete --exclude .git --exclude node_modules --exclude .venv --exclude frontend/dist --exclude backend/data \
    ./ root@"$IP":/opt/closurecall/
  ssh -o StrictHostKeyChecking=no root@"$IP" 'cd /opt/closurecall && docker compose up -d --build && docker compose ps'
  echo
  echo "Closure Call is live at http://$IP/"
  echo "Health: curl http://$IP/api/health"
}

case "${1:-}" in
  create) create ;;
  deploy) [ -n "${2:-}" ] || { echo "usage: $0 deploy <ip>"; exit 1; }; deploy "$2" ;;
  *) echo "usage: $0 create | deploy <ip>"; exit 1 ;;
esac
