# Stage 1: Install opencode-ai CLI via Node.js (Debian-based to match final image's glibc)
FROM m.daocloud.io/docker.io/library/node:20-bookworm-slim AS opencode

RUN npm install -g opencode-ai@1.15.11 --registry https://registry.npmmirror.com

# Stage 2: Python backend with opencode binary from stage 1
FROM m.daocloud.io/docker.io/library/python:3.11-slim

# Set the working directory in the container
WORKDIR /app

# Replace APT source with Tsinghua mirror for faster downloads in China
RUN sed -i 's|http://deb.debian.org|https://mirrors.tuna.tsinghua.edu.cn|g' /etc/apt/sources.list.d/debian.sources && \
    sed -i 's|http://security.debian.org|https://mirrors.tuna.tsinghua.edu.cn|g' /etc/apt/sources.list.d/debian.sources

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
RUN pip install --no-cache-dir -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# Copy the current directory contents into the container at /app
COPY . /app

# Expose port 8000 for the app to listen on
EXPOSE 8000

# Run uvicorn when the container launches
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
