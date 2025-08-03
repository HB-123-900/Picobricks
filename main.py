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
from machine import Pin, PWM
import random
import json
from lib.keypad import Keypad
from lib.mfrc522 import MFRC522

# --- Hardware Setup ---
# IMPORTANT: These are the GPIO pin numbers.
# Please ensure your hardware is connected to these pins.
SERVO_PIN = 15          # Pin for the servo motor's data line
MOTION_PIN = 28         # Pin for the PIR motion sensor's output
KEYPAD_ROWS = [0, 1, 2, 3] # Pins for the keypad rows
KEYPAD_COLS = [4, 5, 6]   # Pins for the keypad columns

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

# --- WiFi Configuration ---
# IMPORTANT: Replace these with your WiFi network credentials.
WIFI_SSID = "YOUR_WIFI_SSID"
WIFI_PASSWORD = "YOUR_WIFI_PASSWORD"

# --- Functions ---
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

def get_keypad_or_rfid_input(keypad_instance, rfid_reader_instance, authorized_tags_list):
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

        # 3. Handle web requests
        try:
            cl, addr = s.accept()
            print('Client connected from', addr)
            response = web_page(access_code, ip_address)
            cl.send('HTTP/1.0 200 OK\r\nContent-type: text/html\r\n\r\n')
            cl.send(response)
            cl.close()
        except OSError:
            pass

    return entered_code

def web_page(code, ip):
    """Creates a simple HTML page to display the code."""
    html = f"""
    <html>
        <head>
            <title>Pico W Security</title>
            <meta http-equiv="refresh" content="30">
        </head>
        <body>
            <h1>Random Access Code</h1>
            <p>Enter this code on the keypad:</p>
            <h2>{code}</h2>
            <p>Connect to your Pico W at: {ip}</p>
        </body>
    </html>
    """
    return html

# --- Global variables for web server access ---
s = None
access_code = ""
ip_address = ""

# --- Main Loop ---
if __name__ == "__main__":
    print("Starting security system...")

    # --- Initialize Hardware ---
    servo = PWM(Pin(SERVO_PIN))
    servo.freq(50)
    motion_sensor = Pin(MOTION_PIN, Pin.IN)
    keypad = Keypad(KEYPAD_ROWS, KEYPAD_COLS)
    spi = SPI(1, baudrate=2500000, polarity=0, phase=0, sck=Pin(RFID_SCK), mosi=Pin(RFID_MOSI), miso=Pin(RFID_MISO))
    rfid_reader = MFRC522(spi=spi, gpioRst=RFID_RST, gpioCs=RFID_SDA)

    set_servo_angle(servo, 0)
    print("Servo, motion sensor, keypad, and RFID reader initialized.")

    # --- RFID Tag Setup ---
    # Load authorized tags from file, or enter programming mode if none exist.
    authorized_tags = load_authorized_tags()
    if not authorized_tags:
        print("\n--- PROGRAMMING MODE ---")
        print(f"No authorized tags found. Please scan {MAX_AUTHORIZED_TAGS} tags to register them.")
        while len(authorized_tags) < MAX_AUTHORIZED_TAGS:
            (stat, tag_type) = rfid_reader.request(rfid_reader.REQIDL)
            if stat == rfid_reader.OK:
                (stat, raw_uid) = rfid_reader.anticoll()
                if stat == rfid_reader.OK:
                    uid = "0x%02x%02x%02x%02x" % (raw_uid[0], raw_uid[1], raw_uid[2], raw_uid[3])
                    if uid not in authorized_tags:
                        authorized_tags.append(uid)
                        print(f"Tag #{len(authorized_tags)} registered: {uid}")
                    else:
                        print("Tag already registered. Scan a different tag.")
                    time.sleep(1) # Wait for tag to be removed

        save_authorized_tags(authorized_tags)
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
            # 1. Generate and display a new code
            access_code = generate_code()
            print("\n----------------------------------")
            print(f"Generated New Access Code: {access_code}")
            print(f"View on your phone at http://{ip_address}")

            # 2. Get user input from keypad or RFID
            user_input = get_keypad_or_rfid_input(keypad, rfid_reader, authorized_tags)

            # 3. Check if the code is correct or RFID was used
            if user_input == access_code or user_input == "RFID_BYPASS":
                if user_input == "RFID_BYPASS":
                    print("RFID Bypass! Activating servo.")
                else:
                    print("Code Correct! Activating servo.")
                set_servo_angle(servo, 90)

                # 4. Wait for motion detector
                print("Waiting for motion...")
                while motion_sensor.value() == 0:
                    time.sleep(0.1)

                print("Motion detected!")

                # 5. Wait 10 seconds and reset servo
                print("Waiting 10 seconds...")
                time.sleep(10)

                print("Resetting servo.")
                set_servo_angle(servo, 0)

            else:
                print("Incorrect code. Generating a new one.")

            time.sleep(1) # a small delay before new code generation

    except Exception as e:
        print(f"A critical error occurred: {e}")
        # Consider a more robust error handling, like a reset.
