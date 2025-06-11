import os
import time
import platform
import subprocess
import shutil
import threading
import logging
import re
from datetime import datetime
from flask import Flask, render_template, request, jsonify

import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError

# ─── Logging & Config ───────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

MAX_RECORDING_DURATION = int(os.getenv("MAX_RECORDING_DURATION", 14400))
SCOPES = ["https://www.googleapis.com/auth/drive.file"]
DRIVE_FOLDER_ID = os.getenv("DRIVE_FOLDER_ID", "")

# ─── Globals ────────────────────────────────────────────────────────────────
recording_process = None
output_file = None
driver = None
start_time = None

# ─── Flask App ─────────────────────────────────────────────────────────────
app = Flask(__name__, template_folder="templates")
is_recording = False
record_thread = None

# ─── Google Drive Helpers ──────────────────────────────────────────────────
def setup_google_drive_api():
    creds = None
    if os.path.exists("token.json"):
        try:
            creds = Credentials.from_authorized_user_file("token.json", SCOPES)
            logger.info("Loaded Drive credentials from token.json")
        except Exception:
            pass
    if not creds or not creds.valid:
        flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
        creds = flow.run_local_server(port=0)
        with open("token.json", "w") as f:
            f.write(creds.to_json())
    return build("drive", "v3", credentials=creds)

def upload_to_drive(filename):
    drive = setup_google_drive_api()
    file_metadata = {"name": os.path.basename(filename)}
    if DRIVE_FOLDER_ID:
        file_metadata["parents"] = [DRIVE_FOLDER_ID]
    media = MediaFileUpload(filename, mimetype="video/mp4")
    f = drive.files().create(body=file_metadata, media_body=media, fields="id").execute()
    logger.info(f"Uploaded to Drive with ID {f['id']}")

# ─── Recording Helpers ──────────────────────────────────────────────────────
def check_ffmpeg():
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpeg not found in PATH")

def start_recording(path):
    global recording_process
    system = platform.system()
    if system == "Linux":
        cmd = ["ffmpeg", "-y", "-f", "x11grab", "-s", "1920x1080", "-i", ":0.0", "-f", "pulse", "-i", "default", "-c:v", "libx264", "-c:a", "aac", path]
    elif system == "Darwin":
        cmd = ["ffmpeg", "-y", "-f", "avfoundation", "-i", "1:0", "-c:v", "libx264", "-c:a", "aac", "-vf", "scale=1280x720", "-r", "30", path]
    else:
        cmd = ["ffmpeg", "-y", "-f", "gdigrab", "-i", "desktop", "-c:v", "libx264", "-c:a", "aac", path]
    logger.info("Launching ffmpeg...")
    recording_process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    time.sleep(2)
    if recording_process.poll() is not None:
        out, err = recording_process.communicate()
        raise RuntimeError(f"ffmpeg failed:\n{err}")
    logger.info("Recording started")

def stop_recording():
    global recording_process, output_file
    if recording_process and recording_process.poll() is None:
        logger.info("Stopping recording...")
        recording_process.terminate()
        try:
            recording_process.wait(5)
        except subprocess.TimeoutExpired:
            recording_process.kill()
        if output_file and os.path.exists(output_file) and os.path.getsize(output_file) > 0:
            upload_to_drive(output_file)
        else:
            logger.warning("No valid file to upload")
        
        # Leave the meeting and close the browser window
        try:
            leave_button = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//*[contains(text(), 'Leave call') or contains(@aria-label, 'Leave call')]"))
            )
            driver.execute_script("arguments[0].click();", leave_button)
            logger.info("Left the meeting.")
            driver.quit()  # Close the browser window
            logger.info("Closed the browser window.")
        except Exception as e:
            logger.error(f"Error while leaving the meeting or closing the browser: {e}")
    else:
        logger.info("No recording in progress")

# ─── Google Meet Helpers ───────────────────────────────────────────────────
def validate_meeting_id(mid):
    return bool(re.match(r"^[a-z]{3}-[a-z]{4}-[a-z]{3}$", mid))

def is_meeting_active():
    try:
        leave = driver.find_elements(By.XPATH, "//*[contains(text(),'Leave call') or contains(@aria-label,'Leave call')]")
        if leave:
            return True
        ended = driver.find_elements(By.XPATH, "//*[contains(text(),'Meeting ended')]")
        return not bool(ended)
    except:
        return True

def join_google_meet(link):
    global driver
    try:
        logger.info(f"Navigating to meeting link: {link}")
        driver.get(link)

        # Wait for the name input to appear
        WebDriverWait(driver, 60).until(
            EC.presence_of_element_located((By.XPATH, "//input[@placeholder='Your name']"))
        )
        inp = driver.find_element(By.XPATH, "//input[@placeholder='Your name']")
        inp.clear()
        inp.send_keys("BotWot")

        # Turn off mic and camera if not already
        for lbl in ("camera", "microphone"):
            try:
                btn = WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.XPATH, f"//div[contains(@aria-label,'{lbl}')]")))
                if "Turn off" in btn.get_attribute("aria-label"):
                    btn.click()
            except:
                logger.info(f"No {lbl} button found or already off.")

        # Click 'Continue without microphone and camera' if pop-up appears
        try:
            continue_button = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//span[contains(text(),'Continue without microphone and camera')]"))
            )
            driver.execute_script("arguments[0].click();", continue_button)
            logger.info("Clicked 'Continue without microphone and camera'.")
        except:
            logger.info("No 'Continue without microphone and camera' button found.")

        # Check and click 'Got it' on the pop-up
        try:
            # Use a more robust XPath to account for case variations and structure
            got_it_button = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//button[contains(translate(text(), 'GOTIT', 'gotit'), 'got it')]"))
            )
            driver.execute_script("arguments[0].click();", got_it_button)
            logger.info("Clicked 'Got it' on the pop-up.")
        except Exception as e:
            logger.info(f"'Got it' pop-up did not appear or could not be clicked: {str(e)}")

        # Click Join button
        join = WebDriverWait(driver, 60).until(EC.any_of(
            EC.element_to_be_clickable((By.XPATH, "//*[contains(text(),'Join now')]")),
            EC.element_to_be_clickable((By.XPATH, "//*[contains(text(),'Ask to join')]"))
        ))
        driver.execute_script("arguments[0].click();", join)
        WebDriverWait(driver, 60).until(EC.presence_of_element_located((By.XPATH, "//*[contains(text(),'Leave call') or contains(@aria-label,'Leave call')]")))
        logger.info("Joined Meet")
    except Exception as e:
        logger.error(f"Error joining Google Meet: {e}")
        if driver:
            driver.quit()
        # Reinitialize driver here if needed
        init_driver_and_join_meeting(link)

# ─── Driver Reinitialization Function ───────────────────────────────────────
def init_driver_and_join_meeting(link):
    global driver
    opts = uc.ChromeOptions()
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    prefs = {"profile.default_content_setting_values.media_stream_mic": 2,
             "profile.default_content_setting_values.media_stream_camera": 2}
    opts.add_experimental_option("prefs", prefs)

    driver = uc.Chrome(options=opts, headless=False)
    join_google_meet(link)

# ─── Bot Lifecycle ─────────────────────────────────────────────────────────
def start_bot(meet_link):
    global driver, output_file, start_time
    # launch pulse & xvfb on Linux
    if platform.system() == "Linux":
        subprocess.Popen(["Xvfb", ":0", "-screen", "0", "1920x1080x24"])
        subprocess.Popen(["pulseaudio", "--start"])
        os.environ["DISPLAY"] = ":0.0"

    opts = uc.ChromeOptions()
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    prefs = {"profile.default_content_setting_values.media_stream_mic": 2,
             "profile.default_content_setting_values.media_stream_camera": 2}
    opts.add_experimental_option("prefs", prefs)

    driver = uc.Chrome(options=opts, headless=False)
    join_google_meet(meet_link)
    check_ffmpeg()
    output_file = f"meeting_{datetime.now():%Y%m%d_%H%M%S}.mp4"
    start_recording(output_file)
    start_time = time.time()

    # monitor
    while is_meeting_active() and (time.time() - start_time) < MAX_RECORDING_DURATION:
        time.sleep(30)
    stop_recording()
    driver.quit()

# ─── Flask Routes ──────────────────────────────────────────────────────────
@app.route("/", methods=["GET", "POST"])
def index():
    global is_recording, record_thread
    error = None
    if request.method == "POST":
        mid = request.form.get("meeting_id", "").strip()
        if not validate_meeting_id(mid):
            error = "Invalid Meet ID. Use xxx-xxxx-xxx."
        else:
            url = f"https://meet.google.com/{mid}"
            record_thread = threading.Thread(target=start_bot, args=(url,))
            record_thread.daemon = True
            record_thread.start()
            is_recording = True
    return render_template("index.html", error=error, is_recording=is_recording)

@app.route("/control", methods=["POST"])
def control():
    global is_recording
    action = request.form.get("action")

    # START recording
    if action == "start":
        meeting_id = request.form.get("meeting_id", "").strip()
        if not meeting_id:
            return jsonify({"message": "No meeting ID provided."}), 400

        if is_recording:
            return jsonify({"message": "Already recording."}), 400

        # Validate the meeting ID
        if not validate_meeting_id(meeting_id):
            return jsonify({"message": "Invalid Meet ID."}), 400

        # Construct meet link
        meet_link = f"https://meet.google.com/{meeting_id}"
        
        # Start bot in background thread
        record_thread = threading.Thread(target=start_bot, args=(meet_link,))
        record_thread.daemon = True
        record_thread.start()

        is_recording = True
        return jsonify({"status": "started"}), 200

    # STOP recording
    elif action == "stop":
        if not is_recording:
            return jsonify({"message": "No recording in progress."}), 400

        stop_recording()
        is_recording = False
        return jsonify({"status": "stopped"}), 200

    return jsonify({"message": "Invalid action."}), 400

# ─── Entrypoint ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    app.run(host="0.0.0.0", port=port, debug=True)