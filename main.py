# main.py
#
# Raspberry Pi Pico W code for a 6-digit random code generator that:
# - Displays the code on a web page.
# - Activates a servo motor when the correct code is entered on a keypad.
# - Resets the servo when a motion detector is triggered.

# Import necessary libraries
import network
import socket
import time
from machine import Pin, PWM, I2C, SPI
import random
import json
import urequests
from lib.keypad import Keypad
from lib.mfrc522 import MFRC522
from lib.ssd1306 import SSD1306_I2C

# --- Hardware Setup ---
# IMPORTANT: These are the GPIO pin numbers.
# Please ensure your hardware is connected to these pins.
SERVO_PIN = 15          # Pin for the servo motor's data line
MOTION_PIN = 28         # Pin for the PIR motion sensor's output
KEYPAD_ROWS = [0, 1, 2, 3] # Pins for the keypad rows
KEYPAD_COLS = [4, 5, 6]   # Pins for the keypad columns

# LED and Buzzer Pins
RED_LED_PIN = 13
GREEN_LED_PIN = 14
BLUE_LED_PIN = 16
BUZZER_PIN = 17

# OLED Display (SSD1306)
# Connect your I2C OLED display to these pins.
OLED_SDA_PIN = 20
OLED_SCL_PIN = 21
OLED_WIDTH = 128
OLED_HEIGHT = 64

# RFID Module (RC522)
# Connect your RC522 module to these pins.
RFID_SDA = 8  # SDA / CS pin
RFID_SCK = 10 # SCK pin
RFID_MOSI = 11 # MOSI pin
RFID_MISO = 12 # MISO pin
RFID_RST = 9  # RST pin

# --- RFID Configuration ---
AUTHORIZED_TAGS_FILE = "authorized_tags.json"
MAX_AUTHORIZED_TAGS = 2

# --- Lock Configuration ---
MOTION_IGNORE_DELAY_S = 3 # Seconds to ignore motion after unlocking
REMOTE_UNLOCK_PASSWORD = "YOUR_SECRET_PASSWORD" # Change this!
DURESS_CODE = "911911" # A 6-digit code that secretly triggers an alert
IFTTT_WEBHOOK_URL = "YOUR_IFTTT_WEBHOOK_URL_HERE" # e.g., https://maker.ifttt.com/trigger/duress_alert/with/key/YOUR_KEY

# --- WiFi Configuration ---
# IMPORTANT: Replace these with your WiFi network credentials.
WIFI_SSID = "YOUR_WIFI_SSID"
WIFI_PASSWORD = "YOUR_WIFI_PASSWORD"

# --- Functions ---
def log_event(message):
    """Adds a timestamped event to the log."""
    global event_log
    # In MicroPython, time.time() might not be available or might not be a real-time clock.
    # Using time.ticks_ms() is a more reliable way to get an uptime-based timestamp.
    timestamp_ms = time.ticks_ms()
    log_entry = f"{timestamp_ms // 1000}s: {message}"
    event_log.insert(0, log_entry) # Add to the top
    if len(event_log) > MAX_LOG_ENTRIES:
        event_log.pop()
    print(f"LOG: {log_entry}") # Also print to console for debugging

def load_authorized_tags():
    """Loads authorized RFID tag UIDs from a file."""
    try:
        with open(AUTHORIZED_TAGS_FILE, "r") as f:
            return json.load(f)
    except (OSError, ValueError):
        # File doesn't exist or is invalid
        return []

def save_authorized_tags(tags):
    """Saves a list of authorized RFID tag UIDs to a file."""
    with open(AUTHORIZED_TAGS_FILE, "w") as f:
        json.dump(tags, f)

def play_tone(buzzer, frequency, duration):
    """Plays a tone on the buzzer."""
    buzzer.duty_u16(32768) # 50% duty cycle for maximum volume
    buzzer.freq(frequency)
    time.sleep(duration)
    buzzer.duty_u16(0)

def play_success_tone(buzzer):
    """Plays a success tone."""
    play_tone(buzzer, 600, 0.1)
    time.sleep(0.05)
    play_tone(buzzer, 800, 0.1)
    time.sleep(0.05)
    play_tone(buzzer, 1000, 0.1)

def play_error_tone(buzzer):
    """Plays an error tone."""
    play_tone(buzzer, 200, 0.3)

def play_program_tone(buzzer):
    """Plays a short tone for RFID programming."""
    play_tone(buzzer, 500, 0.1)

def update_display(oled, status, code=""):
    """Updates the OLED display with the current status and code."""
    oled.fill(0)
    oled.text("Status:", 0, 0)
    oled.text(status, 0, 10)
    if code:
        oled.text("Code:", 0, 30)
        oled.text(code, 0, 40)
    oled.show()

def display_message(oled, line1, line2="", duration_s=2):
    """Displays a temporary message on the OLED."""
    oled.fill(0)
    oled.text(line1, 0, 10)
    if line2:
        oled.text(line2, 0, 30)
    oled.show()
    if duration_s > 0:
        time.sleep(duration_s)

def trigger_duress_notification():
    """Sends a web request to IFTTT to trigger a notification."""
    if not IFTTT_WEBHOOK_URL.startswith("YOUR_IFTTT"):
        try:
            print("Sending duress notification...")
            response = urequests.post(IFTTT_WEBHOOK_URL)
            response.close()
            log_event("Duress notification sent")
        except Exception as e:
            print(f"Failed to send duress notification: {e}")
            log_event("Duress notification failed")
    else:
        print("IFTTT webhook URL not configured.")
        log_event("Duress trigger failed: no URL")

def set_servo_angle(servo, angle):
    """Sets the servo to a specific angle."""
    # This conversion might need tuning for your specific servo
    min_duty = 1000  # Corresponds to 0 degrees
    max_duty = 9000  # Corresponds to 180 degrees
    duty = min_duty + (max_duty - min_duty) * (angle / 180)
    servo.duty_u16(int(duty))

def connect_wifi(ssid, password):
    """Connects the Pico W to the specified WiFi network."""
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    wlan.connect(ssid, password)

    # Wait for connection
    max_wait = 10
    while max_wait > 0:
        if wlan.status() < 0 or wlan.status() >= 3:
            break
        max_wait -= 1
        print('Waiting for connection...')
        time.sleep(1)

    if wlan.status() != 3:
        raise RuntimeError('WiFi connection failed')
    else:
        print('Connected')
        status = wlan.ifconfig()
        print('IP = ' + status[0])
    return status[0]

def generate_code():
    """Generates a 6-digit random code."""
    return "".join([str(random.randint(0, 9)) for _ in range(6)])

def get_keypad_or_rfid_input(keypad_instance, rfid_reader_instance, authorized_tags_list, system_state, socket_instance, code, ip, log):
    """
    Waits for keypad input or a valid RFID scan.
    Returns the entered code or a special value for RFID bypass.
    """
    entered_code = ""
    print("Enter the 6-digit code or scan an authorized RFID tag...")

    while len(entered_code) < 6:
        # 1. Check for RFID tag
        (stat, tag_type) = rfid_reader_instance.request(rfid_reader_instance.REQIDL)
        if stat == rfid_reader_instance.OK:
            (stat, raw_uid) = rfid_reader_instance.anticoll()
            if stat == rfid_reader_instance.OK:
                uid = "0x%02x%02x%02x%02x" % (raw_uid[0], raw_uid[1], raw_uid[2], raw_uid[3])
                if uid in authorized_tags_list:
                    print(f"Authorized RFID tag scanned: {uid}")
                    return "RFID_BYPASS"
                else:
                    print(f"Unauthorized RFID tag scanned: {uid}")
                time.sleep(1) # Wait for tag to be removed

        # 2. Check for keypad input
        key = keypad_instance.scan()
        if key:
            entered_code += key
            print(f"Entered: {entered_code}")
            time.sleep(0.3)
            # Check for duress code immediately after 6 digits are entered
            if len(entered_code) == 6 and entered_code == DURESS_CODE:
                return "DURESS_UNLOCK"

        # 3. Handle web requests
        if socket_instance is not None:
            try:
                cl, addr = socket_instance.accept()
                try:
                    print('Client connected from', addr)
                    request = cl.recv(1024)
                    request_str = request.decode('utf-8')

                    # Check for POST request for remote unlock
                    if "POST /" in request_str:
                        # Super simple code parsing
                        body_start = request_str.find("code=")
                        if body_start != -1:
                            # Access code is always 6 digits
                            code_submitted = request_str[body_start + 5:body_start + 11]
                            if code_submitted == "576809":
                                cl.close()
                                return "REMOTE_UNLOCK"

                    # Otherwise, serve the normal page
                    response = web_page(code, ip, system_state, log)
                    cl.send('HTTP/1.0 200 OK\r\nContent-type: text/html\r\n\r\n')
                    cl.send(response)
                finally:
                    cl.close()
            except OSError:
                pass

    return entered_code

def web_page(code, ip, status, log):
    """Creates an enhanced HTML page to display status, code, and logs."""

    log_html = "".join([f"<li>{entry}</li>" for entry in log])

    html = f"""
    <html>
        <head>
            <title>Pico W Security</title>
            <meta http-equiv="refresh" content="30">
            <style>
                .blurred {{
                    filter: blur(5px);
                    user-select: none;
                    transition: filter 0.3s;
                }}
                .blurred:hover {{
                    filter: blur(2px);
                }}
                .keypad {{
                    display: grid;
                    grid-template-columns: repeat(3, 1fr);
                    gap: 10px;
                    max-width: 250px;
                    margin: 20px 0;
                }}
                .keypad button {{
                    padding: 15px;
                    font-size: 1.2em;
                    cursor: pointer;
                }}
                #entered-code {{
                    font-size: 2em;
                    letter-spacing: 10px;
                    margin: 10px 0;
                    font-family: monospace;
                    font-weight: bold;
                    color: #333;
                }}
            </style>
        </head>
        <body>
            <h1>Pico W Security System</h1>
            <p><strong>Status:</strong> {status}</p>
            <hr>
            <h2>Access Code</h2>
            <p>To unlock the door, you must enter the following code:</p>
            <h2 style="color: blue;">{code}</h2>
            <hr>
            <h2>Remote Control Code</h2>
            <p>Use this code for the Digital Remote Control below:</p>
            <h2 class="blurred" style="color: green;">576809</h2>
            <hr>
            <h3>Digital Remote Control</h3>
            <p>Enter 6-digit code to unlock:</p>
            <div id="entered-code">______</div>
            <div class="keypad">
                <button onclick="press('1')">1</button><button onclick="press('2')">2</button><button onclick="press('3')">3</button>
                <button onclick="press('4')">4</button><button onclick="press('5')">5</button><button onclick="press('6')">6</button>
                <button onclick="press('7')">7</button><button onclick="press('8')">8</button><button onclick="press('9')">9</button>
                <button onclick="press('C')">C</button><button onclick="press('0')">0</button><button onclick="press('OK')">OK</button>
            </div>
            <form id="unlock-form" action="/" method="post">
                <input type="hidden" name="code" id="code-input">
            </form>
            <script>
                let entered = "";
                const display = document.getElementById('entered-code');
                const input = document.getElementById('code-input');
                const form = document.getElementById('unlock-form');
                function press(key) {{
                    if (key === 'C') {{
                        entered = "";
                    }} else if (key === 'OK') {{
                        if (entered.length === 6) {{
                            input.value = entered;
                            form.submit();
                        }} else {{
                            alert("Please enter 6 digits.");
                        }}
                    }} else {{
                        if (entered.length < 6) {{
                            entered += key;
                        }}
                    }}
                    display.innerText = entered.padEnd(6, "_");
                }}
            </script>
            <hr>
            <h3>Event Log</h3>
            <ul>
                {log_html}
            </ul>
            <p>Connect to your Pico W at: {ip}</p>
        </body>
    </html>
    """
    return html

# --- Global variables for web server access ---
s = None
access_code = ""
ip_address = ""
event_log = []
MAX_LOG_ENTRIES = 10

# --- Main Loop ---
if __name__ == "__main__":
    system_state = "LOCKED"
    oled = None
    print("Starting security system...")

    # --- Initialize Hardware ---
    servo = PWM(Pin(SERVO_PIN))
    servo.freq(50)
    motion_sensor = Pin(MOTION_PIN, Pin.IN)
    keypad = Keypad(KEYPAD_ROWS, KEYPAD_COLS)
    spi = SPI(1, baudrate=2500000, polarity=0, phase=0, sck=Pin(RFID_SCK), mosi=Pin(RFID_MOSI), miso=Pin(RFID_MISO))
    rfid_reader = MFRC522(spi=spi, gpioRst=RFID_RST, gpioCs=RFID_SDA)

    # Initialize LEDs and Buzzer
    red_led = Pin(RED_LED_PIN, Pin.OUT)
    green_led = Pin(GREEN_LED_PIN, Pin.OUT)
    blue_led = Pin(BLUE_LED_PIN, Pin.OUT)
    buzzer = PWM(Pin(BUZZER_PIN))

    # Initialize OLED Display
    i2c = I2C(0, sda=Pin(OLED_SDA_PIN), scl=Pin(OLED_SCL_PIN), freq=400000)
    oled = SSD1306_I2C(OLED_WIDTH, OLED_HEIGHT, i2c)

    set_servo_angle(servo, 0)
    print("Servo, motion sensor, keypad, RFID, LEDs, buzzer, and OLED initialized.")

    # --- RFID Tag Setup ---
    # Load authorized tags from file, or enter programming mode if none exist.
    authorized_tags = load_authorized_tags()
    if not authorized_tags:
        print("\n--- PROGRAMMING MODE ---")
        display_message(oled, "PROGRAM MODE", "Scan 2 tags", duration_s=0)
        print(f"No authorized tags found. Please scan {MAX_AUTHORIZED_TAGS} tags to register them.")
        blue_led.on() # Indicate programming mode
        while len(authorized_tags) < MAX_AUTHORIZED_TAGS:
            blue_led.toggle() # Blink the blue LED
            display_message(oled, f"Scan Tag #{len(authorized_tags) + 1}", "", duration_s=0)
            (stat, tag_type) = rfid_reader.request(rfid_reader.REQIDL)
            if stat == rfid_reader.OK:
                (stat, raw_uid) = rfid_reader.anticoll()
                if stat == rfid_reader.OK:
                    uid = "0x%02x%02x%02x%02x" % (raw_uid[0], raw_uid[1], raw_uid[2], raw_uid[3])
                    if uid not in authorized_tags:
                        authorized_tags.append(uid)
                        print(f"Tag #{len(authorized_tags)} registered: {uid}")
                        play_program_tone(buzzer)
                    else:
                        print("Tag already registered. Scan a different tag.")
                        play_error_tone(buzzer)
                    time.sleep(1)

        save_authorized_tags(authorized_tags)
        blue_led.off()
        play_success_tone(buzzer)
        print("--- PROGRAMMING MODE COMPLETE ---")

    print(f"Authorized tags loaded: {authorized_tags}")

    try:
        ip_address = connect_wifi(WIFI_SSID, WIFI_PASSWORD)

        # Setup socket and listen for connections
        addr = socket.getaddrinfo('0.0.0.0', 80)[0][-1]
        s = socket.socket()
        s.setblocking(False) # Use non-blocking socket
        s.bind(addr)
        s.listen(5)
        print('Listening on', addr)

        # --- Main Application Loop ---
        while True:
            if system_state == "LOCKED":
                # System is locked, wait for valid input
                red_led.on()
                green_led.off()
                access_code = generate_code()
                update_display(oled, "LOCKED", access_code)
                print("\n----------------------------------")
                print(f"Generated New Access Code: {access_code}")
                print(f"View on your phone at http://{ip_address}")

                user_input = get_keypad_or_rfid_input(keypad, rfid_reader, authorized_tags, system_state, s, access_code, ip_address, event_log)

                if user_input == "DURESS_UNLOCK":
                    log_event("Duress code entered!")
                    print("Duress code entered. Unlocking normally...")
                    trigger_duress_notification()
                    play_success_tone(buzzer) # Appear normal
                    set_servo_angle(servo, 90)
                    system_state = "UNLOCKED"
                    print("System state: UNLOCKED")
                    display_message(oled, "Access Granted", "UNLOCKED", duration_s=2)

                elif user_input == access_code or user_input == "RFID_BYPASS" or user_input == "REMOTE_UNLOCK":
                    if user_input == "RFID_BYPASS":
                        log_event("Unlocked with RFID")
                        print("RFID Bypass! Unlocking...")
                    elif user_input == "REMOTE_UNLOCK":
                        log_event("Unlocked via remote")
                        print("Remote Unlock! Unlocking...")
                    else:
                        log_event("Unlocked with code")
                        print("Code Correct! Unlocking...")
                    play_success_tone(buzzer)
                    set_servo_angle(servo, 90)
                    system_state = "UNLOCKED"
                    print("System state: UNLOCKED")
                    display_message(oled, "Access Granted", "UNLOCKED", duration_s=2)
                else:
                    log_event(f"Incorrect code: {user_input}")
                    print("Incorrect code. Please try again.")
                    # Beep for 1000ms on incorrect code
                    play_tone(buzzer, 440, 1.0)
                    display_message(oled, "Access Denied", "", duration_s=2)

            elif system_state == "UNLOCKED":
                # System is unlocked, wait for door to close
                red_led.off()
                green_led.on()
                update_display(oled, "UNLOCKED")
                print(f"Door unlocked. Ignoring motion for {MOTION_IGNORE_DELAY_S} seconds...")
                time.sleep(MOTION_IGNORE_DELAY_S)

                print("Ready to lock. Waiting for door to close (motion trigger)...")
                while motion_sensor.value() == 0:
                    time.sleep(0.1)

                print("Door closed. Locking now.")
                log_event("Door closed and locked")
                set_servo_angle(servo, 0)
                system_state = "LOCKED"
                print("System state: LOCKED")
                time.sleep(1) # Debounce/settle time

    except Exception as e:
        print(f"A critical error occurred: {e}")
        if oled:
            try:
                update_display(oled, "ERROR", str(e))
            except Exception:
                pass
