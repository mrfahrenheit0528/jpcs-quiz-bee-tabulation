# Pin the upstream WAL-reset fix while keeping Python's standard sqlite3 driver.
FROM python:3.13-slim-bookworm AS sqlite-build
RUN apt-get update && apt-get install -y --no-install-recommends build-essential curl ca-certificates && rm -rf /var/lib/apt/lists/*
WORKDIR /build
RUN curl -fsSL https://www.sqlite.org/2026/sqlite-autoconf-3510300.tar.gz -o sqlite.tar.gz \
    && echo "81f5be397049b0cae1b167f2225af7646fc0f82e4a9b3c48c9ea3a533e21d77a  sqlite.tar.gz" | sha256sum -c - \
    && tar -xzf sqlite.tar.gz \
    && cd sqlite-autoconf-3510300 \
    && ./configure --prefix=/usr/local --disable-static \
    && make -j2 \
    && make install

FROM python:3.13-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1 QUIZ_DATA_DIR=/data
COPY --from=sqlite-build /usr/local/lib/libsqlite3.so* /usr/local/lib/
RUN ldconfig && python -c "import sqlite3; assert sqlite3.sqlite_version_info >= (3, 51, 3), sqlite3.sqlite_version"
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && groupadd -g 10001 quiz && useradd -u 10001 -g quiz -M quiz && mkdir /data && chown quiz:quiz /data
COPY website website
COPY main.py .
USER 10001:10001
EXPOSE 5000
CMD ["python", "main.py"]
