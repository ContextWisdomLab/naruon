FROM node:26-slim@sha256:c0753125a3789977aefe869cbebccf70e3cfd7ea84ca48547458f02e4f1d7146

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
ARG OCI_IMAGE_TITLE="naruon frontend"
ARG OCI_IMAGE_DESCRIPTION="Naruon Next.js frontend runtime image"
ARG OCI_IMAGE_BASE_DIGEST="sha256:4ebb5ace66f15a24c14c492e01a8beeed4fddf970a856109f5126e703e5fe503"
ARG OCI_IMAGE_BASE_NAME="docker.io/library/node:26-slim@sha256:4ebb5ace66f15a24c14c492e01a8beeed4fddf970a856109f5126e703e5fe503"

# Defaults keep local builds provenance-complete. The release workflow derives
# and overrides both values from this file's exact FROM line, while repository
# governance tests prevent the reviewed defaults from drifting.
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
# The browser client (frontend/src/lib/api-client.ts) uses an empty baseUrl
# and reaches the backend through the same-origin /api/* route handler.
# BACKEND_INTERNAL_URL is intentionally runtime-only so published images
# are not permanently wired to one deployment environment.

ENV POSTCSS_WORKERS=1
ENV DISABLE_POSTCSS_WORKERS=true

RUN pnpm run build

RUN chown -R node:node /app
USER node

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD node -e "fetch('http://127.0.0.1:' + (process.env.PORT || '3000')).then((response) => { if (!response.ok) process.exit(1); }).catch(() => process.exit(1))"

# Render injects $PORT at runtime
CMD sh -c "exec ./node_modules/.bin/next start --hostname 0.0.0.0 --port ${PORT:-3000}"
