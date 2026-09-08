# Stage 1: Backend runtime for local Compose and backend-only deployments
FROM python:3.14-slim@sha256:a7fb1e634c4a578f9e0bd6327f11a3cde11b7a9395f48e24360c0988bcc5c2bc AS backend-runtime
WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# Install Backend dependencies
COPY backend/requirements-hashes.txt /app/requirements-hashes.txt
RUN PIP_ROOT_USER_ACTION=ignore PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_ONLY_BINARY=:all: \
    pip install --no-cache-dir --require-hashes -r requirements-hashes.txt

# Copy Backend
COPY VERSION /app/VERSION
COPY backend /app/

RUN groupadd --system --gid 10001 appuser \
    && useradd --system --create-home --home-dir /home/appuser --uid 10001 --gid appuser --shell /usr/sbin/nologin appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

CMD ["python", "scripts/start_backend.py", "--host", "0.0.0.0", "--port", "8000"]

# Stage 2: Build Frontend
FROM node:26-slim@sha256:4ebb5ace66f15a24c14c492e01a8beeed4fddf970a856109f5126e703e5fe503 AS frontend-builder
WORKDIR /app
ENV NPM_CONFIG_UPDATE_NOTIFIER=false
ENV PNPM_VERSION=11.5.3
ENV PNPM_INTEGRITY=sha512-esHJGTQcITo03A0Cr7cUPFwmrCbujEeC3uqCG4rGTSE0oIH9iUHa5uKbu0j1jfwrf7zuzMB8svCdIZ00Kklp7Q==
RUN node -e "const crypto=require('node:crypto');const fs=require('node:fs');const https=require('node:https');const url='https://registry.npmjs.org/pnpm/-/pnpm-'+process.env.PNPM_VERSION+'.tgz';https.get(url,(res)=>{if(res.statusCode!==200){throw new Error('pnpm download failed: '+res.statusCode)}const chunks=[];res.on('data',(chunk)=>chunks.push(chunk));res.on('end',()=>{const data=Buffer.concat(chunks);const digest='sha512-'+crypto.createHash('sha512').update(data).digest('base64');if(digest!==process.env.PNPM_INTEGRITY){throw new Error('pnpm integrity mismatch')}fs.writeFileSync('/tmp/pnpm.tgz',data);});}).on('error',(error)=>{throw error;});"
RUN mkdir -p /opt/pnpm \
    && tar -xzf /tmp/pnpm.tgz -C /opt/pnpm --strip-components=1 \
    && chmod +x /opt/pnpm/bin/pnpm.cjs /opt/pnpm/bin/pnpx.cjs \
    && ln -sf /opt/pnpm/bin/pnpm.cjs /usr/local/bin/pnpm \
    && ln -sf /opt/pnpm/bin/pnpx.cjs /usr/local/bin/pnpx \
    && rm /tmp/pnpm.tgz
COPY frontend/package.json frontend/pnpm-lock.yaml frontend/pnpm-workspace.yaml frontend/.pnpmfile.cjs ./
COPY frontend/patches ./patches
RUN pnpm install --frozen-lockfile
COPY frontend ./
ENV NEXT_TELEMETRY_DISABLED=1
ENV POSTCSS_WORKERS=1
ENV DISABLE_POSTCSS_WORKERS=true
RUN pnpm run build

# Stage 3: Combined image (Python + Node.js)
# backend-runtime ends with USER appuser (non-root). Stage 3 inherits that
# non-root context, so no root elevation is needed here.
FROM backend-runtime

ARG OCI_IMAGE_CREATED=""
ARG OCI_IMAGE_AUTHORS="Seongho Bae"
ARG OCI_IMAGE_URL="https://github.com/Seongho-Bae/naruon"
ARG OCI_IMAGE_DOCUMENTATION="https://github.com/Seongho-Bae/naruon#readme"
ARG OCI_IMAGE_SOURCE="https://github.com/Seongho-Bae/naruon"
ARG OCI_IMAGE_VERSION="0.14.4"
ARG OCI_IMAGE_REVISION=""
ARG OCI_IMAGE_VENDOR="Seongho-Bae"
ARG OCI_IMAGE_LICENSES="LicenseRef-Naruon-Proprietary"
ARG OCI_IMAGE_REF_NAME=""
ARG OCI_IMAGE_TITLE="naruon"
ARG OCI_IMAGE_DESCRIPTION="Naruon combined FastAPI and Next.js runtime image"
ARG OCI_IMAGE_BASE_DIGEST="sha256:a7fb1e634c4a578f9e0bd6327f11a3cde11b7a9395f48e24360c0988bcc5c2bc"
ARG OCI_IMAGE_BASE_NAME="docker.io/library/python:3.14-slim@sha256:a7fb1e634c4a578f9e0bd6327f11a3cde11b7a9395f48e24360c0988bcc5c2bc"

# Defaults keep local builds provenance-complete. The publishing workflow derives
# and overrides both values from the exact first FROM instruction, while
# repository governance tests prevent the reviewed defaults from drifting.
RUN test -n "$OCI_IMAGE_BASE_DIGEST" && test -n "$OCI_IMAGE_BASE_NAME"

LABEL org.opencontainers.image.created="${OCI_IMAGE_CREATED}" \
      org.opencontainers.image.authors="${OCI_IMAGE_AUTHORS}" \
      org.opencontainers.image.url="${OCI_IMAGE_URL}" \
      org.opencontainers.image.documentation="${OCI_IMAGE_DOCUMENTATION}" \
      org.opencontainers.image.source="${OCI_IMAGE_SOURCE}" \
      org.opencontainers.image.version="${OCI_IMAGE_VERSION}" \
      org.opencontainers.image.revision="${OCI_IMAGE_REVISION}" \
      org.opencontainers.image.vendor="${OCI_IMAGE_VENDOR}" \
      org.opencontainers.image.licenses="${OCI_IMAGE_LICENSES}" \
      org.opencontainers.image.ref.name="${OCI_IMAGE_REF_NAME}" \
      org.opencontainers.image.title="${OCI_IMAGE_TITLE}" \
      org.opencontainers.image.description="${OCI_IMAGE_DESCRIPTION}" \
      org.opencontainers.image.base.digest="${OCI_IMAGE_BASE_DIGEST}" \
      org.opencontainers.image.base.name="${OCI_IMAGE_BASE_NAME}"

# Runtime Node is copied into an app-owned directory so that no root elevation
# is required. /app is owned by appuser (set in stage 1) so appuser can write
# here directly.
RUN mkdir -p /app/bin
COPY --from=frontend-builder --chown=appuser:appuser /usr/local/bin/node /app/bin/node
ENV PATH=/app/bin:$PATH

# Copy Frontend runtime artifacts as appuser to avoid privilege escalation.
COPY --from=frontend-builder --chown=appuser:appuser /app/.next /app/frontend/.next
COPY --from=frontend-builder --chown=appuser:appuser /app/public /app/frontend/public
COPY --from=frontend-builder --chown=appuser:appuser /app/node_modules /app/frontend/node_modules
COPY --from=frontend-builder --chown=appuser:appuser /app/package.json /app/frontend/package.json
COPY --from=frontend-builder --chown=appuser:appuser /app/next.config.ts /app/frontend/next.config.ts

# Startup is handled by scripts/docker_entrypoint.sh (copied with the backend in
# stage 1). It validates required configuration (DATABASE_URL,
# AUTH_SESSION_HMAC_SECRET, and a valid Fernet ENCRYPTION_KEY — never generated
# at runtime), then starts backend and frontend together and reports which
# service exits. Secrets must be supplied by the operator or orchestrator.
RUN chmod +x /app/scripts/docker_entrypoint.sh

# Environment variables for Frontend proxying inside the combined image.
# Browser code uses same-origin /api/*; only the server-side route handler needs
# the internal backend URL at runtime.
ENV BACKEND_INTERNAL_URL=http://127.0.0.1:8000
ENV ALLOW_DOCKER_BACKEND_INTERNAL_URL=1

EXPOSE 3000 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=45s --retries=3 \
    CMD python -c "import urllib.request; [urllib.request.urlopen(url, timeout=3).close() for url in ('http://127.0.0.1:8000/', 'http://127.0.0.1:3000/')]"

CMD ["/app/scripts/docker_entrypoint.sh"]
