# Obraz Lambdy inference — wersja próbna (tracer): spaCy pl_core_news_lg + minimalny handler.
# Cel: zmierzyć rozmiar obrazu, zużycie pamięci i cold start (ADR-0004). XGBoost i packages/features — później.
FROM public.ecr.aws/lambda/python:3.12

COPY requirements.txt ${LAMBDA_TASK_ROOT}/
RUN pip install --no-cache-dir -r ${LAMBDA_TASK_ROOT}/requirements.txt

COPY app/ ${LAMBDA_TASK_ROOT}/app/

CMD ["app.handler.handler"]
