// ============================================================
// app_httpd.cpp
// HTTP Web Server — Live MJPEG Stream + Camera Control UI
// ============================================================

#include "esp_http_server.h"
#include "esp_camera.h"
#include "esp_timer.h"
#include "img_converters.h"
#include "Arduino.h"

// ============================================================
// MJPEG Stream Boundary
// ============================================================
#define PART_BOUNDARY "123456789000000000000987654321"
static const char *_STREAM_CONTENT_TYPE =
    "multipart/x-mixed-replace;boundary=" PART_BOUNDARY;
static const char *_STREAM_BOUNDARY = "\r\n--" PART_BOUNDARY "\r\n";
static const char *_STREAM_PART =
    "Content-Type: image/jpeg\r\nContent-Length: %u\r\nX-Timestamp: %ld.%06ld\r\n\r\n";

// ============================================================
// HTML Control Page
// ============================================================
static const char INDEX_HTML[] PROGMEM = R"rawliteral(
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>ESP32-S3 Camera</title>
  <style>
    :root {
      --bg: #0d0d0d;
      --surface: #1a1a1a;
      --border: #2a2a2a;
      --accent: #00e5ff;
      --accent2: #ff6b35;
      --text: #e0e0e0;
      --muted: #666;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background: var(--bg);
      color: var(--text);
      font-family: 'Courier New', monospace;
      min-height: 100vh;
      display: flex;
      flex-direction: column;
    }
    header {
      padding: 16px 24px;
      border-bottom: 1px solid var(--border);
      display: flex;
      align-items: center;
      gap: 12px;
    }
    .dot {
      width: 10px; height: 10px;
      border-radius: 50%;
      background: var(--accent);
      box-shadow: 0 0 8px var(--accent);
      animation: pulse 1.5s ease-in-out infinite;
    }
    @keyframes pulse {
      0%, 100% { opacity: 1; }
      50% { opacity: 0.3; }
    }
    h1 { font-size: 1rem; letter-spacing: 0.15em; color: var(--accent); font-weight: normal; }
    .container {
      display: flex;
      flex: 1;
      gap: 0;
    }
    .stream-panel {
      flex: 1;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 24px;
      background: #080808;
    }
    #stream-wrapper {
      position: relative;
      border: 1px solid var(--border);
    }
    #stream-wrapper::before {
      content: '';
      position: absolute;
      inset: -1px;
      border: 1px solid var(--accent);
      opacity: 0.3;
      pointer-events: none;
    }
    #stream {
      display: block;
      max-width: 100%;
      max-height: 75vh;
    }
    .controls-panel {
      width: 280px;
      border-left: 1px solid var(--border);
      padding: 20px;
      overflow-y: auto;
      display: flex;
      flex-direction: column;
      gap: 20px;
    }
    .section-title {
      font-size: 0.65rem;
      letter-spacing: 0.2em;
      color: var(--muted);
      text-transform: uppercase;
      margin-bottom: 10px;
    }
    .control-row {
      display: flex;
      flex-direction: column;
      gap: 6px;
      margin-bottom: 12px;
    }
    label {
      font-size: 0.75rem;
      color: var(--muted);
      display: flex;
      justify-content: space-between;
    }
    label span { color: var(--accent); }
    input[type=range] {
      width: 100%;
      accent-color: var(--accent);
      cursor: pointer;
    }
    select {
      width: 100%;
      background: var(--surface);
      color: var(--text);
      border: 1px solid var(--border);
      padding: 6px 8px;
      font-family: inherit;
      font-size: 0.8rem;
      cursor: pointer;
    }
    select:focus { outline: 1px solid var(--accent); }
    .toggle-row {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 10px;
    }
    .toggle-label { font-size: 0.8rem; }
    .toggle {
      position: relative;
      width: 40px; height: 20px;
    }
    .toggle input { opacity: 0; width: 0; height: 0; }
    .slider {
      position: absolute;
      inset: 0;
      background: var(--border);
      border-radius: 20px;
      cursor: pointer;
      transition: 0.3s;
    }
    .slider::before {
      content: '';
      position: absolute;
      width: 14px; height: 14px;
      left: 3px; top: 3px;
      background: var(--muted);
      border-radius: 50%;
      transition: 0.3s;
    }
    input:checked + .slider { background: var(--accent); }
    input:checked + .slider::before {
      transform: translateX(20px);
      background: #000;
    }
    .btn {
      width: 100%;
      padding: 10px;
      background: transparent;
      border: 1px solid var(--accent);
      color: var(--accent);
      font-family: inherit;
      font-size: 0.8rem;
      letter-spacing: 0.1em;
      cursor: pointer;
      transition: all 0.2s;
      text-transform: uppercase;
    }
    .btn:hover { background: var(--accent); color: #000; }
    .btn.danger { border-color: var(--accent2); color: var(--accent2); }
    .btn.danger:hover { background: var(--accent2); color: #000; }
    .status-bar {
      padding: 8px 24px;
      border-top: 1px solid var(--border);
      font-size: 0.7rem;
      color: var(--muted);
      display: flex;
      gap: 24px;
    }
    .status-item { display: flex; gap: 6px; }
    .status-val { color: var(--text); }
    @media (max-width: 700px) {
      .container { flex-direction: column; }
      .controls-panel { width: 100%; border-left: none; border-top: 1px solid var(--border); }
    }
  </style>
</head>
<body>
  <header>
    <div class="dot"></div>
    <h1>ESP32-S3 CAMERA STREAM</h1>
  </header>

  <div class="container">
    <div class="stream-panel">
      <div id="stream-wrapper">
        <img id="stream" src="" alt="Camera Stream">
      </div>
    </div>

    <div class="controls-panel">

      <!-- Resolution -->
      <div>
        <div class="section-title">Resolution</div>
        <select id="framesize" onchange="updateControl('framesize', this.value)">
          <option value="10">UXGA (1600x1200)</option>
          <option value="9">SXGA (1280x1024)</option>
          <option value="8">XGA  (1024x768)</option>
          <option value="7">SVGA (800x600)</option>
          <option value="6" selected>VGA  (640x480)</option>
          <option value="5">CIF  (400x296)</option>
          <option value="4">QVGA (320x240)</option>
          <option value="3">HQVGA (240x176)</option>
          <option value="0">QQVGA (160x120)</option>
        </select>
      </div>

      <!-- Quality -->
      <div>
        <div class="section-title">Image Settings</div>
        <div class="control-row">
          <label>Quality <span id="quality-val">10</span></label>
          <input type="range" id="quality" min="4" max="63" value="10"
            oninput="document.getElementById('quality-val').textContent=this.value"
            onchange="updateControl('quality', this.value)">
        </div>
        <div class="control-row">
          <label>Brightness <span id="brightness-val">0</span></label>
          <input type="range" id="brightness" min="-2" max="2" value="0"
            oninput="document.getElementById('brightness-val').textContent=this.value"
            onchange="updateControl('brightness', this.value)">
        </div>
        <div class="control-row">
          <label>Contrast <span id="contrast-val">0</span></label>
          <input type="range" id="contrast" min="-2" max="2" value="0"
            oninput="document.getElementById('contrast-val').textContent=this.value"
            onchange="updateControl('contrast', this.value)">
        </div>
        <div class="control-row">
          <label>Saturation <span id="saturation-val">0</span></label>
          <input type="range" id="saturation" min="-2" max="2" value="0"
            oninput="document.getElementById('saturation-val').textContent=this.value"
            onchange="updateControl('saturation', this.value)">
        </div>
        <div class="control-row">
          <label>Sharpness <span id="sharpness-val">0</span></label>
          <input type="range" id="sharpness" min="-2" max="2" value="0"
            oninput="document.getElementById('sharpness-val').textContent=this.value"
            onchange="updateControl('sharpness', this.value)">
        </div>
      </div>

      <!-- White Balance & Exposure -->
      <div>
        <div class="section-title">White Balance & Exposure</div>
        <div class="toggle-row">
          <span class="toggle-label">AWB</span>
          <label class="toggle">
            <input type="checkbox" id="awb" checked onchange="updateControl('awb', this.checked?1:0)">
            <span class="slider"></span>
          </label>
        </div>
        <div class="toggle-row">
          <span class="toggle-label">Auto Exposure</span>
          <label class="toggle">
            <input type="checkbox" id="aec" checked onchange="updateControl('aec', this.checked?1:0)">
            <span class="slider"></span>
          </label>
        </div>
        <div class="toggle-row">
          <span class="toggle-label">AGC (Auto Gain)</span>
          <label class="toggle">
            <input type="checkbox" id="agc" checked onchange="updateControl('agc', this.checked?1:0)">
            <span class="slider"></span>
          </label>
        </div>
      </div>

      <!-- Flip / Mirror -->
      <div>
        <div class="section-title">Orientation</div>
        <div class="toggle-row">
          <span class="toggle-label">Vertical Flip</span>
          <label class="toggle">
            <input type="checkbox" id="vflip" onchange="updateControl('vflip', this.checked?1:0)">
            <span class="slider"></span>
          </label>
        </div>
        <div class="toggle-row">
          <span class="toggle-label">H-Mirror</span>
          <label class="toggle">
            <input type="checkbox" id="hmirror" onchange="updateControl('hmirror', this.checked?1:0)">
            <span class="slider"></span>
          </label>
        </div>
      </div>

      <!-- Snapshot -->
      <div style="display:flex; flex-direction:column; gap:8px;">
        <button class="btn" onclick="takeSnapshot()">[ SNAPSHOT ]</button>
        <button class="btn danger" onclick="resetCamera()">[ RESET CAM ]</button>
      </div>

    </div>
  </div>

  <div class="status-bar">
    <div class="status-item">HOST <span class="status-val" id="host-ip">-</span></div>
    <div class="status-item">STREAM <span class="status-val" id="stream-status">CONNECTING</span></div>
  </div>

  <script>
    const host = window.location.hostname;
    document.getElementById('host-ip').textContent = host;

    const streamEl = document.getElementById('stream');
    streamEl.src = `http://${host}:81/stream`;
    streamEl.onload = () => document.getElementById('stream-status').textContent = 'LIVE';
    streamEl.onerror = () => document.getElementById('stream-status').textContent = 'ERROR';

    function updateControl(name, value) {
      fetch(`/control?var=${name}&val=${value}`)
        .catch(err => console.error('Control error:', err));
    }

    function takeSnapshot() {
      const a = document.createElement('a');
      a.href = `/capture`;
      a.download = `snapshot_${Date.now()}.jpg`;
      a.click();
    }

    function resetCamera() {
      if (confirm('Reset camera sensor?')) {
        fetch('/reset').then(() => location.reload());
      }
    }
  </script>
</body>
</html>
)rawliteral";

// ============================================================
// Server Handles
// ============================================================
static httpd_handle_t camera_httpd = NULL;
static httpd_handle_t stream_httpd = NULL;

// ============================================================
// Handler: Root page
// ============================================================
static esp_err_t index_handler(httpd_req_t *req) {
  httpd_resp_set_type(req, "text/html");
  httpd_resp_set_hdr(req, "Content-Encoding", "identity");
  return httpd_resp_send(req, INDEX_HTML, strlen(INDEX_HTML));
}

// ============================================================
// Handler: MJPEG Stream (port 81)
// ============================================================
static esp_err_t stream_handler(httpd_req_t *req) {
  camera_fb_t *fb = NULL;
  struct timeval _timestamp;
  esp_err_t res = ESP_OK;
  size_t _jpg_buf_len = 0;
  uint8_t *_jpg_buf = NULL;
  char part_buf[128];

  httpd_resp_set_type(req, _STREAM_CONTENT_TYPE);
  httpd_resp_set_hdr(req, "Access-Control-Allow-Origin", "*");
  httpd_resp_set_hdr(req, "X-Framerate", "60");

  while (true) {
    fb = esp_camera_fb_get();
    if (!fb) {
      Serial.println("[STREAM] Frame capture failed");
      res = ESP_FAIL;
      break;
    }

    gettimeofday(&_timestamp, NULL);

    if (fb->format != PIXFORMAT_JPEG) {
      bool jpeg_converted = frame2jpg(fb, 80, &_jpg_buf, &_jpg_buf_len);
      esp_camera_fb_return(fb);
      fb = NULL;
      if (!jpeg_converted) {
        Serial.println("[STREAM] JPEG conversion failed");
        res = ESP_FAIL;
        break;
      }
    } else {
      _jpg_buf_len = fb->len;
      _jpg_buf = fb->buf;
    }

    // Write boundary
    res = httpd_resp_send_chunk(req, _STREAM_BOUNDARY, strlen(_STREAM_BOUNDARY));
    if (res != ESP_OK) break;

    // Write part header
    size_t hlen = snprintf(part_buf, sizeof(part_buf), _STREAM_PART,
                           _jpg_buf_len, _timestamp.tv_sec, _timestamp.tv_usec);
    res = httpd_resp_send_chunk(req, part_buf, hlen);
    if (res != ESP_OK) break;

    // Write JPEG data
    res = httpd_resp_send_chunk(req, (const char *)_jpg_buf, _jpg_buf_len);

    if (fb) {
      esp_camera_fb_return(fb);
      fb = NULL;
      _jpg_buf = NULL;
    } else if (_jpg_buf) {
      free(_jpg_buf);
      _jpg_buf = NULL;
    }

    if (res != ESP_OK) break;
  }

  return res;
}

// ============================================================
// Handler: Single JPEG capture (for snapshot)
// ============================================================
static esp_err_t capture_handler(httpd_req_t *req) {
  camera_fb_t *fb = esp_camera_fb_get();
  if (!fb) {
    httpd_resp_send_500(req);
    return ESP_FAIL;
  }
  httpd_resp_set_type(req, "image/jpeg");
  httpd_resp_set_hdr(req, "Content-Disposition", "attachment; filename=capture.jpg");
  httpd_resp_set_hdr(req, "Access-Control-Allow-Origin", "*");
  esp_err_t res = httpd_resp_send(req, (const char *)fb->buf, fb->len);
  esp_camera_fb_return(fb);
  return res;
}

// ============================================================
// Handler: Camera control (/control?var=X&val=Y)
// ============================================================
static esp_err_t cmd_handler(httpd_req_t *req) {
  char buf[64];
  char var[32], val[32];

  if (httpd_req_get_url_query_str(req, buf, sizeof(buf)) != ESP_OK) {
    httpd_resp_send_404(req);
    return ESP_FAIL;
  }
  if (httpd_query_key_value(buf, "var", var, sizeof(var)) != ESP_OK ||
      httpd_query_key_value(buf, "val", val, sizeof(val)) != ESP_OK) {
    httpd_resp_send_404(req);
    return ESP_FAIL;
  }

  int value = atoi(val);
  sensor_t *s = esp_camera_sensor_get();
  int res = -1;

  if      (!strcmp(var, "framesize"))  res = s->set_framesize(s, (framesize_t)value);
  else if (!strcmp(var, "quality"))    res = s->set_quality(s, value);
  else if (!strcmp(var, "brightness")) res = s->set_brightness(s, value);
  else if (!strcmp(var, "contrast"))   res = s->set_contrast(s, value);
  else if (!strcmp(var, "saturation")) res = s->set_saturation(s, value);
  else if (!strcmp(var, "sharpness"))  res = s->set_sharpness(s, value);
  else if (!strcmp(var, "vflip"))      res = s->set_vflip(s, value);
  else if (!strcmp(var, "hmirror"))    res = s->set_hmirror(s, value);
  else if (!strcmp(var, "awb"))        res = s->set_whitebal(s, value);
  else if (!strcmp(var, "aec"))        res = s->set_exposure_ctrl(s, value);
  else if (!strcmp(var, "agc"))        res = s->set_gain_ctrl(s, value);

  if (res != 0) {
    Serial.printf("[CTRL] Unknown or failed: %s=%d\n", var, value);
  }

  httpd_resp_set_hdr(req, "Access-Control-Allow-Origin", "*");
  return httpd_resp_send(req, NULL, 0);
}

// ============================================================
// Handler: Reset camera
// ============================================================
static esp_err_t reset_handler(httpd_req_t *req) {
  httpd_resp_send(req, "OK", 2);
  delay(100);
  ESP.restart();
  return ESP_OK;
}

// ============================================================
// startCameraServer() — called from main sketch
// ============================================================
void startCameraServer() {
  httpd_config_t config = HTTPD_DEFAULT_CONFIG();
  config.max_uri_handlers = 16;

  // ----- Main server on port 80 -----
  config.server_port = 80;
  config.ctrl_port   = 32768;

  httpd_uri_t index_uri = {
    .uri = "/", .method = HTTP_GET, .handler = index_handler, .user_ctx = NULL
  };
  httpd_uri_t capture_uri = {
    .uri = "/capture", .method = HTTP_GET, .handler = capture_handler, .user_ctx = NULL
  };
  httpd_uri_t cmd_uri = {
    .uri = "/control", .method = HTTP_GET, .handler = cmd_handler, .user_ctx = NULL
  };
  httpd_uri_t reset_uri = {
    .uri = "/reset", .method = HTTP_GET, .handler = reset_handler, .user_ctx = NULL
  };

  if (httpd_start(&camera_httpd, &config) == ESP_OK) {
    httpd_register_uri_handler(camera_httpd, &index_uri);
    httpd_register_uri_handler(camera_httpd, &capture_uri);
    httpd_register_uri_handler(camera_httpd, &cmd_uri);
    httpd_register_uri_handler(camera_httpd, &reset_uri);
    Serial.println("[HTTP] Main server started on port 80");
  }

  // ----- Stream server on port 81 -----
  config.server_port = 81;
  config.ctrl_port   = 32769;

  httpd_uri_t stream_uri = {
    .uri = "/stream", .method = HTTP_GET, .handler = stream_handler, .user_ctx = NULL
  };

  if (httpd_start(&stream_httpd, &config) == ESP_OK) {
    httpd_register_uri_handler(stream_httpd, &stream_uri);
    Serial.println("[HTTP] Stream server started on port 81");
  }
}
