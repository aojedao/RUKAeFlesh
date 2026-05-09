import serial
import matplotlib.pyplot as plt
import matplotlib.animation as animation
from collections import deque
import re
import datetime
import sys
import argparse

# --- Configuration ---
DEFAULT_SERIAL_PORT = '/dev/ttyACM0'    # CHANGE THIS to your Arduino's serial port (e.g., 'COM3' or '/dev/ttyACM0')
DEFAULT_BAUD_RATE = 115200      # CHANGE THIS to your Arduino's baud rate
MAX_SAMPLES = 50       # Maximum number of data points to display on the graph
REFRESH_RATE_MS = 10     # Animation refresh rate in milliseconds
MAX_BOARDS = 8         # Maximum number of boards to support (determines subplot layout)
LOG_FILENAME = f"arduino_readings_{datetime.datetime.now():%Y%m%d_%H%M%S}.txt"
REDRAW_EVERY_N_UPDATES = 1
LOG_FLUSH_EVERY_N_UPDATES = 10
DEBUG_UNMATCHED_LINES = False
MAX_LINES_PER_CYCLE = 5

# Data structure to hold the history of readings for each signal
# Key format: "BoardXSensorYAxis" e.g., "B1S0X"
DATA_STREAMS = {}

parser = argparse.ArgumentParser(add_help=False)
parser.add_argument('--serial-port', default=DEFAULT_SERIAL_PORT)
parser.add_argument('--baud-rate', type=int, default=DEFAULT_BAUD_RATE)
parser.add_argument('--serial-test', action='store_true')
parser.add_argument('--serial-test-seconds', type=int, default=5)
args, _ = parser.parse_known_args()

SERIAL_PORT = args.serial_port
BAUD_RATE = args.baud_rate

# Define all unique data streams based on your description
# Boards 1-3 (5 sensors each): BxSyAxis (x=1..3, y=0..4, Axis=X,Y,Z) -> 3 * 5 * 3 = 45 streams
# Boards 4-9 (1 sensor each): BxS0Axis (x=4..9, y=0, Axis=X,Y,Z) -> 6 * 1 * 3 = 18 streams
# TOTAL: 63 unique data streams.

# Function to generate the stream keys
def generate_stream_keys():
    keys = []
    # Generate keys for all possible board/sensor combinations
    for board in range(0, MAX_BOARDS):
        # Board types: 5X boards have sensors 0-4, 1X boards have sensor 0
        # For simplicity, generate keys for all possible sensors (0-4) for each board
        if (board <= 2):
            for sensor in range(0, 5):  # Max 5 sensors per board
                for axis in ['X', 'Y', 'Z']:
                    keys.append(f"B{board}S{sensor}{axis}")
        else:
            sensor=0
            for axis in ['X', 'Y', 'Z']:
                keys.append(f"B{board}S{sensor}{axis}")
    return keys

# Initialize data structures (Sample number is the common x-axis for all)
ALL_KEYS = generate_stream_keys()
SAMPLE_COUNTER = deque(maxlen=MAX_SAMPLES)

# Initialize with sample 0
SAMPLE_COUNTER.append(0)
current_sample = 0
update_count = 0

for key in ALL_KEYS:
    DATA_STREAMS[key] = deque(maxlen=MAX_SAMPLES)
    # Initialize with 0 to prevent Matplotlib errors on first draw
    DATA_STREAMS[key].append(0.0) 

# Regular expression to parse either:
# 1) Board0Sensor0X:-7.20
# 2) Board0SensorX:-7.20
# Group 1: Board Number
# Group 2: Optional Sensor Number (defaults to 0 when omitted)
# Group 3: Axis (X/Y/Z)
# Group 4: Value
PARSE_PATTERN = re.compile(r"Board(\d+)Sensor(?:(\d+))?([XYZ]):\s*([-+]?\d*\.?\d+)")


def run_serial_test(seconds=5):
    """Print raw serial lines and regex match count, then exit."""
    print(f"[serial-test] Listening on {SERIAL_PORT} @ {BAUD_RATE} for {seconds}s...")
    deadline = datetime.datetime.now() + datetime.timedelta(seconds=seconds)
    count = 0
    while datetime.datetime.now() < deadline:
        raw = ser.readline().decode('utf-8', errors='ignore').strip()
        if not raw:
            continue
        count += 1
        matches = PARSE_PATTERN.findall(raw)
        print(f"[{count:03d}] matches={len(matches)} | {raw[:140]}")
        if count >= 40:
            break
    print(f"[serial-test] Done. Non-empty lines={count}")

# --- Serial and Logging Setup ---

try:
    ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=0.1)
    ser.flushInput()
    print(f"Successfully connected to {SERIAL_PORT} at {BAUD_RATE} baud.")
except serial.SerialException as e:
    print(f"Error opening serial port {SERIAL_PORT}: {e}")
    sys.exit(1)

# Open log file for appending, write header
try:
    log_file = open(LOG_FILENAME, 'a')
    # Write a header for the log file
    log_file.write("Timestamp," + ",".join(ALL_KEYS) + "\n")
    print(f"Logging data to {LOG_FILENAME}")
except IOError as e:
    print(f"Error opening log file: {e}")
    ser.close()
    sys.exit(1)

# --- Data Acquisition and Parsing Function ---

def get_serial_data():
    """Reads one line from serial, parses it, updates data structure, and logs."""
    try:
        global current_sample, update_count
        any_data_updated = False
        lines_processed = 0

        # Drain a few buffered lines per animation cycle to keep view live.
        while ser.in_waiting > 0 and lines_processed < MAX_LINES_PER_CYCLE:
            lines_processed += 1

            line = ser.readline().decode('utf-8', errors='ignore').strip()
            if not line:
                continue

            if "Board" not in line or "Sensor" not in line:
                continue

            matches = PARSE_PATTERN.findall(line)
            if not matches:
                if DEBUG_UNMATCHED_LINES and not line.startswith("---") and not line.startswith("Board Configuration"):
                    print(f"No matches found in line: {line[:80]}...")
                continue

            data_updated = False
            processed_keys = set()
            current_values = {}

            for match in matches:
                board_num = match[0]
                sensor_num = match[1] if match[1] else "0"
                axis = match[2]
                value_str = match[3]

                try:
                    value = float(value_str)
                except ValueError:
                    continue

                key = f"B{board_num}S{sensor_num}{axis}"
                if key in processed_keys:
                    continue
                processed_keys.add(key)

                if key in DATA_STREAMS:
                    DATA_STREAMS[key].append(value)
                    current_values[key] = value
                    data_updated = True

            if data_updated:
                timestamp = datetime.datetime.now().strftime("%H:%M:%S.%f")
                row_values = [timestamp]
                for key in ALL_KEYS:
                    row_values.append(str(current_values[key]) if key in current_values else "")
                log_file.write(",".join(row_values) + "\n")

                current_sample += 1
                update_count += 1
                SAMPLE_COUNTER.append(current_sample)
                any_data_updated = True

        if any_data_updated and update_count % LOG_FLUSH_EVERY_N_UPDATES == 0:
            log_file.flush()

        return any_data_updated

    except serial.SerialException as e:
        print(f"Serial error: {e}")
    except KeyboardInterrupt:
        print("\nStopping...")
        return None # Indicate to stop animation
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        
    return False

# --- Plotting Setup ---

# Calculate optimal subplot layout based on number of boards
import math
active_boards = MAX_BOARDS  # Each subplot represents one board (B0, B1, B2, etc.)
cols = int(math.ceil(math.sqrt(active_boards)))
rows = int(math.ceil(active_boards / cols))

# Create dynamic subplot configuration
fig, axes = plt.subplots(nrows=rows, ncols=cols, figsize=(4*cols, 3*rows))
fig.suptitle('Arduino Sensor Readings Live Plot', fontsize=16)

# Adjust spacing to make room for a single global legend
plt.subplots_adjust(hspace=0.55, wspace=0.35, bottom=0.18)

# Flatten the array of axes for easier indexing (handle single plot case)
if active_boards == 1:
    axes = [axes]
elif rows == 1 or cols == 1:
    axes = axes.flatten() if hasattr(axes, 'flatten') else axes
else:
    axes = axes.flatten()

# Prepare lines for each graph
lines = {}
legend_handles = []
legend_labels = []
plot_index = 0
axis_colors = {'X': 'tab:red', 'Y': 'tab:green', 'Z': 'tab:blue'}
sensor_styles = ['-', '--', ':', '-.', (0, (3, 1, 1, 1))]

# Organize plots by Board number (each plot shows one board: B0, B1, B2, etc.)
# First row = Board 0, second row = Board 1, etc.
# Each plot shows X, Y, Z for all sensors on that board
for board_num in range(0, active_boards):
    if plot_index < len(axes):
        ax = axes[plot_index]
        ax.set_title(f'Board {board_num}', fontsize=10)
        ax.tick_params(axis='x', rotation=45)
        ax.grid(True)
        
        # List of keys for this board (all sensors on this board)
        board_keys = []
        
        # For each sensor on this board
        for sensor_num in range(0, 5):  # Max 5 sensors per board
            for axis in ['X', 'Y', 'Z']:
                key = f"B{board_num}S{sensor_num}{axis}"
                if key in DATA_STREAMS:  # Only add if key exists in data streams
                    board_keys.append(key)
        
        # Plot the initial line for each sensor-axis combination on this board
        for key in board_keys:
            # Initial plot: line, = ax.plot(X_data, Y_data, label)
            # Ensure both sample counter and data have the same length
            sample_list = list(SAMPLE_COUNTER)
            data_list = list(DATA_STREAMS.get(key, []))
            min_len = min(len(sample_list), len(data_list))
            
            # Compact label (subplot already tells the board)
            sensor_axis = key.split('B', 1)[1].split('S', 1)[1]
            sensor_num = int(sensor_axis[:-1])
            axis = sensor_axis[-1]
            axis_label = f"S{sensor_num}{axis}"
            
            if min_len > 0:
                line, = ax.plot(
                    sample_list[-min_len:],
                    data_list[-min_len:],
                    label=axis_label,
                    color=axis_colors.get(axis, 'black'),
                    linestyle=sensor_styles[sensor_num % len(sensor_styles)],
                    linewidth=1.2,
                )
            else:
                line, = ax.plot(
                    [],
                    [],
                    label=axis_label,
                    color=axis_colors.get(axis, 'black'),
                    linestyle=sensor_styles[sensor_num % len(sensor_styles)],
                    linewidth=1.2,
                )
            lines[key] = line

            # Build a single figure-level legend from the first board only
            if board_num == 0:
                legend_handles.append(line)
                legend_labels.append(axis_label)
            
        plot_index += 1

# Hide any unused subplots
for i in range(plot_index, len(axes)):
    axes[i].set_visible(False)

if legend_handles:
    fig.legend(
        legend_handles,
        legend_labels,
        loc='lower center',
        ncol=5,
        fontsize='small',
        frameon=False,
        title='Signal legend (all boards)'
    )


# --- Animation Function ---

def animate(i):
    """Function called by FuncAnimation to update the plot."""
    result = get_serial_data()
    if result is None:
        # Stop the animation if get_serial_data returns None (e.g., on KeyboardInterrupt)
        anim.event_source.stop()
        ser.close()
        log_file.close()
        print("\nSerial connection and logging closed.")
        plt.close(fig)
        return []
    
    # If new data was processed, update all plots
    if result:
        global update_count
        sample_numbers = list(SAMPLE_COUNTER)
        
        # Update each line object
        for key, line in lines.items():
            data_values = list(DATA_STREAMS.get(key, [0.0]))
            # Ensure sample numbers and data arrays are the same length
            min_len = min(len(sample_numbers), len(data_values))
            if min_len > 0:
                line.set_data(sample_numbers[-min_len:], data_values[-min_len:])

        # Rescale less frequently to improve responsiveness
        if update_count % REDRAW_EVERY_N_UPDATES == 0:
            for i, ax in enumerate(axes):
                if i < active_boards and sample_numbers:
                    ax.relim()
                    ax.autoscale_view()
        
        # Force redraw
        fig.canvas.draw_idle()
    
    return list(lines.values()) # Return all updated artists

# --- Main Execution ---

try:
    if args.serial_test:
        run_serial_test(args.serial_test_seconds)
        ser.close()
        log_file.close()
        sys.exit(0)

    # Start the animation loop
    # Use configurable refresh rate
    anim = animation.FuncAnimation(
        fig,
        animate,
        interval=REFRESH_RATE_MS,
        blit=False,
        cache_frame_data=False,
    )
    plt.show()

except KeyboardInterrupt:
    print("\nProgram terminated by user.")
finally:
    # Ensure serial and log file are closed if the program exits unexpectedly
    if 'ser' in locals() and ser.is_open:
        ser.close()
    if 'log_file' in locals() and not log_file.closed:
        log_file.close()