/*
  Qwiic Mux Shield - PCA9548A/TCA9548A Multi-Sensor Control V2
  By: Gemini (code revision)
  Original code by: Nathan Seidle
  SparkFun Electronics

  This improved version includes:
  - Sensor board classification structure
  - Fixed reading to output all sensors simultaneously
  - Better organization for different board types (5X, 1xC, 1xF)

  Hardware Connections:
  - Attach the Qwiic Mux Shield to your microcontroller.
  - Connect sensor boards to appropriate ports.
  - Open the Serial Monitor at 115200 baud to see the raw output.
  - Open the Serial Plotter to see the data visualization.
*/

#include <Wire.h>
#include <MLX90393.h> 

#define TCAADDR 0x70 // The I2C address of the TCA9548A multiplexer

// Sensor board classification structure
struct SensorBoard {
  uint8_t boardType;      // 5 for 5X boards, 1 for 1X boards
  uint8_t numSensors;     // Number of sensors on this board
  uint8_t addresses[5];   // I2C addresses for sensors (max 5 for 5X boards, 1 for 1X boards)
  char classification[4]; // "5X", "1XC", "1XF", etc.
};

// Constants for your hardware setup
#define NUMBER_OF_BOARDS 8

// Board configuration - modify this array to match your actual setup
// Format: [5x, 5x, 5x, 1xC, 1xF] as mentioned in requirements
SensorBoard boardConfig[NUMBER_OF_BOARDS] = {
  // First three boards are 5X type (5 sensors each)
  {5, 5, {0x0C, 0x13, 0x12, 0x10, 0x11}, "5X"},  // Board 0 - Palm 1
  {5, 5, {0x0C, 0x13, 0x12, 0x10, 0x11}, "5X"},  // Board 1 - Palm 2
  {5, 5, {0x0C, 0x13, 0x12, 0x10, 0x11}, "5X"},  // Board 2 - Palm 3
  
  // Single sensor boards with ONE specific address each
  {1, 1, {0x0C}, "1XC"}, // Board 3 - 1xC type (only address 0x0C)
  {1, 1, {0x0F}, "1XF"}, // Board 4 - 1xF type (only address 0x0F)
  
  // Continue pattern for remaining boards (modify as needed)
  {1, 1, {0x0C}, "1XC"},  // Board 5
  {1, 1, {0x0F}, "1XF"},  // Board 6
  {1, 1, {0x0F}, "1XF"}   // Board 7
};

// Create a 2D array for the MLX90393 sensor objects and their data
MLX90393 mlx[NUMBER_OF_BOARDS][5]; // Max 5 sensors per board
MLX90393::txyz data[NUMBER_OF_BOARDS][5];

// A 2D array to track which sensors have been successfully initialized
bool sensorIsInitialized[NUMBER_OF_BOARDS][5];

// Structure to hold all sensor readings for simultaneous output
struct AllSensorReadings {
  MLX90393::txyz readings[NUMBER_OF_BOARDS][5];
  bool isValid[NUMBER_OF_BOARDS][5];
} allReadings;

// Function to select a specific channel on the TCA9548A multiplexer
void tcaSelect(uint8_t i) {
  if (i > 7) return; // The TCA9548A has 8 channels (0-7)

  Wire1.beginTransmission(TCAADDR);
  Wire1.write(1 << i);
  Wire1.endTransmission();
}

void setup() {
  Serial.begin(115200);
  Serial.println("Qwiic Mux Shield Multi-Sensor V2 - All Boards Simultaneous Reading");
  Wire1.begin(); // Start the I2C bus used by the mux
  Wire1.setClock(400000); // Set the I2C clock speed
  delay(10);

  // Print board configuration
  Serial.println("Board Configuration:");
  for (byte board = 0; board < NUMBER_OF_BOARDS; board++) {
    Serial.print("Board ");
    Serial.print(board);
    Serial.print(": Type ");
    Serial.print(boardConfig[board].classification);
    Serial.print(", Sensors: ");
    Serial.print(boardConfig[board].numSensors);
    Serial.print(", Addresses: ");
    for (byte i = 0; i < boardConfig[board].numSensors; i++) {
      Serial.print("0x");
      Serial.print(boardConfig[board].addresses[i], HEX);
      if (i < boardConfig[board].numSensors - 1) Serial.print(", ");
    }
    Serial.println();
  }
  Serial.println("------------------------------------");

  // Initialize the sensors on all boards
  for (byte board = 0; board < NUMBER_OF_BOARDS; board++) {
    tcaSelect(board); // Enable the multiplexer channel for this board
    delay(20); // Reduced delay for faster initialization
  
    Serial.print("--- Initializing Board ");
    Serial.print(board);
    Serial.print(" (");
    Serial.print(boardConfig[board].classification);
    Serial.print(") - ");
    Serial.print(boardConfig[board].numSensors);
    Serial.println(" sensor(s) ---");
  
    // Initialize only the actual number of sensors for this board type
    for (byte sensor = 0; sensor < boardConfig[board].numSensors; sensor++) {
      Serial.print("  Sensor ");
      Serial.print(sensor);
      Serial.print(" @ 0x");
      Serial.print(boardConfig[board].addresses[sensor], HEX);
      Serial.print(": ");

      byte status = mlx[board][sensor].begin(boardConfig[board].addresses[sensor], -1, Wire1);
    
      if (status == 0) {
        Serial.println("OK");
        mlx[board][sensor].startBurst(0xF); // Start burst mode for fast reading
        sensorIsInitialized[board][sensor] = true;
      } else {
        Serial.print("FAILED (");
        Serial.print(status);
        Serial.println(")");
        sensorIsInitialized[board][sensor] = false;
      }
      delay(5); // Minimal delay between sensor initializations
    }
    
    // Initialize unused sensor slots as false (important for 1X boards)
    for (byte sensor = boardConfig[board].numSensors; sensor < 5; sensor++) {
      sensorIsInitialized[board][sensor] = false;
    }
  }
  Serial.println("All sensors initialized. Mux Shield online.");
  
  // Initialize ALL sensor readings to zero to prevent garbage values
  for (byte board = 0; board < NUMBER_OF_BOARDS; board++) {
    for (byte sensor = 0; sensor < 5; sensor++) {
      allReadings.readings[board][sensor].x = 0;
      allReadings.readings[board][sensor].y = 0;
      allReadings.readings[board][sensor].z = 0;
      allReadings.isValid[board][sensor] = false;
    }
  }
  Serial.println("All sensor readings initialized to zero.");
  
  // Print header for data output
  Serial.println("\nData Format: Board#_Sensor#_X, Board#_Sensor#_Y, Board#_Sensor#_Z");
  Serial.println("Starting continuous readings...\n");
}

void loop() {
  // STEP 1: Collect ALL sensor readings VERY FAST
  for (byte board = 0; board < NUMBER_OF_BOARDS; board++) {
    tcaSelect(board); // Tell mux to connect to this board's port
    delayMicroseconds(100); // Ultra-fast switching - microseconds instead of milliseconds
    
    // Read only the actual sensors for this board type (1 for 1X, 5 for 5X)
    for (byte sensor = 0; sensor < boardConfig[board].numSensors; sensor++) {
      if (sensorIsInitialized[board][sensor]) {
        // Only read if sensor was successfully initialized
        mlx[board][sensor].readBurstData(allReadings.readings[board][sensor]);
        allReadings.isValid[board][sensor] = true;
      } else {
        // Clear readings and mark as invalid for failed/disconnected sensors
        allReadings.readings[board][sensor].x = 0;
        allReadings.readings[board][sensor].y = 0;
        allReadings.readings[board][sensor].z = 0;
        allReadings.isValid[board][sensor] = false;
      }
    }
    
    // ALWAYS clear unused sensor slots for this board type
    for (byte sensor = boardConfig[board].numSensors; sensor < 5; sensor++) {
      allReadings.readings[board][sensor].x = 0;
      allReadings.readings[board][sensor].y = 0;
      allReadings.readings[board][sensor].z = 0;
      allReadings.isValid[board][sensor] = false;
    }
    

  }
  
  // STEP 2: Output ALL boards and sensors (connected or not) for consistent format
  // This ensures disconnected/failed boards show 0 values instead of being skipped
  bool firstValue = true;
  
  for (byte board = 0; board < NUMBER_OF_BOARDS; board++) {
    for (byte sensor = 0; sensor < boardConfig[board].numSensors; sensor++) {
      // Add tab separator except for the first value
      if (!firstValue) Serial.print("\t");
      firstValue = false;
      
      // Output X, Y, Z values for this sensor (0 if not connected/failed)
      Serial.print("Board");
      Serial.print(board);
      Serial.print("Sensor");
      Serial.print(sensor);
      Serial.print("X:");
      // Always print the reading (will be 0 if sensor failed/disconnected due to clearing above)
      Serial.print(allReadings.readings[board][sensor].x);
      Serial.print("\t");
      
      Serial.print("Board");
      Serial.print(board);
      Serial.print("Sensor");
      Serial.print(sensor);
      Serial.print("Y:");
      // Always print the reading (will be 0 if sensor failed/disconnected due to clearing above)
      Serial.print(allReadings.readings[board][sensor].y);
      Serial.print("\t");
      
      Serial.print("Board");
      Serial.print(board);
      Serial.print("Sensor");
      Serial.print(sensor);
      Serial.print("Z:");
      // Always print the reading (will be 0 if sensor failed/disconnected due to clearing above)
      Serial.print(allReadings.readings[board][sensor].z);
    }
  }
  
  Serial.println(); // Print a newline at the end of each complete reading cycle
  // No delay - maximum speed reading!
}

// Helper function to print board configuration (can be called from Serial commands)
void printBoardConfig() {
  Serial.println("Current Board Configuration:");
  for (byte board = 0; board < NUMBER_OF_BOARDS; board++) {
    Serial.print("Board ");
    Serial.print(board);
    Serial.print(": ");
    Serial.print(boardConfig[board].classification);
    Serial.print(" (");
    Serial.print(boardConfig[board].numSensors);
    Serial.print(" sensors)");
    Serial.println();
  }
}
