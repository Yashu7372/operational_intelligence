FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /workspace
COPY . .
RUN python -m pip install --upgrade pip \
    && python -m pip install -e .

CMD ["operational-intelligence-lab"]
