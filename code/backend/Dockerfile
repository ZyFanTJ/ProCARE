# Stage 1: Install opencode-ai CLI via Node.js (Debian-based to match final image's glibc)
FROM node:20-bookworm-slim AS opencode

RUN npm install -g opencode-ai@1.15.11

# Stage 2: Python backend with opencode binary from stage 1
FROM python:3.11-slim

# Set the working directory in the container
WORKDIR /app

# Configure APT sources with fallback (try official, fallback to Aliyun for China network)
RUN set -e; \
    apt-get update || { \
        echo "Official source failed, trying Aliyun mirror..."; \
        sed -i 's|http://deb.debian.org|https://mirrors.aliyun.com|g' /etc/apt/sources.list.d/debian.sources; \
        sed -i 's|http://security.debian.org|https://mirrors.aliyun.com|g' /etc/apt/sources.list.d/debian.sources; \
        apt-get update; \
    }

# Install system dependencies (including LaTeX toolchain for paper export)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    texlive-xetex \
    texlive-fonts-recommended \
    texlive-latex-extra \
    texlive-lang-chinese \
    latexmk \
    fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

# Copy opencode binary from stage 1
COPY --from=opencode /usr/local/lib/node_modules /usr/local/lib/node_modules
COPY --from=opencode /usr/local/bin/opencode /usr/local/bin/opencode

# Copy the requirements file into the container at /app
COPY requirements.txt /app/

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt || \
    pip install --no-cache-dir -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/

# Copy the current directory contents into the container at /app
COPY . /app

# Expose port 8000 for the app to listen on
EXPOSE 8000

# Run uvicorn when the container launches
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
