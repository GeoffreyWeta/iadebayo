#!/usr/bin/env bash
#
# Deploys the current origin/master onto the droplet.
#
# Normally run by .github/workflows/deploy.yml, which pipes this file over SSH
# rather than executing the server's copy — the reset below rewrites the working
# tree, and a script being edited while bash is still reading it misbehaves in
# ways that are miserable to debug.
#
# To deploy by hand from your machine:
#     ssh deploy@YOUR_IP 'bash -s' < deploy/deploy.sh
#
set -euo pipefail

APP_DIR=/srv/iadebayo
BRANCH=master
SERVICE=iadebayo
PY="$APP_DIR/.venv/bin/python"
PIP="$APP_DIR/.venv/bin/pip"

cd "$APP_DIR"

PREVIOUS=$(git rev-parse HEAD)
echo "==> currently deployed: $(git rev-parse --short HEAD) $(git log -1 --format=%s)"

# --- code ------------------------------------------------------------------
# reset --hard, not pull: the server's tree must match origin exactly. A pull
# can stop on a conflict from someone's quick edit on the box and leave the
# deploy half-applied.
git fetch --prune origin
git reset --hard "origin/$BRANCH"
echo "==> deploying:         $(git rev-parse --short HEAD) $(git log -1 --format=%s)"

if [ "$PREVIOUS" = "$(git rev-parse HEAD)" ]; then
  echo "==> already at this commit; continuing anyway (dependencies or .env may have changed)"
fi

# --- dependencies ----------------------------------------------------------
"$PIP" install --quiet --upgrade pip
"$PIP" install --quiet -r requirements.txt

# --- database and static ---------------------------------------------------
"$PY" manage.py migrate --noinput
"$PY" manage.py collectstatic --noinput

# Config sanity *before* the restart, so a broken .env leaves the currently
# running workers untouched and the site up on the old code.
"$PY" manage.py check --deploy

# --- swap in the new code --------------------------------------------------
sudo systemctl restart "$SERVICE"

# --- prove it actually came back -------------------------------------------
# Gunicorn binds 127.0.0.1:8000 and Django rejects hosts outside ALLOWED_HOSTS,
# so borrow the first allowed host from .env for the Host header.
HEALTH_HOST=$(grep -E '^DJANGO_ALLOWED_HOSTS=' .env 2>/dev/null \
              | cut -d= -f2- | tr -d '"'"'" | tr ',' '\n' | head -1 | xargs || true)
HEALTH_HOST=${HEALTH_HOST:-localhost}

for attempt in 1 2 3 4 5 6 7 8 9 10; do
  code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 \
              -H "Host: $HEALTH_HOST" http://127.0.0.1:8000/ || true)
  if [ "$code" = "200" ]; then
    echo "==> healthy: gunicorn answered 200 for Host: $HEALTH_HOST"
    echo "==> deployed $(git rev-parse --short HEAD)"
    exit 0
  fi
  echo "    attempt $attempt/10: got ${code:-no response}, retrying..."
  sleep 3
done

# --- failed ----------------------------------------------------------------
# Deliberately no automatic rollback. The migrations above have already been
# applied, and checking out older code against a newer schema is how a bad
# deploy becomes a bad database. Roll back knowingly, after reading the log.
echo
echo "!!! gunicorn did not return 200 after the restart."
echo "!!! Last 40 log lines:"
sudo journalctl -u "$SERVICE" -n 40 --no-pager || true
echo
echo "!!! Still on the new code. To go back to the previous commit:"
echo "!!!   ssh $(whoami)@\$HOST"
echo "!!!   cd $APP_DIR && git reset --hard $PREVIOUS && sudo systemctl restart $SERVICE"
echo "!!! Check first whether the migrations that just ran need reversing."
exit 1
