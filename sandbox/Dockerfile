# OpenClaw sandbox image — custom runtimes for Jimbo
#
# Base: openclaw-sandbox:bookworm-slim-original (Debian 12)
# Adds: Python 3.11, Node 18, TypeScript tooling, git, common CLI tools
#
# Build on VPS:
#   scp sandbox/Dockerfile root@167.99.206.214:/tmp/Dockerfile.jimbo
#   ssh jimbo 'docker build -f /tmp/Dockerfile.jimbo -t openclaw-sandbox:bookworm-slim /tmp/'
#
# Then recreate the sandbox container:
#   ssh jimbo 'docker rm -f $(docker ps -aq --filter name=openclaw-sbx) && systemctl restart openclaw'
#
# IMPORTANT: Do NOT add "USER openclaw" — OpenClaw creates this user at container runtime.

FROM openclaw-sandbox:bookworm-slim-original

USER root

# System packages (apt)
RUN apt-get update -qq && \
    apt-get install -y -qq --no-install-recommends \
    python3 python3-pip python3-venv \
    nodejs npm \
    git ca-certificates \
    jq curl make \
    && rm -rf /var/lib/apt/lists/*

# TypeScript tooling (global — available everywhere without per-project npm install)
# Note: @types/node is NOT installed globally — it only works as a local project dependency
RUN npm install -g typescript ts-node

# --- Writable paths ---
# The root filesystem is read-only. The only writable mount is /workspace.
# We redirect HOME, XDG, npm cache, and git config there so all tools
# can write their config/cache without hitting EROFS or EPERM.
ENV HOME=/workspace
ENV XDG_CONFIG_HOME=/workspace/.config
ENV npm_config_cache=/workspace/.npm-cache
ENV GIT_CONFIG_GLOBAL=/workspace/.gitconfig

# Suppress harmless fchown warnings from npm (CHOWN capability is dropped).
# Packages still install correctly — they just keep root's ownership.
ENV npm_config_unsafe_perm=true

# Default umask so new files/dirs created by root are world-readable/writable.
# Prevents permission drift when Jimbo creates new blog posts or directories.
# The workspace is owned by openclaw (uid 1000) but the container runs as root.
# Note: bash.bashrc only applies to interactive shells. The ENV UMASK is
# documentation — the actual process umask depends on the parent process.
RUN echo 'umask 0000' >> /etc/bash.bashrc
ENV UMASK=0000
