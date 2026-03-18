FROM python:3.12-slim

# Install Chrome and its dependencies
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        wget \
        gnupg \
    && wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | gpg --dearmor -o /usr/share/keyrings/google-chrome.gpg \
    && echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google-chrome.gpg] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends google-chrome-stable \
    && apt-get purge -y wget gnupg \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

# Install Lambda Runtime Interface Client
RUN pip install --no-cache-dir awslambdaric

WORKDIR /app

# Install Python dependencies
COPY app/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy function code
COPY app/ .

ENTRYPOINT ["python", "-m", "awslambdaric"]
CMD ["handler.lambda_handler"]
