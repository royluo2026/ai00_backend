FROM artifactory.ep.chehejia.com/licloud-docker/base/run/python:3.12

RUN mkdir -p /chj/app /chj/app/backend/static/uploads && chmod 775 -R /chj

WORKDIR /chj/app

ENV SOURCE_PATH=.
ENV HOST=0.0.0.0
ENV PORT=80
ENV ENV_FILE=/chj/app/backend/.env

COPY ${SOURCE_PATH} .

RUN pip install --upgrade pip && pip install -r backend/requirements.txt

# Fail the image build when code and the frozen Provider manifest differ.
RUN python -m backend.scripts.audit_official_domain_artifacts
RUN ENV_FILE= AI00_DEPLOY_PROFILE=production python -c "from backend.capability_v2.bootstrap import build_capability_registry; from backend.capability_v2.gateway import configure_default_gateway; configure_default_gateway(build_capability_registry())"

EXPOSE 80

CMD ["sh", "-c", "test -n \"$ENV_FILE\" || { echo 'ENV_FILE is required for container runtime' >&2; exit 2; }; exec python -m backend.scripts.supervise_environment"]
