FROM python:3.12-slim

# Install chrome-headless-shell and its dependencies
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        wget \
        unzip \
        ca-certificates \
        fonts-liberation \
        libasound2 \
        libatk-bridge2.0-0 \
        libatk1.0-0 \
        libcups2 \
        libdbus-1-3 \
        libdrm2 \
        libgbm1 \
        libgtk-3-0 \
        libnspr4 \
        libnss3 \
        libxcomposite1 \
        libxdamage1 \
        libxfixes3 \
        libxkbcommon0 \
        libxrandr2 \
    && CHROME_VERSION=$(wget -qO- https://googlechromelabs.github.io/chrome-for-testing/LATEST_RELEASE_STABLE) \
    && wget -q "https://storage.googleapis.com/chrome-for-testing-public/${CHROME_VERSION}/linux64/chrome-headless-shell-linux64.zip" \
    && unzip chrome-headless-shell-linux64.zip \
    && mv chrome-headless-shell-linux64 /opt/chrome-headless-shell \
    && ln -s /opt/chrome-headless-shell/chrome-headless-shell /usr/local/bin/chrome-headless-shell \
    && rm chrome-headless-shell-linux64.zip \
    && apt-get purge -y wget unzip \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

ENV LAMBDA_TASK_ROOT=/var/task
WORKDIR ${LAMBDA_TASK_ROOT}

# Install Python dependencies
COPY app/requirements.txt .
RUN pip install --no-cache-dir awslambdaric -r requirements.txt

# Pre-cache cdipy protocol files into the image
ENV CDIPY_CHROME_PATH=/usr/local/bin/chrome-headless-shell
ENV CDIPY_CACHE=/var/task/cdipy-cache
RUN python -c "from cdipy.protocol import DOMAINS"
RUN chmod -R 755 /var/task/cdipy-cache
ENV CDIPY_CACHE=/tmp/cdipy-cache

# Copy function code
COPY app/ .

ENTRYPOINT ["python", "-m", "awslambdaric"]
CMD ["handler.lambda_handler"]
