FROM artifactory.ep.chehejia.com/licloud-docker/base/run/python:3.12

RUN mkdir -p /chj/app /chj/app/backend/static/uploads && chmod 775 -R /chj

WORKDIR /chj/app

ENV SOURCE_PATH=.
ENV HOST=0.0.0.0
ENV PORT=8080

COPY ${SOURCE_PATH} .

RUN pip install --upgrade pip && pip install -r backend/requirements.txt

EXPOSE 8080

CMD ["python", "-c", "import os; env_file = os.getenv('ENV_FILE', '').strip(); assert env_file, 'ENV_FILE is required for container runtime'; from dotenv import load_dotenv; load_dotenv(env_file, override=True); import uvicorn; uvicorn.run('backend.main:app', host=os.getenv('HOST', '0.0.0.0'), port=int(os.getenv('PORT', '8080') or '8080'))"]
