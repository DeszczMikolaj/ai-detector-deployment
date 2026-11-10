# Obraz Lambdy inference (ADR-0004, ADR-0012, ADR-0015).
#
# Budowany z KATALOGU GŁÓWNEGO repo — kontekst musi zawierać packages/features:
#   docker build --platform linux/amd64 --provenance=false -f services/inference/Dockerfile -t <repo>:<tag> .
# Co trafia do kontekstu: services/inference/Dockerfile.dockerignore.
#
# Obraz zawiera kod, zależności i model spaCy. Model XGBoost NIE jest w obrazie —
# handler pobiera go z S3 przy starcie (zmienna MODEL_URI, ADR-0012).
# Model spaCy musi być tym, na którym trenowano klasyfikator — handler to sprawdza (metadata.json).
FROM public.ecr.aws/lambda/python:3.12

ARG SPACY_MODEL=pl_core_news_md
ARG SPACY_MODEL_VERSION=3.8.0

COPY services/inference/requirements.txt ${LAMBDA_TASK_ROOT}/
COPY packages/features /tmp/build/features
RUN pip install --no-cache-dir \
      -r ${LAMBDA_TASK_ROOT}/requirements.txt \
      /tmp/build/features \
      "https://github.com/explosion/spacy-models/releases/download/${SPACY_MODEL}-${SPACY_MODEL_VERSION}/${SPACY_MODEL}-${SPACY_MODEL_VERSION}-py3-none-any.whl" \
 && rm -rf /tmp/build

ENV SPACY_MODEL=${SPACY_MODEL}

COPY services/inference/app/ ${LAMBDA_TASK_ROOT}/app/

CMD ["app.handler.handler"]
