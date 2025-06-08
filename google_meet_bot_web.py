import os
import time
import tkinter as tk
from tkinter import messagebox
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError
import subprocess
import logging
import re
import shutil
from datetime import datetime
import platform
import signal
import sys

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Configuration
MAX_RECORDING_DURATION = int(os.getenv("MAX_RECORDING_DURATION", 14400))  # 4 hours in seconds
CHECK_INTERVAL = 30  # Check meeting status every 30 seconds (in seconds)
CHECK_INTERVAL_MS = CHECK_INTERVAL * 1000  # Convert to milliseconds for Tkinter's after method
SCOPES = ['https://www.googleapis.com/auth/drive.file']
DRIVE_FOLDER_ID = os.getenv("DRIVE_FOLDER_ID", "")  # Optional: Specific folder ID in Google Drive

# Global variables to track recording process and state
recording_process = None
output_file = None
driver = None
root = None
stop_button = None
start_time = None

def setup_google_drive_api():
    """Authenticate and set up Google Drive API client."""
    logger.info("Setting up Google Drive API authentication...")
    creds = None
    if os.path.exists('token.json'):
        try:
            creds = Credentials.from_authorized_user_file('token.json', SCOPES)
            logger.info("Loaded credentials from token.json")
        except Exception as e:
            logger.warning(f"Failed to load token.json: {e}. Will attempt to re-authenticate.")
    if not creds or not creds.valid:
        try:
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
            with open('token.json', 'w') as token:
                token.write(creds.to_json())
            logger.info("New token.json generated successfully.")
        except Exception as e:
            logger.error(f"Failed to authenticate with Google Drive API: {e}")
            raise
    logger.info("Google Drive API authentication successful.")
    return build('drive', 'v3', credentials=creds)

def upload_to_drive(filename, drive_service):
    """Upload the recorded file to Google Drive."""
    logger.info(f"Uploading file '{filename}' to Google Drive...")
    file_metadata = {
        'name': os.path.basename(filename),
        'parents': [DRIVE_FOLDER_ID] if DRIVE_FOLDER_ID else []
    }
    media = MediaFileUpload(filename, mimetype='video/mp4')
    try:
        file = drive_service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id'
        ).execute()
        logger.info(f"File uploaded successfully to Google Drive with ID: {file.get('id')}")
        return file.get('id')
    except HttpError as e:
        logger.error(f"Google Drive API error during upload: {e}")
        logger.error(f"Error details: {e.content}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error during upload to Google Drive: {e}")
        raise

def check_ffmpeg():
    """Check if ffmpeg is installed and available in PATH."""
    logger.info("Checking for ffmpeg installation...")
    ffmpeg_path = shutil.which("ffmpeg")
    if ffmpeg_path is None:
        logger.error("ffmpeg is not installed or not found in PATH. Please install ffmpeg to enable recording.")
        raise Exception("ffmpeg is not installed or not found in PATH. Please install ffmpeg to enable recording.")
    logger.info(f"ffmpeg found at: {ffmpeg_path}")

def start_recording(output_file_path):
    """Start screen recording using ffmpeg."""
    global recording_process
    logger.info(f"Preparing to start recording to file: {output_file_path}")
    system = platform.system()
    if system == "Linux":
        cmd = [
            'ffmpeg',
            '-y',
            '-f', 'x11grab',
            '-s', '1920x1080',
            '-i', ':0.0',
            '-f', 'pulse',
            '-i', 'default',
            '-c:v', 'libx264',
            '-c:a', 'aac',
            output_file_path
        ]
    elif system == "Darwin":  # macOS
        # List devices to help debug if needed
        try:
            result = subprocess.run(['ffmpeg', '-f', 'avfoundation', '-list_devices', 'true', '-i', ''], 
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            logger.info(f"avfoundation devices: stdout={result.stdout}, stderr={result.stderr}")
        except Exception as e:
            logger.warning(f"Failed to list avfoundation devices: {e}")
        cmd = [
            'ffmpeg',
            '-y',
            '-f', 'avfoundation',
            '-i', '1:0',  # 1:0 for screen and default audio (adjust if needed)
            '-c:v', 'libx264',
            '-c:a', 'aac',
            '-vf', 'scale=1280:720',
            '-r', '30',  # Frame rate
            output_file_path
        ]
    else:  # Windows
        cmd = [
            'ffmpeg',
            '-y',
            '-f', 'gdigrab',
            '-i', 'desktop',
            '-c:v', 'libx264',
            '-c:a', 'aac',
            output_file_path
        ]
    try:
        # Start ffmpeg in the background
        recording_process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        # Wait a moment to check if it started successfully
        time.sleep(2)
        if recording_process.poll() is None:
            # Check if the file is being written to
            if not os.path.exists(output_file_path) or os.path.getsize(output_file_path) == 0:
                stdout, stderr = recording_process.communicate()
                logger.error(f"ffmpeg started but file is empty or not created. stdout: {stdout}, stderr: {stderr}")
                logger.error("If the error mentions 'Input/output error', ensure Terminal has screen and audio recording permissions in System Settings > Privacy & Security.")
                recording_process.terminate()
                raise Exception("ffmpeg started but no data is being recorded. Check permissions or device indices.")
            logger.info("Recording started successfully.")
            if stop_button:
                stop_button.config(state=tk.NORMAL)  # Enable the stop button
        else:
            stdout, stderr = recording_process.communicate()
            logger.error(f"ffmpeg failed to start. stdout: {stdout}, stderr: {stderr}")
            logger.error("If the error mentions 'Input/output error', ensure Terminal has screen and audio recording permissions in System Settings > Privacy & Security.")
            raise Exception(f"ffmpeg failed to start: {stderr}")
    except Exception as e:
        logger.error(f"Failed to start recording: {e}")
        if recording_process:
            recording_process.terminate()
        raise

def stop_recording():
    """Stop the recording process and upload to Google Drive."""
    global recording_process, output_file
    if recording_process and recording_process.poll() is None:  # Check if process is still running
        logger.info("Stopping recording...")
        recording_process.terminate()
        stdout, stderr = recording_process.communicate()
        logger.info(f"Recording process stdout: {stdout}, stderr: {stderr}")
        try:
            recording_process.wait(timeout=10)
            logger.info("Recording stopped successfully.")
        except subprocess.TimeoutExpired:
            logger.warning("Recording process did not terminate in time, killing it...")
            recording_process.kill()
        if stop_button:
            stop_button.config(state=tk.DISABLED)  # Disable the stop button

        # Upload to Google Drive if file exists and has content
        if output_file and os.path.exists(output_file) and os.path.getsize(output_file) > 0:
            try:
                drive_service = setup_google_drive_api()
                upload_to_drive(output_file, drive_service)
                logger.info("Recording uploaded to Google Drive successfully.")
            except Exception as e:
                logger.error(f"Failed to upload recording to Google Drive: {e}")
        else:
            logger.warning("No valid recording file to upload.")
    else:
        logger.info("No active recording to stop.")

def is_meeting_active(driver):
    """Check if the Google Meet is still active."""
    logger.info("Checking if meeting is still active...")
    try:
        leave_button = driver.find_elements(By.XPATH, "//*[contains(text(), 'Leave call') or contains(@aria-label, 'Leave call')]")
        if leave_button:
            logger.info("Meeting is active (Leave call button found).")
            return True
        ended_message = driver.find_elements(By.XPATH, "//*[contains(text(), 'Meeting ended')]")
        if ended_message:
            logger.info("Meeting has ended (Meeting ended message found).")
            return False
        logger.info("Meeting status unclear, assuming active.")
        return True
    except Exception as e:
        logger.warning(f"Error checking meeting status: {e}")
        return False

def join_google_meet(driver, meet_link):
    """Join a Google Meet as a guest with camera and mic off, and set name to BotWot."""
    logger.info(f"Navigating to meeting link: {meet_link}")
    driver.get(meet_link)
    
    try:
        # Handle any browser alerts/pop-ups
        try:
            driver.switch_to.alert.dismiss()
            logger.info("Dismissed browser alert/pop-up.")
        except:
            pass

        # Wait for the name input field (guest mode)
        WebDriverWait(driver, 60).until(
            EC.presence_of_element_located((By.XPATH, "//input[@placeholder='Your name']"))
        )
        name_input = driver.find_element(By.XPATH, "//input[@placeholder='Your name']")
        logger.info("Name input field found. Entering 'BotWot'...")
        name_input.clear()
        name_input.send_keys("BotWot")

        # Check for "Continue without microphone and camera" pop-up
        try:
            continue_button = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//*[contains(text(), 'Continue without microphone and camera')]"))
            )
            driver.execute_script("arguments[0].click();", continue_button)
            logger.info("Clicked 'Continue without microphone and camera' button.")
        except:
            logger.info("No 'Continue without microphone and camera' button found. Proceeding with manual toggle.")

        # Toggle off mic/camera on preview page if not already done
        try:
            camera_button = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.XPATH, "//div[contains(@aria-label, 'camera') or contains(@data-is-muted, 'true')]"))
            )
            if "Turn off camera" in camera_button.get_attribute("aria-label"):
                driver.execute_script("arguments[0].click();", camera_button)
                logger.info("Camera turned off on preview page.")
            else:
                logger.info("Camera already off on preview page.")
        except:
            logger.warning("Camera toggle not found on preview page.")

        try:
            mic_button = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.XPATH, "//div[contains(@aria-label, 'microphone') or contains(@data-is-muted, 'true')]"))
            )
            if "Turn off microphone" in mic_button.get_attribute("aria-label"):
                driver.execute_script("arguments[0].click();", mic_button)
                logger.info("Microphone turned off on preview page.")
            else:
                logger.info("Microphone already off on preview page.")
        except:
            logger.warning("Microphone toggle not found on preview page.")

        # Join the meeting
        max_attempts = 3
        joined = False
        for attempt in range(max_attempts):
            logger.info(f"Attempt {attempt + 1}/{max_attempts} to join the meeting...")
            try:
                join_element = WebDriverWait(driver, 60).until(
                    EC.any_of(
                        EC.element_to_be_clickable((By.XPATH, "//*[contains(text(), 'Join now')]")),
                        EC.element_to_be_clickable((By.XPATH, "//*[contains(text(), 'Ask to join')]"))
                    )
                )
                driver.execute_script("arguments[0].scrollIntoView(true);", join_element)
                time.sleep(1)
                try:
                    if "Join now" in join_element.text:
                        logger.info("Found 'Join now' button. Clicking...")
                        driver.execute_script("arguments[0].click();", join_element)
                    else:
                        logger.info("Found 'Ask to join' button. Clicking...")
                        driver.execute_script("arguments[0].click();", join_element)
                        # Wait for admission with a more robust check
                        WebDriverWait(driver, 60).until(
                            EC.any_of(
                                EC.presence_of_element_located((By.XPATH, "//*[contains(text(), 'Leave call') or contains(@aria-label, 'Leave call')]")),
                                EC.presence_of_element_located((By.XPATH, "//button[@aria-label='Chat with everyone']"))
                            )
                        )
                        logger.info("Successfully admitted to the meeting.")
                except Exception as e:
                    logger.warning(f"JavaScript click failed: {e}. Retrying with ActionChains...")
                    actions = ActionChains(driver)
                    actions.move_to_element(join_element).click().perform()

                # Confirm join with a more robust check
                WebDriverWait(driver, 60).until(
                    EC.any_of(
                        EC.presence_of_element_located((By.XPATH, "//*[contains(text(), 'Leave call') or contains(@aria-label, 'Leave call')]")),
                        EC.presence_of_element_located((By.XPATH, "//button[@aria-label='Chat with everyone']"))
                    )
                )
                logger.info("Successfully joined the Google Meet as BotWot.")
                joined = True
                break
            except Exception as e:
                logger.warning(f"Join attempt {attempt + 1} failed: {e}")
                try:
                    overlay = driver.find_element(By.XPATH, "//div[contains(@class, 'uW2Fw-IE5DDf')]")
                    driver.execute_script("arguments[0].remove();", overlay)
                    logger.info("Removed overlay blocking the join button.")
                except:
                    logger.info("No overlay found to remove.")
                if attempt == max_attempts - 1:
                    raise
                time.sleep(5)

        if not joined:
            raise Exception("Failed to join meeting after all attempts.")

        # Wait for UI to stabilize
        time.sleep(5)

        # Check if meeting is still active before proceeding
        if not is_meeting_active(driver):
            raise Exception("Meeting ended immediately after joining.")

    except Exception as e:
        logger.error(f"Failed to join meeting: {e}")
        driver.save_screenshot("join_error_screenshot.png")
        raise

def validate_meeting_id(meeting_id):
    """Validate Google Meet meeting ID format."""
    logger.info(f"Validating meeting ID: {meeting_id}")
    pattern = r'^[a-z]{3}-[a-z]{4}-[a-z]{3}$'
    is_valid = bool(re.match(pattern, str(meeting_id)))
    logger.info(f"Meeting ID validation result: {is_valid}")
    return is_valid

def create_dialog_box():
    """Create a Tkinter dialog box to input the meeting ID."""
    global root, stop_button
    logger.info("Creating Tkinter dialog box for meeting ID input...")
    def on_submit():
        meeting_id = entry.get().strip()
        if validate_meeting_id(meeting_id):
            meet_link = f"https://meet.google.com/{meeting_id}"
            logger.info(f"Valid meeting ID entered. Meeting link: {meet_link}")
            start_bot(meet_link)
        else:
            logger.warning(f"Invalid meeting ID entered: {meeting_id}")
            messagebox.showerror("Invalid Input", "Please enter a valid meeting ID (e.g., xxx-xxxx-xxx).")
    
    def on_stop():
        stop_recording()
        messagebox.showinfo("Recording Stopped", "Recording has been stopped and will be uploaded to Google Drive if a valid file exists.")

    root = tk.Tk()
    root.title("Google Meet Recorder")
    root.geometry("300x200")
    
    tk.Label(root, text="Enter Google Meet ID (e.g., xxx-xxxx-xxx):").pack(pady=10)
    entry = tk.Entry(root, width=20)
    entry.pack(pady=10)
    
    tk.Button(root, text="Start Recording", command=on_submit).pack(pady=10)
    
    stop_button = tk.Button(root, text="Stop Recording", command=on_stop, state=tk.DISABLED)
    stop_button.pack(pady=10)
    
    logger.info("Tkinter dialog box displayed. Waiting for user input...")
    root.protocol("WM_DELETE_WINDOW", cleanup_and_exit)  # Handle window close
    root.mainloop()

def cleanup_and_exit():
    """Clean up resources and exit the application."""
    logger.info("Cleaning up and exiting...")
    stop_recording()
    if driver:
        try:
            driver.quit()
            logger.info("Chrome driver closed successfully.")
        except Exception as e:
            logger.warning(f"Error closing driver: {e}")
    if output_file and os.path.exists(output_file):
        os.remove(output_file)
        logger.info(f"Cleaned up local recording file: {output_file}")
    if root:
        root.destroy()
    logger.info("Script execution completed.")
    sys.exit(0)

def signal_handler(sig, frame):
    """Handle Ctrl+C gracefully."""
    logger.info("Received interrupt signal, cleaning up...")
    cleanup_and_exit()

def check_meeting_status():
    """Periodically check if the meeting is still active."""
    if is_meeting_active(driver) and (time.time() - start_time) < MAX_RECORDING_DURATION:
        logger.info("Meeting is still active. Continuing recording...")
        root.after(CHECK_INTERVAL_MS, check_meeting_status)  # Schedule the next check
    else:
        logger.info("Meeting ended or max duration reached. Stopping recording...")
        stop_recording()
        cleanup_and_exit()

def start_bot(meet_link):
    """Start the bot to record the meeting and save to Google Drive."""
    global driver, output_file, start_time
    logger.info("Starting bot process...")
    system = platform.system()
    if system == "Linux":
        os.environ['DISPLAY'] = ':0.0'
        subprocess.Popen(['Xvfb', ':0', '-screen', '0', '1920x1080x24'])
        subprocess.Popen(['pulseaudio', '--start'])

    prefs = {
        "profile.default_content_setting_values.media_stream_mic": 2,
        "profile.default_content_setting_values.media_stream_camera": 2
    }
    options = uc.ChromeOptions()
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_argument('--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.7151.69 Safari/537.36')
    options.add_argument('--start-maximized')
    options.add_argument('--disable-gpu')
    options.add_argument('--disable-extensions')
    options.add_argument('--disable-notifications')
    options.add_experimental_option("prefs", prefs)

    try:
        logger.info("Initializing Chrome driver...")
        driver = uc.Chrome(options=options, headless=False)
        logger.info("Chrome driver initialized successfully.")

        join_google_meet(driver, meet_link)

        # Start recording immediately after joining
        check_ffmpeg()
        logger.info("ffmpeg check passed. Proceeding with recording.")
        
        output_file = f"meeting_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4"
        logger.info(f"Recording file will be saved as: {output_file}")
        start_recording(output_file)
        
        start_time = time.time()
        logger.info("Starting recording loop...")
        root.after(CHECK_INTERVAL_MS, check_meeting_status)  # Start periodic checking
        
    except Exception as e:
        logger.error(f"An error occurred during bot execution: {e}")
        cleanup_and_exit()

if __name__ == "__main__":
    # Set up signal handler for Ctrl+C
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    logger.info("Script execution started...")
    create_dialog_box()