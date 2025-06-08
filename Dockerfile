# Use an official Python runtime as the base image
FROM python:3.12-slim

# Install dependencies
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
    libasound2 && \
    rm -rf /var/lib/apt/lists/*

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

# Prepare PulseAudio socket permissions
RUN mkdir -p /var/run/pulse && \
    chown root:audio /var/run/pulse && \
    chmod 775 /var/run/pulse

# Set the PULSE_SERVER environment variable for Pulseaudio
ENV PULSE_SERVER=unix:/run/user/1000/pulse/native

# Expose port
EXPOSE 5001

# Set up the working directory
WORKDIR /app

# Copy application files
COPY . .

# Install Python dependencies
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Entry point command
ENTRYPOINT ["/bin/bash", "-c", "pulseaudio --start --exit-idle-time=-1 && exec python3 google_meet_bot_web.py"]
