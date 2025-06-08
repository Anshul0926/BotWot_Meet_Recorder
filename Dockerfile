# Use an official Python runtime as the base image
FROM python:3.12-slim

# Install system dependencies & key tools in one go
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

# Add Google’s signing key into /usr/share/keyrings, then add the Chrome repo
RUN wget -qO /usr/share/keyrings/google-chrome-archive-keyring.gpg \
      https://dl-ssl.google.com/linux/linux_signing_key.pub && \
    echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google-chrome-archive-keyring.gpg] \
      http://dl.google.com/linux/chrome/deb/ stable main" \
      > /etc/apt/sources.list.d/google-chrome.list

# Install Chrome itself
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      google-chrome-stable && \
    rm -rf /var/lib/apt/lists/*

# Set up PulseAudio socket permissions
RUN mkdir -p /var/run/pulse && \
    chown root:audio /var/run/pulse && \
    chmod 775 /var/run/pulse

# Create and switch to the app directory
WORKDIR /app
COPY . .

# Python deps
RUN pip install --no-cache-dir -r requirements.txt

# Expose app port
EXPOSE 5000

# Launch PulseAudio in the background and start your bot
CMD pulseaudio --start --exit-idle-time=-1 && python google_meet_bot_web.py
