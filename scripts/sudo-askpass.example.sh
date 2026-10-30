#!/usr/bin/env bash
# Template for scripts/sudo-askpass.sh (gitignored). The installer copies it there (mode 700) once the
# machine's owner puts LOCAL_SUDO_PASS in ~/.claude/.env (mode 600): installer/settings_install.seed_askpass.
# The password comes from that file only (a LOCAL_SUDO_PASS in the caller's environment is ignored).
# Without it: a clear refusal, exit 2.
set -u
unset LOCAL_SUDO_PASS
envf="${CLAUDE_CONFIG_DIR:-$HOME/.claude}/.env"
# shellcheck source=/dev/null  # the machine's own .env, not part of the repo
if [ -r "$envf" ]; then set -a; . "$envf"; set +a; fi
if [ -z "${LOCAL_SUDO_PASS:-}" ]; then
  echo "sudo-askpass: LOCAL_SUDO_PASS not set in $envf; ask the machine owner to run the sudo step" >&2
  exit 2
fi
printf '%s\n' "$LOCAL_SUDO_PASS"
