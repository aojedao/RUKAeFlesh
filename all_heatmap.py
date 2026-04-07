import serial
import matplotlib.pyplot as plt
import matplotlib.animation as animation
from matplotlib.colors import Normalize
from matplotlib.cm import ScalarMappable
import numpy as np
from collections import deque
import re
import datetime
import sys
from PIL import Image

# --- Configuration ---
SERIAL_PORT = '/dev/ttyACM0'    # CHANGE THIS to your Arduino's serial port
BAUD_RATE = 115200              # CHANGE THIS to your Arduino's baud rate
MAX_SAMPLES = 50                # Maximum number of data points to display on the graph
REFRESH_RATE_MS = 0.1           # Animation refresh rate in milliseconds
MAX_BOARDS = 5                 # Maximum number of boards/sensors
LOG_FILENAME = f"arduino_readings_{datetime.datetime.now():%Y%m%d_%H%M%S}.txt"

# Sensor locations on the image (x, y coordinates)
# You'll need to adjust these based on your actual sensor layout image
SENSOR_LOCATIONS = {
    0: (100, 100),
    1: (150, 100),
    2: (200, 100),
    3: (250, 100),
    4: (300, 100)
}

# Size of each sensor circle
SENSOR_RADIUS = 15

# Data structure to hold the history of readings for each signal
DATA_STREAMS = {}

def generate_stream_keys():
    keys = []
    for board in range(0, MAX_BOARDS):
        for sensor in range(0, 5):  # Max 5 sensors per board
            for axis in ['X', 'Y', 'Z']:
                keys.append(f"B{board}S{sensor}{axis}")
    return keys

# Initialize data structures
ALL_KEYS = generate_stream_keys()
SAMPLE_COUNTER = deque(maxlen=MAX_SAMPLES)
SAMPLE_COUNTER.append(0)
current_sample = 0

for key in ALL_KEYS:
    DATA_STREAMS[key] = deque(maxlen=MAX_SAMPLES)
    DATA_STREAMS[key].append(0.0)

# Regular expression to parse the input
PARSE_PATTERN = re.compile(r"Board(\d+)Sensor(\d+)([XYZ]):\s*([-+]?\d*\.?\d+)")

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
        if ser.in_waiting > 0:
            line = ser.readline().decode('utf-8').strip()
            
            if not line:
                return False
            
            matches = PARSE_PATTERN.findall(line)
            
            if matches:
                global current_sample
                data_updated = False
                processed_keys = set()
                current_values = {}
                
                for match in matches:
                    board_num = match[0]
                    sensor_num = match[1]
                    axis = match[2]
                    value_str = match[3]
                    
                    try:
                        value = float(value_str)
                    except ValueError:
                        print(f"Skipping invalid value: {value_str}")
                        continue
                    
                    key = f"B{board_num}S{sensor_num}{axis}"
                    
                    if key in processed_keys:
                        continue
                        
                    processed_keys.add(key)
                    
                    if key in DATA_STREAMS:
                        DATA_STREAMS[key].append(value)
                        current_values[key] = value
                        data_updated = True
                    else:
                        print(f"Unknown key: {key}")
                
                if data_updated:
                    timestamp = datetime.datetime.now().strftime("%H:%M:%S.%f")
                    row_values = [timestamp]
                    
                    for key in ALL_KEYS:
                        if key in current_values:
                            row_values.append(str(current_values[key]))
                        else:
                            row_values.append("")
                    
                    log_file.write(",".join(row_values) + "\n")
                    current_sample += 1
                    SAMPLE_COUNTER.append(current_sample)
                    log_file.flush()
                    return True

    except serial.SerialException as e:
        print(f"Serial error: {e}")
    except KeyboardInterrupt:
        print("\nStopping...")
        return None
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        
    return False

# --- Plotting Setup ---

fig, axes = plt.subplots(2, 3, figsize=(15, 10))
fig.suptitle('Arduino Sensor Readings - Heatmap Visualization', fontsize=16)
plt.subplots_adjust(hspace=0.3, wspace=0.3)

# Flatten axes for easier indexing
axes = axes.flatten()

# Create a heatmap for each axis (X, Y, Z) across all boards
# We'll show 3 main heatmaps for X, Y, Z values
heatmap_data = {
    'X': np.zeros((MAX_BOARDS, 1)),
    'Y': np.zeros((MAX_BOARDS, 1)),
    'Z': np.zeros((MAX_BOARDS, 1)),
}

im_handles = {}
cbar_handles = {}

# Create heatmaps for each axis
for idx, axis in enumerate(['X', 'Y', 'Z']):
    ax = axes[idx]
    ax.set_title(f'Sensor {axis}-Axis Heatmap', fontsize=12)
    
    # Create heatmap
    im = ax.imshow(
        heatmap_data[axis],
        cmap='RdYlBu_r',
        aspect='auto',
        animated=True,
        vmin=-500,
        vmax=500
    )
    ax.set_ylabel(f'Board/Sensor')
    ax.set_xlabel('Sensor Index')
    ax.set_xticks([0])
    ax.set_yticks(range(MAX_BOARDS))
    ax.set_yticklabels([f'S{i}' for i in range(MAX_BOARDS)])
    
    cbar = fig.colorbar(im, ax=ax, label='Value')
    im_handles[axis] = im
    cbar_handles[axis] = cbar

# Create overlay heatmaps with sensor location image
for idx, axis in enumerate(['X', 'Y', 'Z']):
    ax = axes[3 + idx]
    ax.set_title(f'Sensor {axis}-Axis with Location Overlay', fontsize=12)
    
    # You can load an image of your sensor layout here
    # For now, we'll just create a white background
    # To use your own image, uncomment and modify the line below:
    # image = Image.open('/path/to/your/sensor_layout_image.png')
    # ax.imshow(image)
    
    # Create white background
    ax.set_xlim(0, 400)
    ax.set_ylim(0, 400)
    ax.invert_yaxis()
    ax.set_aspect('equal')
    ax.set_xlabel('X Position')
    ax.set_ylabel('Y Position')
    
    # We'll update these circles with data in the animate function
    im_handles[f'{axis}_overlay'] = ax

# Store circle patches for updating
circle_patches = {}

# --- Animation Function ---

def animate(frame):
    """Function called by FuncAnimation to update the plots."""
    result = get_serial_data()
    if result is None:
        anim.event_source.stop()
        ser.close()
        log_file.close()
        print("\nSerial connection and logging closed.")
        plt.close(fig)
        return list(im_handles.values())
    
    if result:
        # Update heatmap data for each axis
        for axis in ['X', 'Y', 'Z']:
            axis_data = []
            
            # Collect latest value for each board/sensor combination
            for board in range(MAX_BOARDS):
                for sensor in range(5):  # Get data from sensor 0 only for simplicity
                    key = f"B{board}S{sensor}{axis}"
                    if key in DATA_STREAMS:
                        values = list(DATA_STREAMS[key])
                        if values:
                            axis_data.append(values[-1])  # Get latest value
                        else:
                            axis_data.append(0)
                
            # Reshape and update heatmap
            if axis_data:
                heatmap_data[axis] = np.array(axis_data[:MAX_BOARDS]).reshape(-1, 1)
                im_handles[axis].set_data(heatmap_data[axis])
                im_handles[axis].set_clim(vmin=np.min(heatmap_data[axis]), vmax=np.max(heatmap_data[axis]))
        
        # Update overlay heatmaps with sensor location circles
        for idx, axis in enumerate(['X', 'Y', 'Z']):
            ax = im_handles[f'{axis}_overlay']
            
            # Clear previous circles
            for child in ax.get_children():
                if hasattr(child, 'set_visible'):
                    if isinstance(child, plt.Circle):
                        child.remove()
            
            # Create new circles with data-based colors
            norm = Normalize(vmin=-500, vmax=500)
            cmap = plt.cm.RdYlBu_r
            
            for board in range(MAX_BOARDS):
                key = f"B{board}S0{axis}"
                if key in DATA_STREAMS:
                    values = list(DATA_STREAMS[key])
                    if values:
                        value = values[-1]
                        color = cmap(norm(value))
                        
                        # Get location from SENSOR_LOCATIONS
                        if board in SENSOR_LOCATIONS:
                            x, y = SENSOR_LOCATIONS[board]
                            circle = plt.Circle((x, y), SENSOR_RADIUS, color=color, ec='black', linewidth=1)
                            ax.add_patch(circle)
                            
                            # Add text label
                            ax.text(x, y, f'S{board}', ha='center', va='center', fontsize=8, color='white', weight='bold')
        
        fig.canvas.draw_idle()
    
    return list(im_handles.values())

# --- Main Execution ---

try:
    anim = animation.FuncAnimation(fig, animate, interval=REFRESH_RATE_MS, blit=False)
    plt.show()

except KeyboardInterrupt:
    print("\nProgram terminated by user.")
finally:
    if 'ser' in locals() and ser.is_open:
        ser.close()
    if 'log_file' in locals() and not log_file.closed:
        log_file.close()
