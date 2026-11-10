# Obraz Lambdy inference — wersja próbna (tracer): spaCy + minimalny handler.
# Cel: zmierzyć rozmiar obrazu, zużycie pamięci i cold start (ADR-0004). XGBoost i packages/features — później.
#
# Model spaCy wybierany przy budowaniu, np.:
#   docker build --build-arg SPACY_MODEL=pl_core_news_sm ...
# Domyślnie pl_core_news_md (ADR-0015).
# Uwaga: model w inference musi być tym samym modelem, na którym trenowano klasyfikator (ADR-0002).
FROM public.ecr.aws/lambda/python:3.12

ARG SPACY_MODEL=pl_core_news_md
ARG SPACY_MODEL_VERSION=3.8.0

COPY requirements.txt ${LAMBDA_TASK_ROOT}/
RUN pip install --no-cache-dir -r ${LAMBDA_TASK_ROOT}/requirements.txt \
 && pip install --no-cache-dir \
    "https://github.com/explosion/spacy-models/releases/download/${SPACY_MODEL}-${SPACY_MODEL_VERSION}/${SPACY_MODEL}-${SPACY_MODEL_VERSION}-py3-none-any.whl"

ENV SPACY_MODEL=${SPACY_MODEL}

COPY app/ ${LAMBDA_TASK_ROOT}/app/

CMD ["app.handler.handler"]
