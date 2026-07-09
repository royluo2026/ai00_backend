ARG sdkVersion=3.12
FROM artifactory.ep.chehejia.com/licloud-docker/base/run/python:${sdkVersion}

RUN mkdir -p /chj/app /chj/app/backend/static/uploads && chmod 775 -R /chj

WORKDIR /chj/app

# 默认复制仓库根目录，保证 backend 包结构可用
ENV SOURCE_PATH=.
ENV SERVICE_PORT=8080

COPY ${SOURCE_PATH} .

RUN pip install --upgrade pip && pip install -r backend/requirements.txt

EXPOSE 8080

CMD sh -c "python -m uvicorn backend.main:app --host 0.0.0.0 --port ${SERVICE_PORT} 2>&1"
