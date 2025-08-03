# keypad.py
# A simple library for a 4x3 matrix keypad on Raspberry Pi Pico.

from machine import Pin
import time

class Keypad:
    # Define the keypad layout
    KEY_MAP = [
        ['1', '2', '3'],
        ['4', '5', '6'],
        ['7', '8', '9'],
        ['*', '0', '#']
    ]

    def __init__(self, row_pins, col_pins):
        """
        Initializes the keypad.
        :param row_pins: A list of GPIO pin numbers for the rows.
        :param col_pins: A list of GPIO pin numbers for the columns.
        """
        if len(row_pins) != 4 or len(col_pins) != 3:
            raise ValueError("Must specify 4 row pins and 3 column pins.")

        # Setup row pins as outputs
        self.rows = [Pin(p, Pin.OUT) for p in row_pins]

        # Setup column pins as inputs with pull-down resistors
        self.cols = [Pin(p, Pin.IN, Pin.PULL_DOWN) for p in col_pins]

        self.scan_delay = 0.05  # 50ms delay for debouncing

    def scan(self):
        """
        Scans the keypad for a single key press.
        :return: The character of the pressed key, or None if no key is pressed.
        """
        for i, row in enumerate(self.rows):
            # Drive the current row high
            row.value(1)

            for j, col in enumerate(self.cols):
                if col.value() == 1:
                    # A key has been pressed
                    time.sleep(self.scan_delay) # Debounce

                    # Wait for key release
                    while col.value() == 1:
                        pass

                    row.value(0) # Reset the row pin
                    return self.KEY_MAP[i][j]

            # Set the current row back to low
            row.value(0)

        return None
