ARG sdkVersion=3.12
FROM artifactory.ep.chehejia.com/licloud-docker/base/run/python:${sdkVersion}

RUN mkdir -p /chj/app /chj/app/backend/static/uploads && chmod 775 -R /chj

WORKDIR /chj/app

ENV SOURCE_PATH=.
ENV SERVICE_PORT=8080
ENV FEISHU_APP_ID=local_dummy_app_id
ENV FEISHU_APP_SECRET=local_dummy_app_secret
ENV FEISHU_REDIRECT_URI=http://127.0.0.1:8080/auth/feishu/callback
ENV JWT_SECRET=local_dummy_jwt_secret_replace_me
ENV USERS_DB_URL=mysql://root:root@127.0.0.1:3306/workmanship
ENV HOST=0.0.0.0
ENV PORT=8080

COPY ${SOURCE_PATH} .

RUN pip install --upgrade pip && pip install -r backend/requirements.txt

EXPOSE 8080

CMD ["sh", "-c", "python -m uvicorn backend.main:app --host 0.0.0.0 --port ${SERVICE_PORT} 2>&1"]
