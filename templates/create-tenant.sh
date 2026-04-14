#!/usr/bin/env bash
# Create a new L3 tenant fork from L2 (AutoService).
#
# Usage: ./templates/create-tenant.sh <tenant-name> [org]
# Example: ./templates/create-tenant.sh cinnox h2oslabs

set -euo pipefail

TENANT="${1:?Usage: create-tenant.sh <tenant-name> [org]}"
ORG="${2:-h2oslabs}"
UPSTREAM="h2oslabs/AutoService"

echo "==> Creating L3 fork for tenant: $TENANT (org: $ORG)"

# 1. Fork the repo
gh repo fork "$UPSTREAM" --org "$ORG" --fork-name "${TENANT}-autoservice" --clone
cd "${TENANT}-autoservice"

# 2. Configure upstream
git remote add upstream "git@github.com:${UPSTREAM}.git"

# 3. Create tenant plugin directory
mkdir -p "plugins/${TENANT}/mock_data" "plugins/${TENANT}/references"
cp -r plugins/_example/* "plugins/${TENANT}/"
sed -i "s/_example/${TENANT}/g" "plugins/${TENANT}/plugin.yaml"

# 4. Create tenant skill directory (optional)
mkdir -p "skills/${TENANT}-demo"

# 5. Update .autoservice-info.yaml
cat > .autoservice-info.yaml << EOF
app_name: "${TENANT}-autoservice"
version: "0.1.0"
layer: L3
upstream: "${UPSTREAM}"
customer: "${TENANT}"
description: "${TENANT} customer service bot"
EOF

# 6. Initial commit
git add "plugins/${TENANT}/" "skills/${TENANT}-demo/" .autoservice-info.yaml
git commit -m "feat: initialize ${TENANT} tenant"

echo ""
echo "==> Done! Tenant '${TENANT}' created at: $(pwd)"
echo "    Next steps:"
echo "    1. Edit plugins/${TENANT}/plugin.yaml"
echo "    2. Add mock data to plugins/${TENANT}/mock_data/"
echo "    3. git push origin main"
