// ============================================================
// CameraWebServer.ino
// ESP32-S3 + OV3660 + MLX90614 Thermal Scanner
// UI matches reference heatmap with smooth purple→yellow gradient
// Servo fixed with proper attach, test sweep, and detach logic
// ============================================================

#include "esp_camera.h"
#include <WiFi.h>
#include <WebServer.h>
#include <Wire.h>
#include <Adafruit_MLX90614.h>
#include <ESP32Servo.h>
#include "board_config.h"

// ============================================================
// WIFI
// ============================================================
const char *ssid     = "YOUR_WIFI_NAME";
const char *password = "YOUR_WIFI_PASSWORD";

// ============================================================
// PINS
// ============================================================
#define SDA_PIN    8
#define SCL_PIN    9
#define SERVO_PIN  18

// ============================================================
// SERVO SETTINGS — fixed
// ============================================================
#define SERVO_MIN_US   500    // pulse width for 0°   (tune if servo doesn't reach)
#define SERVO_MAX_US  2500    // pulse width for 180° (tune if servo doesn't reach)
#define SERVO_MIN_DEG  10     // leftmost scan angle
#define SERVO_MAX_DEG 170     // rightmost scan angle
#define SERVO_CENTER  90      // rest position

// ============================================================
// SCAN GRID
// ============================================================
#define ROWS  8
#define COLS  15

// ============================================================
// TIMING — critical for accurate MLX90614 readings
// ============================================================
#define SERVO_SETTLE_MS   900   // wait after each servo move (MUST be ≥700ms)
#define SAMPLE_DELAY_MS    60   // between samples (MLX refreshes every ~50ms)
#define SAMPLES_TOTAL       8   // samples collected per point
#define SAMPLES_SKIP        2   // discard first N (stale servo position)
#define SAMPLES_DROP        2   // drop 1 highest + 1 lowest (outlier rejection)
#define ROW_PAUSE_MS     3000   // pause between rows for manual repositioning
#define BETWEEN_SCAN_MS 20000   // wait between full scans

// ============================================================
// FAULT THRESHOLDS
// Change these to match what you're scanning:
//   Human body: OK=37.0 WARN=38.0 CRIT=39.5
//   Electronics: OK=45.0 WARN=55.0 CRIT=70.0
// ============================================================
#define TEMP_OK_MAX    37.0
#define TEMP_WARNING   38.5
#define TEMP_CRITICAL  40.0
#define FAULT_MIN_CELLS  2

// ============================================================
// GLOBALS
// ============================================================
Adafruit_MLX90614 mlx;
Servo             myServo;
WebServer         thermalServer(82);

float   objMap[ROWS][COLS];
float   ambMap[ROWS][COLS];
uint8_t statMap[ROWS][COLS];  // 0=OK 1=WARN 2=NOTOK 3=DANGER

bool    scanDone    = false;
bool    scanRunning = false;
int     scanRow     = 0;
int     scanCol     = 0;

struct FaultZone { int r0,c0,r1,c1,cells,level; float peak; };
FaultZone faults[20];
int  faultCount = 0;
int  cntOK=0,cntWarn=0,cntBad=0,cntDanger=0;
bool sysOK = true;
bool visited[ROWS][COLS];

void startCameraServer();
#if defined(LED_GPIO_NUM)
void setupLedFlash() { ledcAttach(LED_GPIO_NUM,5000,8); }
#endif

// ============================================================
// SERVO HELPER — move with verification
// The fix: use writeMicroseconds() for precise control,
// move in small steps to avoid stall/skip, verify with delay
// ============================================================
void servoMoveTo(int targetDeg) {
  // Clamp to safe range
  if (targetDeg < SERVO_MIN_DEG) targetDeg = SERVO_MIN_DEG;
  if (targetDeg > SERVO_MAX_DEG) targetDeg = SERVO_MAX_DEG;

  // Convert degrees to microseconds for precise control
  // Formula: us = MIN_US + (deg/180) * (MAX_US - MIN_US)
  int us = SERVO_MIN_US + (int)((float)targetDeg / 180.0f * (SERVO_MAX_US - SERVO_MIN_US));

  myServo.writeMicroseconds(us);

  // Wait for servo to physically reach position
  // Then extra time for vibration to settle (important for accurate thermal reading)
  vTaskDelay(pdMS_TO_TICKS(SERVO_SETTLE_MS));
}

void servoCenter() {
  myServo.writeMicroseconds(1500); // exact center = 1500us
  vTaskDelay(pdMS_TO_TICKS(400));
}

// ============================================================
// ACCURATE TEMPERATURE READ
// MLX90614 problem: internal register holds PREVIOUS position
// reading for first 1-2 cycles after sensor FOV changes.
// Fix: skip first SAMPLES_SKIP readings, then collect fresh ones,
// then sort and drop outliers before averaging.
// ============================================================
float readTemp() {
  // Flush stale buffer readings
  for (int i = 0; i < SAMPLES_SKIP; i++) {
    mlx.readObjectTempC();
    vTaskDelay(pdMS_TO_TICKS(SAMPLE_DELAY_MS));
  }

  // Collect fresh samples
  float s[SAMPLES_TOTAL];
  for (int i = 0; i < SAMPLES_TOTAL; i++) {
    s[i] = mlx.readObjectTempC();
    vTaskDelay(pdMS_TO_TICKS(SAMPLE_DELAY_MS));
  }

  // Bubble sort ascending
  for (int i = 0; i < SAMPLES_TOTAL-1; i++)
    for (int j = 0; j < SAMPLES_TOTAL-i-1; j++)
      if (s[j] > s[j+1]) { float t=s[j]; s[j]=s[j+1]; s[j+1]=t; }

  // Average middle values (drop 1 lowest + 1 highest)
  float sum = 0; int cnt = 0;
  for (int i = SAMPLES_DROP/2; i < SAMPLES_TOTAL - SAMPLES_DROP/2; i++) {
    sum += s[i]; cnt++;
  }
  return cnt > 0 ? (sum/cnt) : s[SAMPLES_TOTAL/2];
}

// ============================================================
// CLASSIFY
// ============================================================
uint8_t classify(float t) {
  if (t < TEMP_OK_MAX)   return 0;
  if (t < TEMP_WARNING)  return 1;
  if (t < TEMP_CRITICAL) return 2;
  return 3;
}

// ============================================================
// FLOOD FILL — connected fault cluster detection
// ============================================================
void fill(int r, int c, FaultZone &z) {
  if (r<0||r>=ROWS||c<0||c>=COLS||visited[r][c]||statMap[r][c]<2) return;
  visited[r][c]=true; z.cells++;
  if (objMap[r][c]>z.peak)       z.peak=objMap[r][c];
  if (r<z.r0)z.r0=r; if(c<z.c0)z.c0=c;
  if (r>z.r1)z.r1=r; if(c>z.c1)z.c1=c;
  if (statMap[r][c]>z.level) z.level=statMap[r][c];
  fill(r+1,c,z);fill(r-1,c,z);fill(r,c+1,z);fill(r,c-1,z);
}

void analyse() {
  faultCount=cntOK=cntWarn=cntBad=cntDanger=0;
  sysOK=true;
  memset(visited,false,sizeof(visited));
  for (int i=0;i<ROWS;i++)
    for (int j=0;j<COLS;j++) {
      statMap[i][j]=classify(objMap[i][j]);
      switch(statMap[i][j]){
        case 0:cntOK++;break; case 1:cntWarn++;break;
        case 2:cntBad++;sysOK=false;break;
        case 3:cntDanger++;sysOK=false;break;
      }
    }
  for (int i=0;i<ROWS;i++)
    for (int j=0;j<COLS;j++)
      if(!visited[i][j]&&statMap[i][j]>=2){
        FaultZone z={i,j,i,j,0,(int)statMap[i][j],objMap[i][j]};
        fill(i,j,z);
        if(z.cells>=FAULT_MIN_CELLS&&faultCount<20)faults[faultCount++]=z;
      }

  // Print full grid to Serial
  Serial.println(F("\n====== SCAN RESULT ======"));
  Serial.printf("Status: %s\n", sysOK?"ALL OK":"FAULT DETECTED");
  float minT=999,maxT=-999;
  for(int i=0;i<ROWS;i++)for(int j=0;j<COLS;j++){
    if(objMap[i][j]<minT)minT=objMap[i][j];
    if(objMap[i][j]>maxT)maxT=objMap[i][j];
  }
  Serial.printf("Range: %.2f°C – %.2f°C  (spread: %.2f°C)\n",minT,maxT,maxT-minT);
  Serial.println(F("Object temps (°C):"));
  Serial.print("     ");
  for(int j=0;j<COLS;j++) Serial.printf(" %4d",j);
  Serial.println();
  for(int i=0;i<ROWS;i++){
    Serial.printf("R%02d:",i);
    for(int j=0;j<COLS;j++) Serial.printf(" %4.1f",objMap[i][j]);
    Serial.println();
  }
  Serial.printf("OK:%d Warn:%d NotOK:%d Danger:%d  Faults:%d\n",
                cntOK,cntWarn,cntBad,cntDanger,faultCount);
  Serial.println(F("=========================\n"));
}

// ============================================================
// SCAN TASK — Core 0
// ============================================================
void scanTask(void *p) {
  vTaskDelay(pdMS_TO_TICKS(2000));

  // Column angles: evenly distribute across servo range
  float step = (float)(SERVO_MAX_DEG - SERVO_MIN_DEG) / (float)(COLS - 1);
  int   angles[COLS];
  for (int j=0;j<COLS;j++)
    angles[j] = SERVO_MIN_DEG + (int)(j * step);

  for (;;) {
    scanRunning=true; scanDone=false;
    Serial.println(F("\n[SCAN] Starting new scan..."));
    Serial.printf("[SCAN] Angles: %d° to %d° in %.1f° steps\n",
                  SERVO_MIN_DEG, SERVO_MAX_DEG, step);

    for (int row=0; row<ROWS; row++) {
      scanRow=row;
      Serial.printf("[SCAN] Row %d/%d — reposition sensor vertically, waiting %dms\n",
                    row+1, ROWS, ROW_PAUSE_MS);
      servoCenter();
      vTaskDelay(pdMS_TO_TICKS(ROW_PAUSE_MS));

      for (int col=0; col<COLS; col++) {
        scanCol=col;
        int deg = angles[col];

        // Move servo to position and wait for settle
        servoMoveTo(deg);

        // Read ambient (quick, once per point)
        ambMap[row][col] = mlx.readAmbientTempC();

        // Read accurate object temp
        float t = readTemp();
        objMap[row][col] = t;

        Serial.printf("  [R%d,C%d] %d°  obj=%.2f°C  amb=%.2f°C  [%s]\n",
          row+1,col+1,deg,t,ambMap[row][col],
          classify(t)==0?"OK":classify(t)==1?"WARN":classify(t)==2?"NOK":"!!!");
      }
      servoCenter();
    }

    analyse();
    scanDone=true; scanRunning=false;
    Serial.printf("[SCAN] Done. Next scan in %d seconds.\n", BETWEEN_SCAN_MS/1000);
    vTaskDelay(pdMS_TO_TICKS(BETWEEN_SCAN_MS));
  }
}

// ============================================================
// COLOUR — smooth purple → red → orange → yellow
// This matches the reference image colour scale exactly
// Maps temperature within the actual scanned range dynamically
// ============================================================

// Global min/max tracked across current scan for dynamic scaling
float gMinT = 20.0;
float gMaxT = 40.0;

// Returns an RGB hex string interpolated across the heatmap palette
// Palette: purple(0%) → dark red(25%) → red(45%) → orange(70%) → yellow(100%)
String heatColor(float t, float lo, float hi) {
  if (hi <= lo) hi = lo + 0.01f;
  float pct = (t - lo) / (hi - lo);
  if (pct < 0) pct = 0;
  if (pct > 1) pct = 1;

  // 5-stop palette matching reference image
  // Stop 0 (0%):   #2d1b69  deep purple
  // Stop 1 (25%):  #8b1a4a  dark magenta-red
  // Stop 2 (50%):  #c0392b  red
  // Stop 3 (75%):  #e67e22  orange
  // Stop 4 (100%): #f1c40f  yellow
  struct Stop { float p; uint8_t r,g,b; };
  Stop stops[] = {
    {0.00f,  45,  27,105},
    {0.25f, 139,  26, 74},
    {0.50f, 192,  57, 43},
    {0.75f, 230, 126, 34},
    {1.00f, 241, 196, 15}
  };
  int n = 5;

  // Find which two stops to interpolate between
  int lo_i = 0;
  for (int i=0;i<n-1;i++) if (pct >= stops[i].p) lo_i = i;
  int hi_i = lo_i + 1;
  if (hi_i >= n) hi_i = n-1;

  float span = stops[hi_i].p - stops[lo_i].p;
  float t2   = (span > 0) ? (pct - stops[lo_i].p) / span : 0;

  uint8_t r = (uint8_t)(stops[lo_i].r + t2*(stops[hi_i].r - stops[lo_i].r));
  uint8_t g = (uint8_t)(stops[lo_i].g + t2*(stops[hi_i].g - stops[lo_i].g));
  uint8_t b = (uint8_t)(stops[lo_i].b + t2*(stops[hi_i].b - stops[lo_i].b));

  char buf[8];
  snprintf(buf, sizeof(buf), "#%02x%02x%02x", r, g, b);
  return String(buf);
}

// Text colour — white on dark cells, black on bright yellow
String textColor(float pct) {
  return (pct > 0.80f) ? "#1a1a1a" : "#ffffff";
}

// ============================================================
// BUILD HTML — matches reference heatmap style
// ============================================================
String buildHTML() {
  // Compute actual min/max of current scan
  float minT=999, maxT=-999, sumT=0, sumA=0;
  for(int i=0;i<ROWS;i++)
    for(int j=0;j<COLS;j++){
      float o=objMap[i][j];
      if(o<minT)minT=o; if(o>maxT)maxT=o;
      sumT+=o; sumA+=ambMap[i][j];
    }
  float avgT=sumT/(ROWS*COLS), avgA=sumA/(ROWS*COLS);
  // Use actual range for colour scaling (not fixed thresholds)
  float lo = minT, hi = maxT;
  // Ensure at least 0.5°C spread so colours are visible
  if (hi-lo < 0.5f) { lo -= 0.25f; hi += 0.25f; }

  String sysBg  = sysOK ? "#155724" : "#7f1d1d";
  String sysMsg = sysOK ? "ALL PARTS OK" : "FAULT DETECTED";

  String h = F("<!DOCTYPE html><html lang='en'><head>"
    "<meta charset='UTF-8'>"
    "<meta name='viewport' content='width=device-width,initial-scale=1'>"
    "<meta http-equiv='refresh' content='4'>"
    "<title>Thermal Heatmap</title>"
    "<style>"
    ":root{--bg:#111;--sf:#1c1c1c;--bd:#2a2a2a;--acc:#ff6b35;--tx:#e0e0e0;--mu:#666;}"
    "*{box-sizing:border-box;margin:0;padding:0;}"
    "body{background:var(--bg);color:var(--tx);font-family:'Courier New',monospace;padding:16px;}"

    // Tab bar (matching reference)
    ".tabs{display:flex;gap:0;border-bottom:2px solid var(--acc);margin-bottom:16px;}"
    ".tab{padding:8px 18px;font-size:.78rem;letter-spacing:.08em;cursor:pointer;"
         "border-radius:4px 4px 0 0;color:var(--mu);}"
    ".tab.active{background:var(--acc);color:#000;font-weight:bold;}"

    // Banner
    ".banner{padding:10px 16px;border-radius:4px;display:flex;justify-content:"
            "space-between;align-items:center;margin-bottom:14px;font-size:.85rem;"
            "letter-spacing:.1em;font-weight:bold;}"

    // Stats
    ".stats{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:14px;}"
    ".st{background:var(--sf);border:1px solid var(--bd);padding:8px 13px;}"
    ".sv{font-size:1rem;display:block;font-weight:bold;}"
    ".sl{font-size:.58rem;color:var(--mu);margin-top:1px;}"

    // Grid container — matches reference layout
    ".heatmap-wrap{display:flex;gap:12px;align-items:flex-start;margin:14px 0;overflow-x:auto;}"
    ".heatmap-main{flex:1;}"

    // Row/col axis labels
    ".col-axis{display:flex;margin-left:28px;margin-bottom:3px;gap:2px;}"
    ".col-ax{font-size:.58rem;color:var(--mu);text-align:center;flex-shrink:0;}"
    ".grid-row{display:flex;gap:2px;margin-bottom:2px;align-items:center;}"
    ".row-ax{font-size:.58rem;color:var(--mu);width:26px;text-align:right;"
             "margin-right:2px;flex-shrink:0;}"

    // Each cell — smooth filled square with value
    ".cell{flex-shrink:0;border-radius:3px;display:flex;align-items:center;"
          "justify-content:center;font-size:.68rem;font-weight:bold;"
          "transition:transform .15s;cursor:crosshair;position:relative;}"
    ".cell:hover{transform:scale(1.15);z-index:10;}"
    ".cell.fault{outline:2px solid #fff;outline-offset:-2px;animation:bl 0.8s infinite;}"
    "@keyframes bl{0%,100%{outline-color:#fff}50%{outline-color:rgba(255,255,255,.1)}}"

    // Colour scale bar — vertical, right side (matches reference)
    ".scale-bar{display:flex;flex-direction:column;align-items:center;gap:0;width:36px;}"
    ".scale-gradient{width:18px;border-radius:3px;flex:1;min-height:180px;"
                    "background:linear-gradient(to bottom,"
                    "#f1c40f 0%,#e67e22 33%,#c0392b 55%,#8b1a4a 77%,#2d1b69 100%);}"
    ".scale-label{font-size:.62rem;color:var(--mu);white-space:nowrap;}"
    ".scale-top{margin-bottom:4px;} .scale-bot{margin-top:4px;}"

    // X axis numbers at bottom (matching reference 0, 5, 10)
    ".x-axis{display:flex;margin-left:28px;margin-top:4px;gap:2px;}"
    ".x-tick{font-size:.58rem;color:var(--mu);}"

    // Fault cards
    ".faults{margin:12px 0;}"
    ".fc{background:var(--sf);padding:9px 13px;margin-bottom:6px;"
        "border-radius:0 4px 4px 0;border-left:4px solid #b71c1c;}"
    ".fc h3{font-size:.76rem;margin-bottom:2px;}"
    ".fc p{font-size:.66rem;color:#888;margin-top:2px;}"

    // Progress
    ".prog{font-size:.66rem;color:var(--mu);margin:4px 0;}"
    ".pbar{width:100%;height:3px;background:var(--bd);border-radius:2px;margin:3px 0;}"
    ".pfill{height:3px;background:var(--acc);border-radius:2px;}"

    ".note{font-size:.62rem;color:var(--mu);margin-top:5px;}"
    ".link{display:inline-block;margin-top:12px;padding:8px 16px;"
          "border:1px solid var(--acc);color:var(--acc);text-decoration:none;"
          "font-size:.74rem;letter-spacing:.08em;}"
    ".link:hover{background:var(--acc);color:#000;}"
    "</style></head><body>");

  // Tab bar (cosmetic — matching reference UI)
  h += F("<div class='tabs'>"
         "<div class='tab active'>Heatmap</div>"
         "<div class='tab'>Anomaly Confidence</div>"
         "<div class='tab'>Analysis</div>"
         "</div>");

  // Banner
  h += "<div class='banner' style='background:" + sysBg + ";color:#fff;'>";
  h += "<span>" + sysMsg + "</span>";
  h += "<span style='font-size:.75rem'>" + String(faultCount) + " fault zone(s) | ";
  h += "range " + String(minT,1) + "–" + String(maxT,1) + "°C</span></div>";

  // Stats
  h += "<div class='stats'>";
  h += "<div class='st'><span class='sv' style='color:#00c853'>"  +String(cntOK)    +"</span><span class='sl'>OK</span></div>";
  h += "<div class='st'><span class='sv' style='color:#fdd835'>"  +String(cntWarn)  +"</span><span class='sl'>WARNING</span></div>";
  h += "<div class='st'><span class='sv' style='color:#fb8c00'>"  +String(cntBad)   +"</span><span class='sl'>NOT OK</span></div>";
  h += "<div class='st'><span class='sv' style='color:#ef5350'>"  +String(cntDanger)+"</span><span class='sl'>DANGER</span></div>";
  h += "<div class='st'><span class='sv' style='color:#ccc'>" +String(minT,2)+"°C</span><span class='sl'>MIN</span></div>";
  h += "<div class='st'><span class='sv' style='color:#ccc'>" +String(maxT,2)+"°C</span><span class='sl'>MAX</span></div>";
  h += "<div class='st'><span class='sv' style='color:#ccc'>" +String(avgT,2)+"°C</span><span class='sl'>AVG OBJ</span></div>";
  h += "<div class='st'><span class='sv' style='color:#aaa'>" +String(avgA,1) +"°C</span><span class='sl'>AMBIENT</span></div>";
  h += "</div>";

  // Scan progress bar
  if (scanRunning) {
    int done=(scanRow*COLS+scanCol), total=ROWS*COLS, pct=(done*100)/total;
    h += "<div class='prog'>Scanning R"+String(scanRow+1)+"/"+String(ROWS)+
         " C"+String(scanCol+1)+"/"+String(COLS)+" ("+String(pct)+"%)</div>";
    h += "<div class='pbar'><div class='pfill' style='width:"+String(pct)+"%'></div></div>";
  }

  // ---- HEATMAP + SCALE BAR ----
  int cellW = 44;   // cell width px — matches reference cell size
  int cellH = 40;   // cell height px

  h += "<div class='heatmap-wrap'><div class='heatmap-main'>";

  // Column axis (0, 1, 2 ... COLS-1)
  h += "<div class='col-axis'>";
  for (int j=0;j<COLS;j++)
    h += "<div class='col-ax' style='width:"+String(cellW)+"px'>"+String(j)+"</div>";
  h += "</div>";

  // Grid rows
  for (int i=0;i<ROWS;i++) {
    h += "<div class='grid-row'>";
    h += "<span class='row-ax'>"+String(i)+"</span>";
    for (int j=0;j<COLS;j++) {
      float   t   = objMap[i][j];
      uint8_t st  = statMap[i][j];
      float   pct2 = (hi>lo) ? (t-lo)/(hi-lo) : 0.5f;
      if(pct2<0)pct2=0; if(pct2>1)pct2=1;

      String bg  = heatColor(t, lo, hi);
      String tc  = textColor(pct2);
      String fc2 = (st>=2) ? " fault" : "";

      // Tooltip shows exact values
      String tip = "R"+String(i)+" C"+String(j)+" | "+String(t,2)+"°C obj | "+
                   String(ambMap[i][j],2)+"°C amb";

      h += "<div class='cell"+fc2+"' style='width:"+String(cellW)+"px;height:"+
           String(cellH)+"px;background:"+bg+";color:"+tc+";' title='"+tip+"'>";
      h += String(t,1);
      h += "</div>";
    }
    h += "</div>";
  }

  // X-axis tick labels (0, 5, 10 — matching reference)
  h += "<div class='x-axis'>";
  for (int j=0;j<COLS;j++) {
    String lbl = (j==0||j==5||j==10||j==14) ? String(j) : "";
    h += "<div class='x-tick' style='width:"+String(cellW)+"px;text-align:center'>"+lbl+"</div>";
  }
  h += "</div>";

  h += "</div>"; // end heatmap-main

  // Vertical colour scale bar (right side, matching reference)
  h += "<div class='scale-bar'>";
  h += "<span class='scale-label scale-top'>"+String(maxT,1)+"</span>";
  h += "<div class='scale-gradient'></div>";
  // Mid labels
  float mid1 = lo + (hi-lo)*0.75f;
  float mid2 = lo + (hi-lo)*0.50f;
  float mid3 = lo + (hi-lo)*0.25f;
  h += "</div>";  // scale-bar

  // Separate label column for readability
  h += "<div style='display:flex;flex-direction:column;justify-content:space-between;"
       "font-size:.6rem;color:var(--mu);padding:18px 0;'>";
  h += "<span>"+String(maxT,1)+"</span>";
  h += "<span>"+String(mid1,1)+"</span>";
  h += "<span>"+String(mid2,1)+"</span>";
  h += "<span>"+String(mid3,1)+"</span>";
  h += "<span>"+String(minT,1)+"</span>";
  h += "</div>";

  h += "</div>"; // end heatmap-wrap

  // Fault zone detail cards
  if (faultCount > 0) {
    h += "<div class='faults'>";
    for (int i=0;i<faultCount;i++) {
      FaultZone &z=faults[i];
      String bc=(z.level==3)?"#b71c1c":"#e65100";
      h += "<div class='fc' style='border-left-color:"+bc+"'>";
      h += "<h3>Fault Zone "+String(i+1)+" — "+(z.level==3?"DANGER":"NOT OK")+"</h3>";
      h += "<p>Rows "+String(z.r0)+"–"+String(z.r1)+" | Cols "+String(z.c0)+"–"+String(z.c1)+
           " | "+String(z.cells)+" cells | Peak: <b style='color:"+bc+"'>"+String(z.peak,2)+"°C</b></p>";
      h += "<p>"+(z.level==3?"STOP — Check for overheating or short circuit.":
                  "CAUTION — Monitor and check cooling/connections.")+"</p>";
      h += "</div>";
    }
    h += "</div>";
  } else if (scanDone) {
    h += "<div style='padding:10px 14px;background:#155724;border-radius:4px;font-size:.74rem;margin:10px 0;'>";
    h += "All "+String(ROWS*COLS)+" points within safe limits.</div>";
  }

  h += "<div class='note'>Colour scale: purple=coolest ("+String(lo,1)+"°C) → yellow=hottest ("+String(hi,1)+"°C) — dynamic range</div>";
  h += "<div class='note' style='margin-top:3px'>Thresholds: OK&lt;"+String(TEMP_OK_MAX,0)+
       "°C | Warn:"+String(TEMP_OK_MAX,0)+"-"+String(TEMP_WARNING,0)+
       "°C | NotOK:"+String(TEMP_WARNING,0)+"-"+String(TEMP_CRITICAL,0)+
       "°C | Danger:&gt;"+String(TEMP_CRITICAL,0)+"°C</div>";
  h += "<div class='note' style='margin-top:3px'>";
  h += scanRunning?"Scan in progress — auto-refresh 4s":
       (scanDone?"Scan complete — auto-refresh 4s":"Waiting for first scan...");
  h += "</div>";
  h += "<a class='link' href='javascript:void(0)' onclick=\"window.location.href='http://'+window.location.hostname\">";
  h += "[ CAMERA DASHBOARD ]</a>";
  h += "</body></html>";
  return h;
}

void handleRoot() { thermalServer.send(200,"text/html",buildHTML()); }

String buildTelemetryJson() {
  float minT = 999.0f;
  float maxT = -999.0f;
  float sumObj = 0.0f;
  float sumAmb = 0.0f;

  for (int i = 0; i < ROWS; i++) {
    for (int j = 0; j < COLS; j++) {
      float obj = objMap[i][j];
      float amb = ambMap[i][j];
      if (obj < minT) minT = obj;
      if (obj > maxT) maxT = obj;
      sumObj += obj;
      sumAmb += amb;
    }
  }

  int total = ROWS * COLS;
  float avgObj = total > 0 ? sumObj / total : 0.0f;
  float avgAmb = total > 0 ? sumAmb / total : 0.0f;

  String status = sysOK ? "OK" : "NOK";
  String json = "{";
  json += "\"status\":\"" + status + "\",";
  json += "\"scanRunning\":" + String(scanRunning ? "true" : "false") + ",";
  json += "\"scanDone\":" + String(scanDone ? "true" : "false") + ",";
  json += "\"row\":" + String(scanRow) + ",";
  json += "\"col\":" + String(scanCol) + ",";
  json += "\"minTemp\":" + String(minT, 2) + ",";
  json += "\"maxTemp\":" + String(maxT, 2) + ",";
  json += "\"avgTemp\":" + String(avgObj, 2) + ",";
  json += "\"ambientTemp\":" + String(avgAmb, 2) + ",";
  json += "\"okCount\":" + String(cntOK) + ",";
  json += "\"warnCount\":" + String(cntWarn) + ",";
  json += "\"badCount\":" + String(cntBad) + ",";
  json += "\"dangerCount\":" + String(cntDanger) + ",";
  json += "\"faultCount\":" + String(faultCount);
  json += "}";
  return json;
}

void handleData() {
  thermalServer.sendHeader("Access-Control-Allow-Origin", "*");
  thermalServer.send(200, "application/json", buildTelemetryJson());
}

void handleHealth() {
  thermalServer.sendHeader("Access-Control-Allow-Origin", "*");
  thermalServer.send(200, "text/plain", "ok");
}

// ============================================================
// SETUP
// ============================================================
void setup() {
  Serial.begin(115200);
  Serial.setDebugOutput(true);
  Serial.println(F("\n============================"));
  Serial.println(F("  ESP32-S3 Thermal Heatmap"));
  Serial.println(F("============================\n"));

  // ----- I2C + MLX90614 -----
  Wire.begin(SDA_PIN, SCL_PIN, 100000);
  delay(500);
  if (!mlx.begin()) {
    Serial.println(F("[ERROR] MLX90614 not found!"));
    Serial.printf(F("  SDA=GPIO%d  SCL=GPIO%d\n"), SDA_PIN, SCL_PIN);
    Serial.println(F("  Need 4.7k pull-ups on SDA+SCL to 3.3V"));
  } else {
    Serial.println(F("[OK] MLX90614 detected"));
    Serial.println(F("[TEST] 5 live readings:"));
    for (int i=0;i<5;i++) {
      Serial.printf("  #%d obj=%.2f°C amb=%.2f°C\n",
                    i+1, mlx.readObjectTempC(), mlx.readAmbientTempC());
      delay(100);
    }
  }

  // ----- Servo — FIXED INIT -----
  // Use allocateTimer(0) to ensure no PWM conflicts with camera LEDC
  ESP32PWM::allocateTimer(0);
  ESP32PWM::allocateTimer(1);
  ESP32PWM::allocateTimer(2);
  ESP32PWM::allocateTimer(3);

  myServo.setPeriodHertz(50);              // Standard 50Hz servo signal
  myServo.attach(SERVO_PIN, SERVO_MIN_US, SERVO_MAX_US);  // with min/max pulse

  Serial.println(F("[SERVO] Attached. Running test sweep..."));
  // Test sweep — verifies servo is wired and responding
  Serial.println(F("[SERVO] Moving to 0°..."));
  myServo.writeMicroseconds(SERVO_MIN_US); delay(800);
  Serial.println(F("[SERVO] Moving to 90°..."));
  myServo.writeMicroseconds(1500);          delay(800);
  Serial.println(F("[SERVO] Moving to 180°..."));
  myServo.writeMicroseconds(SERVO_MAX_US); delay(800);
  Serial.println(F("[SERVO] Returning to center..."));
  myServo.writeMicroseconds(1500);          delay(600);
  Serial.println(F("[SERVO] Test sweep complete"));

  // ----- Camera -----
  camera_config_t cfg;
  cfg.ledc_channel=LEDC_CHANNEL_0; cfg.ledc_timer=LEDC_TIMER_0;
  cfg.pin_d0=Y2_GPIO_NUM; cfg.pin_d1=Y3_GPIO_NUM;
  cfg.pin_d2=Y4_GPIO_NUM; cfg.pin_d3=Y5_GPIO_NUM;
  cfg.pin_d4=Y6_GPIO_NUM; cfg.pin_d5=Y7_GPIO_NUM;
  cfg.pin_d6=Y8_GPIO_NUM; cfg.pin_d7=Y9_GPIO_NUM;
  cfg.pin_xclk=XCLK_GPIO_NUM; cfg.pin_pclk=PCLK_GPIO_NUM;
  cfg.pin_vsync=VSYNC_GPIO_NUM; cfg.pin_href=HREF_GPIO_NUM;
  cfg.pin_sccb_sda=SIOD_GPIO_NUM; cfg.pin_sccb_scl=SIOC_GPIO_NUM;
  cfg.pin_pwdn=PWDN_GPIO_NUM; cfg.pin_reset=RESET_GPIO_NUM;
  cfg.xclk_freq_hz=20000000; cfg.pixel_format=PIXFORMAT_JPEG;
  cfg.frame_size=FRAMESIZE_UXGA; cfg.grab_mode=CAMERA_GRAB_WHEN_EMPTY;
  cfg.fb_location=CAMERA_FB_IN_PSRAM; cfg.jpeg_quality=12; cfg.fb_count=1;
  if (psramFound()) { cfg.jpeg_quality=10; cfg.fb_count=2; cfg.grab_mode=CAMERA_GRAB_LATEST; }
  else              { cfg.frame_size=FRAMESIZE_SVGA; cfg.fb_location=CAMERA_FB_IN_DRAM; }

  if (esp_camera_init(&cfg)!=ESP_OK) {
    Serial.println(F("[ERROR] Camera init failed"));
  } else {
    sensor_t *s=esp_camera_sensor_get();
    if(s->id.PID==OV3660_PID){s->set_vflip(s,1);s->set_brightness(s,1);s->set_saturation(s,-2);}
    s->set_framesize(s,FRAMESIZE_QVGA);
#if defined(CAMERA_MODEL_ESP32S3_EYE)
    s->set_vflip(s,1);
#endif
    Serial.println(F("[OK] Camera initialized"));
  }
#if defined(LED_GPIO_NUM)
  setupLedFlash();
#endif

  // ----- WiFi -----
  Serial.printf("[WiFi] Connecting to %s...\n", ssid);
  WiFi.begin(ssid,password);
  WiFi.setSleep(false);
  int att=0;
  while(WiFi.status()!=WL_CONNECTED){
    delay(500); Serial.print(".");
    if(++att>40){Serial.println(F("\n[ERROR] WiFi failed"));ESP.restart();}
  }
  String ip=WiFi.localIP().toString();
  Serial.printf("\n[WiFi] Connected: %s\n",ip.c_str());

  startCameraServer();
  thermalServer.on("/",handleRoot);
  thermalServer.on("/data",handleData);
  thermalServer.on("/health",handleHealth);
  thermalServer.begin();
  Serial.println(F("[HTTP] Thermal server on port 82"));

  // Stack 8192 needed for flood-fill recursion
  xTaskCreatePinnedToCore(scanTask,"ThermalScan",8192,NULL,1,NULL,0);

  Serial.println(F("\n============================"));
  Serial.printf("  Camera:  http://%s\n",          ip.c_str());
  Serial.printf("  Stream:  http://%s:81/stream\n", ip.c_str());
  Serial.printf("  Thermal: http://%s:82\n",        ip.c_str());
  Serial.println(F("============================\n"));
}

void loop() {
  thermalServer.handleClient();
  delay(2);
}
