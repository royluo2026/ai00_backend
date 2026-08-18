FROM artifactory.ep.chehejia.com/licloud-docker/base/run/python:3.12

RUN mkdir -p /chj/app /chj/app/backend/static/uploads && chmod 775 -R /chj

WORKDIR /chj/app

ENV SOURCE_PATH=.
ENV HOST=0.0.0.0
ENV PORT=8080

COPY ${SOURCE_PATH} .

RUN pip install --upgrade pip && pip install -r backend/requirements.txt

EXPOSE 8080

CMD ["sh", "-c", "test -n \"$ENV_FILE\" || { echo 'ENV_FILE is required for container runtime' >&2; exit 2; }; exec gunicorn backend.main:app -c backend/gunicorn.conf.py"]
