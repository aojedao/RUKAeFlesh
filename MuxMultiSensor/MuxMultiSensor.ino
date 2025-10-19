/*
  Qwiic Mux Shield - PCA9548A/TCA9548A Basic Control
  By: Gemini (code revision)
  Original code by: Nathan Seidle
  SparkFun Electronics

  This code is a simplified version designed to read from a single sensor
  board connected to Mux channel 0. It serves as a baseline to ensure
  I2C communication is working correctly.

  Hardware Connections:
  - Attach the Qwiic Mux Shield to your microcontroller.
  - Plug a single sensor board into port 0.
  - Open the Serial Monitor at 115200 baud to see the raw output.
  - Open the Serial Plotter to see the data visualization.
*/

#include <Wire.h>
#include <MLX90393.h> 

#define TCAADDR 0x70 // The I2C address of the TCA9548A multiplexer

// Constants for your new hardware setup
#define NUMBER_OF_BOARDS 20
#define NUMBER_OF_SENSORS_PER_BOARD 5

// The I2C addresses for the 5 sensors on each board
// NOTE: These are the addresses from your original code.
// Please update them if your addresses are different.
uint8_t sensorAddresses[NUMBER_OF_SENSORS_PER_BOARD] = {0x0C, 0x13, 0x12, 0x10, 0x11};

// Create a 2D array for the MLX90393 sensor objects and their data
MLX90393 mlx[NUMBER_OF_BOARDS][NUMBER_OF_SENSORS_PER_BOARD];
MLX90393::txyz data[NUMBER_OF_BOARDS][NUMBER_OF_SENSORS_PER_BOARD];

// A 2D array to track which sensors have been successfully initialized
bool sensorIsInitialized[NUMBER_OF_BOARDS][NUMBER_OF_SENSORS_PER_BOARD];

// Y-axis offsets for visualization on the Arduino Plotter
int yOffsets[NUMBER_OF_BOARDS] = {0};

// Function to select a specific channel on the TCA9548A multiplexer
void tcaSelect(uint8_t i) {
  if (i > 7) return; // The TCA9548A has 8 channels (0-7)

  Wire1.beginTransmission(TCAADDR);
  Wire1.write(1 << i);
  Wire1.endTransmission();
}

void setup() {
  Serial.begin(115200);
  Serial.println("Qwiic Mux Shield Read Example - Single Board Version");
  Wire1.begin(); // Start the I2C bus used by the mux
  Wire1.setClock(400000); // Set the I2C clock speed
  delay(10);

  // Initialize the sensors on all boards
  for (byte board = 0; board < NUMBER_OF_BOARDS; board++) {
    tcaSelect(board); // Enable the multiplexer channel for this board
    delay(50); // Add a longer delay to ensure the bus is stable
  
    Serial.print("--- Initializing sensors on Board ");
    Serial.print(board);
    Serial.println(" ---");
  
    for (byte sensor = 0; sensor < NUMBER_OF_SENSORS_PER_BOARD; sensor++) {
      Serial.print("Attempting to initialize Sensor ");
      Serial.print(sensor);
      Serial.print(" at address 0x");
      Serial.println(sensorAddresses[sensor], HEX);

      byte status = mlx[board][sensor].begin(sensorAddresses[sensor], -1, Wire1);
    
      if (status == 0) {
        Serial.println("Initialization successful!");
        mlx[board][sensor].startBurst(0xF); // Start burst mode
        sensorIsInitialized[board][sensor] = true;
      } else {
        Serial.print("Initialization FAILED! Status: ");
        Serial.println(status);
        sensorIsInitialized[board][sensor] = false;
      }
      delay(10); // Short delay between sensor initializations
    }
    Serial.println("------------------------------------");
  }
  Serial.println("All sensors initialized. Mux Shield online.");
}

void loop() {
  for (byte board = 0; board < NUMBER_OF_BOARDS; board++) {
    tcaSelect(board); // Tell mux to connect to this board's port
    delay(10); // Ensure the bus connection is stable
    //Serial.print("BOARD NUMBER IS: ");
    //Serial.println(board);

    for (byte sensor = 0; sensor < NUMBER_OF_SENSORS_PER_BOARD; sensor++) {
      // Only attempt to read if the sensor was initialized successfully
      if (sensorIsInitialized[board][sensor]) {
        mlx[board][sensor].readBurstData(data[board][sensor]);

        // Apply the Y-axis offset based on both board and sensor
        //int yValOffset = data[board][sensor].y + (board * 8000); // 1000 is an example offset per board
        
        // Print the X, Y(offset), and Z data, separated by tabs, for the Arduino Plotter
        Serial.print("Board" + String(board) + "SensorX:");
        Serial.print(data[board][sensor].x);
        Serial.print("\t");
        Serial.print("Board" + String(board) + "SensorY:");
        //Serial.print(yValOffset);
        Serial.print(data[board][sensor].y);
        Serial.print("\t");
        Serial.print("Board" + String(board) + "SensorZ:");
        Serial.print(data[board][sensor].z);
        Serial.print("\t");
      } else {
        // If the sensor failed to initialize, print a placeholder to maintain plotter alignment
        Serial.print(0);
        Serial.print("\t");
        Serial.print(yOffsets[board]);
        Serial.print("\t");
        Serial.print(0);
        Serial.print("\t");
      }
    }
  }
  Serial.println(); // Print a newline at the end of each full reading cycle
  delayMicroseconds(500); // Wait a short period before the next reading cycle
}
