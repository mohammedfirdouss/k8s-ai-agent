FROM python:3.12-slim

# Install kubectl — the investigation layer shells out to it.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates \
    && curl -fsSLo /usr/local/bin/kubectl \
        "https://dl.k8s.io/release/v1.31.0/bin/linux/$(dpkg --print-architecture)/kubectl" \
    && chmod +x /usr/local/bin/kubectl \
    && apt-get purge -y curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /code

# Install dependencies first so this layer is cached between builds.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code.
COPY app ./app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
