#!/usr/bin/env bash
# Installs HexTime on a Linux server, or updates an installation.
#
#   bash hextime-install.sh                 # the published image (ghcr.io)
#   bash hextime-install.sh --build         # build the image here from source
#   bash hextime-install.sh --help
#
# Run it as the ordinary user who will own HexTime, from a terminal: it asks
# questions. It needs Podman 4.6 or newer and systemd. sudo is asked for only
# where nothing else will do: letting rootless Podman use ports 80 and 443,
# and keeping this user's services running after logout.
#
# What it does:
#   1. gets the HexTime image (pulls it, or builds it from the source)
#   2. asks the installation questions inside the image (`hextime setup`),
#      which writes the settings into ~/.config/hextime/ (mode 600)
#   3. installs the services: HexTime, PostgreSQL and Caddy as Podman Quadlet
#      units, and a nightly database backup
#   4. starts them, waits for HexTime to answer, and invites the first
#      administrator by email
#
# Running it again is how HexTime is updated, and how a setting is changed:
# the current answers are the defaults, and the secrets are kept.
set -euo pipefail

DEFAULT_IMAGE="ghcr.io/carmantis/hextime:latest"
DEFAULT_REPO="https://github.com/Carmantis/HexTime.git"
LOCAL_IMAGE="localhost/hextime:latest"
MIN_PODMAN="4.6"
# The user the HexTime image runs as (deploy/Containerfile).
IMAGE_UID=10001
# Not $USER: it is unset in some sessions (cron, `podman exec`, containers).
me="$(id -un)"

CONFIG_DIR="$HOME/.config/hextime"
QUADLET_DIR="$HOME/.config/containers/systemd"
USER_UNIT_DIR="$HOME/.config/systemd/user"
DATA_DIR="$HOME/.local/share/hextime"

image=""
build=0
source_dir=""
repo="$DEFAULT_REPO"
ref="main"

say() { printf '\n\033[1m==> %s\033[0m\n' "$*"; }
note() { printf '    %s\n' "$*"; }
die() {
  printf '\nhextime-install: %s\n' "$*" >&2
  exit 1
}

usage() {
  cat <<EOF
Usage: bash hextime-install.sh [options]

  --image IMAGE   use this image (default: $DEFAULT_IMAGE)
  --build         build the image on this server instead of pulling it
  --source DIR    with --build: build from this checkout instead of cloning
  --repo URL      with --build: the repository to clone ($DEFAULT_REPO)
  --ref REF       with --build: the branch or tag to build (default: main)
  -h, --help      show this help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --image) image="${2:?--image needs a value}"; shift ;;
    --build) build=1 ;;
    --source) source_dir="${2:?--source needs a directory}"; build=1; shift ;;
    --repo) repo="${2:?--repo needs a URL}"; shift ;;
    --ref) ref="${2:?--ref needs a branch or tag}"; shift ;;
    -h | --help) usage; exit 0 ;;
    *) usage >&2; die "unknown option: $1" ;;
  esac
  shift
done

# ---------------------------------------------------------------------------
# 1. What the server needs
# ---------------------------------------------------------------------------

say "Checking this server"

[[ $EUID -ne 0 ]] ||
  die "run this as the user who will own HexTime, not as root. It asks for sudo where needed."
[[ -t 0 && -t 1 ]] ||
  die "run this from a terminal: it asks questions. (Download it first, then: bash hextime-install.sh)"
command -v podman >/dev/null ||
  die "Podman is needed. Install it first, e.g.: sudo apt install podman  (or: sudo dnf install podman)"

podman_version="$(podman version --format '{{.Client.Version}}')"
if [[ "$(printf '%s\n%s\n' "$MIN_PODMAN" "$podman_version" | sort -V | head -n1)" != "$MIN_PODMAN" ]]; then
  die "Podman $podman_version is too old; HexTime needs $MIN_PODMAN or newer (Ubuntu 24.04, Debian 13, Fedora, RHEL 9 have it)."
fi
note "Podman $podman_version"

systemctl --user show-environment >/dev/null 2>&1 ||
  die "no systemd user session. Log in as $me directly (ssh $me@server), not with su or sudo -u."

# ---------------------------------------------------------------------------
# 2. The image
# ---------------------------------------------------------------------------

if [[ $build -eq 1 ]]; then
  say "Building the HexTime image on this server"
  if [[ -z "$source_dir" ]]; then
    command -v git >/dev/null || die "git is needed for --build: sudo apt install git"
    source_dir="$DATA_DIR/source"
    if [[ -d "$source_dir/.git" ]]; then
      git -C "$source_dir" fetch --depth 1 origin "$ref"
      git -C "$source_dir" checkout --force FETCH_HEAD
    else
      mkdir -p "$DATA_DIR"
      git clone --depth 1 --branch "$ref" "$repo" "$source_dir"
    fi
  fi
  [[ -f "$source_dir/deploy/Containerfile" ]] || die "$source_dir is not a HexTime checkout"
  note "from $source_dir (this takes a few minutes)"
  podman build -f "$source_dir/deploy/Containerfile" -t "$LOCAL_IMAGE" "$source_dir"
  image="$LOCAL_IMAGE"
else
  image="${image:-$DEFAULT_IMAGE}"
  if [[ "$image" == localhost/* ]]; then
    podman image exists "$image" || die "there is no image $image on this server"
    note "using $image"
  else
    say "Getting the HexTime image"
    podman pull "$image" || die "could not pull $image.
    While the repository is private, sign in first:
      podman login --authfile ~/.config/containers/auth.json ghcr.io
    Or build the image here instead: bash hextime-install.sh --build"
  fi
fi

# ---------------------------------------------------------------------------
# 3. The questions
# ---------------------------------------------------------------------------

say "Setting up"
mkdir -p "$CONFIG_DIR"
chmod 700 "$CONFIG_DIR"

setup_args=()
for address in $(hostname -I 2>/dev/null || true); do
  setup_args+=(--host-address "$address")
done

# The server's own zone is the default answer to the time zone question.
host_zone="$(timedatectl show --property=Timezone --value 2>/dev/null || true)"
if [[ -z "$host_zone" && -L /etc/localtime ]]; then
  host_zone="$(readlink /etc/localtime | sed 's|.*/zoneinfo/||')"
fi
if [[ -n "$host_zone" ]]; then
  setup_args+=(--host-time-zone "$host_zone")
fi

# keep-id maps this user to the image's user, so the files it writes into
# the mounted directory belong to this user on the server.
podman run --rm -it \
  --userns="keep-id:uid=$IMAGE_UID,gid=$IMAGE_UID" \
  -v "$CONFIG_DIR:/config:Z" \
  "$image" python -m app.cli setup --config-dir /config "${setup_args[@]}"

# shellcheck source=/dev/null
source "$CONFIG_DIR/install.vars"

# ---------------------------------------------------------------------------
# 4. What only root can allow
# ---------------------------------------------------------------------------

low_port="$(sysctl -n net.ipv4.ip_unprivileged_port_start)"
if [[ "$low_port" -gt 80 ]]; then
  say "Allowing rootless Podman to use ports 80 and 443 (sudo)"
  note "Caddy needs them for HTTPS. This writes /etc/sysctl.d/90-hextime.conf."
  sudo install -d /etc/sysctl.d
  echo "net.ipv4.ip_unprivileged_port_start=80" |
    sudo tee /etc/sysctl.d/90-hextime.conf >/dev/null
  sudo sysctl -q -p /etc/sysctl.d/90-hextime.conf
fi

if [[ "$(loginctl show-user "$me" --property=Linger --value 2>/dev/null)" != "yes" ]]; then
  say "Keeping $me's services running after logout (sudo)"
  sudo loginctl enable-linger "$me"
fi

# ---------------------------------------------------------------------------
# 5. The services
# ---------------------------------------------------------------------------

say "Installing the services"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
# The unit files travel inside the image, matching the version installed.
podman run --rm --entrypoint tar "$image" -C /app/deploy -cf - Caddyfile quadlet systemd |
  tar -xf - -C "$work"

mkdir -p "$QUADLET_DIR" "$USER_UNIT_DIR"
for unit in "$work"/quadlet/*; do
  name="$(basename "$unit")"
  sed "s|@IMAGE@|$image|" "$unit" >"$QUADLET_DIR/$name"
  if [[ "$image" == localhost/* ]]; then
    # A locally built image has no registry for `podman auto-update`.
    sed -i '/^AutoUpdate=/d' "$QUADLET_DIR/$name"
  fi
done
install -m 644 "$work"/systemd/* "$USER_UNIT_DIR/"
install -m 644 "$work/Caddyfile" "$CONFIG_DIR/Caddyfile"

systemctl --user daemon-reload
# Restart rather than start: after an update the containers must be
# recreated from the new image.
systemctl --user restart hextime-postgres.service
systemctl --user restart hextime.service
systemctl --user restart hextime-caddy.service
systemctl --user enable --now hextime-backup.timer >/dev/null

say "Waiting for HexTime to answer"
ready=0
for _ in $(seq 1 60); do
  if podman exec hextime python -c \
    "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/config', timeout=4)" \
    >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 5
done
if [[ $ready -ne 1 ]]; then
  journalctl --user -u hextime.service -n 40 --no-pager >&2 || true
  die "HexTime did not start in five minutes; its log is above."
fi
note "it does"

# ---------------------------------------------------------------------------
# 6. The first administrator, once
# ---------------------------------------------------------------------------

marker="$CONFIG_DIR/.admin-invited"
if [[ ! -e "$marker" ]]; then
  say "Inviting the first administrator"
  if podman exec hextime python -m app.cli create-admin \
    --email "$ADMIN_EMAIL" --name "$ADMIN_NAME" --send-link; then
    touch "$marker"
  else
    note "Not invited (see above). Try again later with:"
    note "  podman exec -it hextime python -m app.cli create-admin --email $ADMIN_EMAIL --send-link"
  fi
fi

say "HexTime is running: https://$HEXTIME_DOMAIN"
cat <<EOF
    The administrator ($ADMIN_EMAIL) has an email with a link to set a password.

    Update, or change a setting:  bash hextime-install.sh
    Log:                          journalctl --user -u hextime -f
    Settings:                     $CONFIG_DIR/
    Database backups (nightly):   $DATA_DIR/backups/
EOF
