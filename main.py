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
from lib.keypad import Keypad

# --- Hardware Setup ---
# IMPORTANT: These are the GPIO pin numbers.
# Please ensure your hardware is connected to these pins.
SERVO_PIN = 15          # Pin for the servo motor's data line
MOTION_PIN = 28         # Pin for the PIR motion sensor's output
KEYPAD_ROWS = [0, 1, 2, 3] # Pins for the keypad rows
KEYPAD_COLS = [4, 5, 6]   # Pins for the keypad columns

# --- Lock Configuration ---
LOCK_DELAY_S = 10 # Seconds to wait after motion is detected before locking

# --- WiFi Configuration ---
# IMPORTANT: Replace these with your WiFi network credentials.
WIFI_SSID = "YOUR_WIFI_SSID"
WIFI_PASSWORD = "YOUR_WIFI_PASSWORD"

# --- Functions ---
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

def get_keypad_input(keypad_instance):
    """
    Waits for keypad input.
    Returns the entered code.
    """
    entered_code = ""
    print("Enter the 6-digit code...")

    while len(entered_code) < 6:
        # Handle web requests to display the code
        try:
            cl, addr = s.accept()
            print('Client connected from', addr)
            response = web_page(access_code, ip_address, system_state)
            cl.send('HTTP/1.0 200 OK\r\nContent-type: text/html\r\n\r\n')
            cl.send(response)
            cl.close()
        except OSError:
            pass # No client waiting

        # Check for keypad input
        key = keypad_instance.scan()
        if key:
            entered_code += key
            print(f"Entered: {entered_code}")
            time.sleep(0.3) # Debounce

    return entered_code

def web_page(code, ip, status):
    """Creates a simple HTML page to display the status and code."""
    html = f"""
    <html>
        <head>
            <title>Pico W Lock</title>
            <meta http-equiv="refresh" content="10">
        </head>
        <body>
            <h1>Pico W Lock System</h1>
            <p><strong>Status:</strong> {status}</p>
            <hr>
            <h2>Random Access Code</h2>
            <p>Enter this code on the keypad:</p>
            <h2 style="color: blue;">{code}</h2>
            <hr>
            <p>Connect to your Pico W at: http://{ip}</p>
        </body>
    </html>
    """
    return html

# --- Global variables for web server access ---
s = None
access_code = ""
ip_address = ""
system_state = "LOCKED"

# --- Main Loop ---
if __name__ == "__main__":
    print("Starting lock system...")

    # --- Initialize Hardware ---
    servo = PWM(Pin(SERVO_PIN))
    servo.freq(50)
    motion_sensor = Pin(MOTION_PIN, Pin.IN)
    keypad = Keypad(KEYPAD_ROWS, KEYPAD_COLS)

    set_servo_angle(servo, 0) # Start in locked position
    print("Servo, motion sensor, and keypad initialized.")

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
                # System is locked, generate a new code and wait for input
                access_code = generate_code()
                print("\n----------------------------------")
                print(f"Generated New Access Code: {access_code}")
                print(f"View on your phone at http://{ip_address}")

                user_input = get_keypad_input(keypad)

                if user_input == access_code:
                    print("Code Correct! Unlocking...")
                    set_servo_angle(servo, 90)
                    system_state = "UNLOCKED"
                    print("System state: UNLOCKED")
                else:
                    print("Incorrect code. A new code will be generated.")
                    time.sleep(2) # Brief pause

            elif system_state == "UNLOCKED":
                # System is unlocked, wait for the door to be closed
                print("System unlocked. Waiting for motion to signal door is closed...")

                # Wait for the first motion trigger
                while motion_sensor.value() == 0:
                    time.sleep(0.1)

                print(f"Motion detected. Waiting {LOCK_DELAY_S} seconds before locking.")
                time.sleep(LOCK_DELAY_S)

                print("Locking now.")
                set_servo_angle(servo, 0)
                system_state = "LOCKED"
                print("System state: LOCKED")
                time.sleep(1) # Debounce/settle time

    except Exception as e:
        print(f"A critical error occurred: {e}")
        # In a real application, you might want to try to reconnect or reset.
