// ============================================================
// board_config.h — ESP32-S3 Dev Module with OV3660 Camera
// ============================================================

#pragma once

// ----- Camera Model Selection -----
#define CAMERA_MODEL_ESP32S3_EYE  // Change if using a different board

// ----- Pin Definitions for ESP32-S3 Dev Module + OV3660 -----
// These match the standard ESP32-S3-EYE / Freenove ESP32-S3 CAM pinout.
// Adjust if your wiring differs.

#define PWDN_GPIO_NUM    -1   // Power down: not used on S3
#define RESET_GPIO_NUM   -1   // Reset: not used on S3

#define XCLK_GPIO_NUM    15
#define SIOD_GPIO_NUM    4    // SDA (SCCB data)
#define SIOC_GPIO_NUM    5    // SCL (SCCB clock)

#define Y9_GPIO_NUM      16
#define Y8_GPIO_NUM      17
#define Y7_GPIO_NUM      18
#define Y6_GPIO_NUM      12
#define Y5_GPIO_NUM      10
#define Y4_GPIO_NUM      8
#define Y3_GPIO_NUM      9
#define Y2_GPIO_NUM      11

#define VSYNC_GPIO_NUM   6
#define HREF_GPIO_NUM    7
#define PCLK_GPIO_NUM    13

// ----- Optional: LED Flash -----
// Uncomment and set the correct GPIO if your board has a flash LED
// #define LED_GPIO_NUM   48

// ============================================================
// NOTE: If you are using a different ESP32-S3 camera board
// (e.g., Freenove, AI-Thinker S3, XIAO ESP32S3 Sense),
// the pin numbers may be different. Check your board's schematic.
// ============================================================
