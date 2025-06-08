# Use an official Python runtime as the base image
FROM python:3.12-slim

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    gnupg \
    ca-certificates \
    apt-transport-https \
    wget \
    ffmpeg \
    xvfb \
    pulseaudio \
    libnss3 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    python3-distutils \
    && rm -rf /var/lib/apt/lists/*

# Install distutils for Python 3.12 (to fix 'ModuleNotFoundError: No module named distutils')
RUN apt-get install -y python3-distutils

# Fetch & dearmor Google’s signing key, add Chrome repo
RUN wget -qO - https://dl-ssl.google.com/linux/linux_signing_key.pub \
      | gpg --dearmor --yes -o /usr/share/keyrings/google-chrome-archive-keyring.gpg && \
    echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google-chrome-archive-keyring.gpg] \
      http://dl.google.com/linux/chrome/deb/ stable main" \
      > /etc/apt/sources.list.d/google-chrome.list

# Install Google Chrome
RUN apt-get update && \
    apt-get install -y --no-install-recommends google-chrome-stable && \
    rm -rf /var/lib/apt/lists/*

# Expose port for Flask
EXPOSE 5001

# Set the working directory
WORKDIR /app

# Copy the application code
COPY . .

# Install Python dependencies
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Set environment variable for pulseaudio to avoid user instance conflict
ENV PULSE_SERVER=unix:/run/user/1000/pulse/native

# Start the application with the proper entrypoint
ENTRYPOINT ["/bin/sh", "-c", "pulseaudio --start --exit-idle-time=-1 && Xvfb :99 -screen 0 1920x1080x24 & export DISPLAY=:99 && exec python3 google_meet_bot_web.py"]
