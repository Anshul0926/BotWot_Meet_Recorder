# Use an official Python runtime as the base image
FROM python:3.12-slim

# 1) Install system deps + GPG tooling in one layer
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

# 2) Fetch & dearmor Google’s signing key, add Chrome repo
RUN wget -qO - https://dl-ssl.google.com/linux/linux_signing_key.pub \
      | gpg --dearmor --yes -o /usr/share/keyrings/google-chrome-archive-keyring.gpg && \
    echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google-chrome-archive-keyring.gpg] \
      http://dl.google.com/linux/chrome/deb/ stable main" \
      > /etc/apt/sources.list.d/google-chrome.list

# 3) Install Chrome itself
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      google-chrome-stable && \
    rm -rf /var/lib/apt/lists/*

# 4) Prepare PulseAudio socket permissions
RUN mkdir -p /var/run/pulse && \
    chown root:audio /var/run/pulse && \
    chmod 775 /var/run/pulse

# 5) Copy application code into /app
WORKDIR /app
COPY . .

# 6) Install Python dependencies
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# 7) Expose port and set up container start commands
EXPOSE 5000

# Start PulseAudio, then run your script via python3
ENTRYPOINT ["pulseaudio", "--start", "--exit-idle-time=-1"]
CMD ["python3", "google_meet_bot_web.py"]
