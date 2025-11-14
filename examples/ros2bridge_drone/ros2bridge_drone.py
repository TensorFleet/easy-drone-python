#!/usr/bin/env python3
import time
import math
import threading

import roslibpy


ARM_WAIT_SECONDS = 3.0          # Wait after connect before arming (unchanged)
TAKEOFF_ALTITUDE = 3.0          # Target takeoff altitude (m AGL from home_z)
POSITION_TOLERANCE = 1.5        # Waypoint distance tolerance (m) for long legs
ALTITUDE_TOLERANCE = 0.3        # Altitude tolerance (m)
TIMEOUT = 900.0                 # Generic timeout for long legs (s)
SETPOINT_HZ = 20.0              # Stream rate for position setpoints (Hz) >2 Hz required
SETPOINT_ACCEPT_MODES = ('OFFBOARD',)  # PX4: external setpoints only in OFFBOARD


class DroneError(Exception):
  pass


class MavrosBridgeController:
  """
  PX4 SITL via MAVROS (ROS 2) over rosbridge using roslibpy.

  Subs:
    /mavros/state                   (mavros_msgs/State)
    /mavros/local_position/pose     (geometry_msgs/PoseStamped)
    /mavros/global_position/global  (sensor_msgs/NavSatFix)
    /mavros/altitude                (mavros_msgs/Altitude)

  Pubs:
    /mavros/setpoint_position/local (geometry_msgs/PoseStamped)

  Srvs:
    /mavros/cmd/arming              (mavros_msgs/CommandBool)
    /mavros/cmd/takeoff             (mavros_msgs/CommandTOL)         # kept for other flows
    /mavros/cmd/land                (mavros_msgs/CommandTOL)
    /mavros/cmd/command             (mavros_msgs/CommandLong)        # used for NAV_TAKEOFF
    /mavros/set_mode                (mavros_msgs/SetMode)
    /mavros/sys/set_parameters      (rcl_interfaces/srv/SetParameters)
    /mavros/param/set               (mavros_msgs/ParamSetV2)

  Notes:
    * OFFBOARD utilities remain for your mission legs; takeoff stage no longer uses them.
    * Takeoff logic now: arm (if needed) -> MAV_CMD_NAV_TAKEOFF -> wait AUTO.LOITER@alt.
  """

  def __init__(self, host='172.16.0.10', port=9091):
    self.ros = roslibpy.Ros(host=host, port=port)

    self.state = None
    self.current_pose = None
    self.home_position = None
    self.home_z = None
    self.global_fix = None  # NavSatFix

    # status thread control
    self._status_thread = None
    self._status_thread_stop = False

    # setpoint streaming (PoseStamped OFFBOARD)
    self._sp_thread = None
    self._sp_stop = False
    self._sp_lock = threading.Lock()
    self._sp_target = {'x': 0.0, 'y': 0.0, 'z': 0.0, 'yaw': None}

    # takeoff/altitude reach signaling (still used by mission if needed)
    self._takeoff_reached_event = threading.Event()

    # --- Topics (subscribers) ---
    self.state_sub = roslibpy.Topic(self.ros, '/mavros/state', 'mavros_msgs/State')
    self.pose_sub = roslibpy.Topic(self.ros, '/mavros/local_position/pose', 'geometry_msgs/PoseStamped')
    self.global_sub = roslibpy.Topic(self.ros, '/mavros/global_position/global', 'sensor_msgs/NavSatFix')
    self.alt_sub = roslibpy.Topic(self.ros, '/mavros/altitude', 'mavros_msgs/Altitude')

    # --- Topics (publishers) ---
    self.setpoint_pos_pub = roslibpy.Topic(self.ros, '/mavros/setpoint_position/local', 'geometry_msgs/PoseStamped')

    # --- Services (MAVROS) ---
    self.arm_srv = roslibpy.Service(self.ros, '/mavros/cmd/arming', 'mavros_msgs/CommandBool')
    self.takeoff_srv = roslibpy.Service(self.ros, '/mavros/cmd/takeoff', 'mavros_msgs/CommandTOL')  # kept
    self.land_srv = roslibpy.Service(self.ros, '/mavros/cmd/land', 'mavros_msgs/CommandTOL')
    self.cmd_long_srv = roslibpy.Service(self.ros, '/mavros/cmd/command', 'mavros_msgs/CommandLong')
    self.mode_srv = roslibpy.Service(self.ros, '/mavros/set_mode', 'mavros_msgs/SetMode')

    # ROS 2 parameters on MAVROS node
    self.param_srv = roslibpy.Service(self.ros, '/mavros/sys/set_parameters', 'rcl_interfaces/srv/SetParameters')

    # PX4 params (via MAVROS)
    self.param_set_srv = roslibpy.Service(self.ros, '/mavros/param/set', 'mavros_msgs/ParamSetV2')

  # ------------------------------------------------------------------
  # Connection & basic callbacks
  # ------------------------------------------------------------------
  def connect(self):
    self.ros.run()
    start = time.time()
    while not self.ros.is_connected:
      if time.time() - start > 10.0:
        raise DroneError('Timeout connecting to rosbridge')
      time.sleep(0.02)
    print('Connected to rosbridge')

    # Short grace period
    time.sleep(0.3)

    # Set ROS 2 params on mavros sys plugin via /mavros/sys/set_parameters
    self._set_heartbeat_params()

    # Subscribe to MAVROS topics
    self.state_sub.subscribe(self._state_cb)
    self.pose_sub.subscribe(self._pose_cb)
    self.global_sub.subscribe(self._global_cb)
    self.alt_sub.subscribe(self._alt_cb)

    # Wait until we have state & pose so we can talk to FCU
    self._wait_for_state()
    self._wait_for_pose()

    # Disable PX4 battery/power arming checks and reboot FCU (SITL intent) — unchanged
    print('[DEV] Disabling PX4 battery/power arming checks (CBRK_SUPPLY_CHK, COM_ARM_BAT_MIN) and rebooting...')
    self._disable_battery_checks_and_reboot()
    print('[DEV] FCU rebooted. Re-synchronizing topics...')

    # After reboot, wait again for FCU state & pose and set home
    self._wait_for_state(timeout=15.0)
    self._wait_for_pose(timeout=15.0)

    # Treat the first pose AFTER reboot as "home"
    self.home_position = self.current_pose.copy()
    self.home_z = self.home_position['pose']['position']['z']
    print('Got initial state and pose, home position set')
    print(f"Current FCU mode at connect: {self.state.get('mode')}")

    # Initialize setpoint target at current pose so OFFBOARD acceptance is immediate
    pos = self.current_pose['pose']['position']
    self._set_target_pose(pos['x'], pos['y'], pos['z'], yaw=None)

    # Start periodic status updates (once per second) and setpoint stream (>2 Hz)
    self._start_status_loop()
    self._start_setpoint_stream()

  def _state_cb(self, msg): self.state = msg
  def _pose_cb(self, msg): self.current_pose = msg
  def _global_cb(self, msg): self.global_fix = msg
  def _alt_cb(self, msg): self.altitude = msg

  def _wait_for_state(self, timeout=5.0):
    start = time.time()
    while self.state is None:
      if time.time() - start > timeout:
        raise DroneError('No /mavros/state received')
      time.sleep(0.02)

  def _wait_for_pose(self, timeout=5.0):
    start = time.time()
    while self.current_pose is None:
      if time.time() - start > timeout:
        raise DroneError('No /mavros/local_position/pose received')
      time.sleep(0.02)

  def _have_gps_fix(self):
    return bool(self.global_fix and
                isinstance(self.global_fix.get('latitude', None), (int, float)) and
                isinstance(self.global_fix.get('longitude', None), (int, float)))

  # ------------------------------------------------------------------
  # Periodic status updates (1 Hz)
  # ------------------------------------------------------------------
  def _start_status_loop(self):
    if self._status_thread is not None:
      return
    self._status_thread_stop = False
    self._status_thread = threading.Thread(target=self._status_loop, daemon=True)
    self._status_thread.start()

  def _stop_status_loop(self):
    self._status_thread_stop = True
    if self._status_thread is not None:
      self._status_thread.join(timeout=1.0)
    self._status_thread = None

  def _status_loop(self):
    while not self._status_thread_stop and self.ros.is_connected:
      try:
        if self.state and self.current_pose:
          pos = self.current_pose['pose']['position']
          mode = self.state.get('mode')
          armed = self.state.get('armed')
          status = self.state.get('system_status')
          agl = self._get_agl()
          print(f"[STATUS] mode={mode} armed={armed} sys_status={status} "
                f"pos=({pos['x']:.2f}, {pos['y']:.2f}, {pos['z']:.2f}) agl={agl:.2f}m")
        else:
          print("[STATUS] waiting for telemetry (no state/pose yet)")
      except Exception as e:
        print(f"[STATUS] error while printing status: {e}")
      time.sleep(1.0)

  # ------------------------------------------------------------------
  # Altitude helper (sign-agnostic): AGL = |z - home_z|   (ROS ENU: +Z Up)
  # ------------------------------------------------------------------
  def _get_agl(self):
    if not self.current_pose or self.home_z is None:
      return 0.0
    z = self.current_pose['pose']['position']['z']
    return abs(z - self.home_z)

  # ------------------------------------------------------------------
  # ROS 2 parameter setting (sys plugin heartbeat)
  # ------------------------------------------------------------------
  def _set_heartbeat_params(self):
    PARAMETER_DOUBLE = 3
    PARAMETER_STRING = 4
    req = roslibpy.ServiceRequest({
      'parameters': [
        {'name': 'heartbeat_mav_type',
         'value': {'type': PARAMETER_STRING, 'string_value': 'GCS'}},
        {'name': 'heartbeat_rate',
         'value': {'type': PARAMETER_DOUBLE, 'double_value': 2.0}},
      ]
    })
    resp = self.param_srv.call(req)
    results = resp.get('results', [])
    if len(results) != 2:
      raise DroneError(f'Expected 2 SetParameters results, got {len(results)} – response: {resp}')
    for param_name, result in zip(['heartbeat_mav_type', 'heartbeat_rate'], results):
      if not result.get('successful', False):
        reason = result.get('reason', 'no reason provided')
        raise DroneError(f'Failed to set parameter {param_name}: {reason}')
    print('MAVROS sys heartbeat params set: heartbeat_mav_type=GCS, heartbeat_rate=2.0 Hz')

  # ------------------------------------------------------------------
  # PX4 battery/power checks disabling + reboot (SITL)  (UNCHANGED)
  # ------------------------------------------------------------------
  def _disable_battery_checks_and_reboot(self):
    PARAMETER_INTEGER = 2
    PARAMETER_DOUBLE = 3

    req1 = roslibpy.ServiceRequest({
      'force_set': True,
      'param_id': 'CBRK_SUPPLY_CHK',
      'value': {'type': PARAMETER_INTEGER, 'integer_value': 894281}
    })
    r1 = self.param_set_srv.call(req1)
    if not r1.get('success', True):
      print('[DEV][WARN] Failed to set CBRK_SUPPLY_CHK:', r1)

    req2 = roslibpy.ServiceRequest({
      'force_set': True,
      'param_id': 'COM_ARM_BAT_MIN',
      'value': {'type': PARAMETER_DOUBLE, 'double_value': 0.0}
    })
    r2 = self.param_set_srv.call(req2)
    if not r2.get('success', True):
      print('[DEV][WARN] Failed to set COM_ARM_BAT_MIN:', r2)

    reboot_req = roslibpy.ServiceRequest({
      'command': 246,  # MAV_CMD_PREFLIGHT_REBOOT_SHUTDOWN
      'confirmation': 0,
      'param1': 1.0, 'param2': 0.0, 'param3': 0.0, 'param4': 0.0,
      'param5': 0.0, 'param6': 0.0, 'param7': 0.0
    })
    _ = self.cmd_long_srv.call(reboot_req)

    self._wait_for_fcu_cycle()

  def _wait_for_fcu_cycle(self, disconnect_timeout=10.0, reconnect_timeout=30.0):
    t0 = time.time()
    while self.state and self.state.get('connected', True):
      if time.time() - t0 > disconnect_timeout:
        print('[DEV][WARN] Did not observe FCU disconnect; continuing to wait for reconnect...')
        break
      time.sleep(0.05)

    t1 = time.time()
    while (not self.state) or (not self.state.get('connected', False)):
      if time.time() - t1 > reconnect_timeout:
        raise DroneError('Timeout waiting for FCU to reconnect after reboot')
      time.sleep(0.05)

    time.sleep(0.5)

  # ------------------------------------------------------------------
  # FCU arming, OFFBOARD handshake, takeoff/land
  # ------------------------------------------------------------------
  def ensure_offboard(self, prestream_seconds=1.5):
    """
    OFFBOARD handshake:
      - stream PoseStamped setpoints >2 Hz for a short period
      - set mode OFFBOARD
      - verify state.mode == 'OFFBOARD'
    """
    self._wait_for_pose()

    # Pre-stream current pose
    pos = self.current_pose['pose']['position']
    x, y, z = pos['x'], pos['y'], pos['z']
    self._set_target_pose(x, y, z, yaw=None)

    t_end = time.time() + prestream_seconds
    while time.time() < t_end:
      self._tick_setpoint_stream_once()
      time.sleep(1.0 / SETPOINT_HZ)

    print('Setting mode: OFFBOARD (handshake)')
    req = roslibpy.ServiceRequest({'base_mode': 0, 'custom_mode': 'OFFBOARD'})
    resp = self.mode_srv.call(req)
    if not resp.get('mode_sent', False):
      raise DroneError('FCU rejected OFFBOARD (mode_sent=False)')

    # Verify OFFBOARD while continuing to stream
    start = time.time()
    while (self.state is None or (self.state.get('mode') or '').upper() != 'OFFBOARD') and time.time() - start < 3.0:
      self._tick_setpoint_stream_once()
      time.sleep(1.0 / SETPOINT_HZ)

    if (self.state.get('mode') or '').upper() != 'OFFBOARD':
      raise DroneError('Unable to enter OFFBOARD during handshake')

    print('Mode is now OFFBOARD')

  def ensure_armed(self):
    self._wait_for_state()

    # Ensure OFFBOARD is ready before arming (UNCHANGED for your flow)
    if (self.state.get('mode') or '').upper() != 'OFFBOARD':
      self.ensure_offboard()

    if self.state.get('armed'):
      print('Already armed, skipping arming step')
      self._schedule_takeoff_procedure()
      return

    print(f'Waiting {ARM_WAIT_SECONDS}s before arming...')
    t_end = time.time() + ARM_WAIT_SECONDS
    while time.time() < t_end:
      self._tick_setpoint_stream_once()
      time.sleep(0.02)

    print('Sending arm command...')
    req = roslibpy.ServiceRequest({'value': True})
    resp = self.arm_srv.call(req)
    if not resp.get('success', False):
      raise DroneError('Arming command failed (response.success == False)')

    start = time.time()
    while not self.state.get('armed') and time.time() - start < 5.0:
      self._tick_setpoint_stream_once()
      time.sleep(0.05)
    if not self.state.get('armed'):
      raise DroneError('Vehicle did not arm within timeout')
    print('Vehicle armed')

    # Takeoff stage (MODIFIED)
    self._schedule_takeoff_procedure()

  # ------------------ TAKEOFF STAGE: CHANGED ONLY HERE ------------------
  def _schedule_takeoff_procedure(self):
    """
    Commander-style takeoff:
      - Send a single MAV_CMD_NAV_TAKEOFF (CommandLong) immediately.
      - Block until AUTO.LOITER at requested relative altitude band.
      - No OFFBOARD setpoint climb/hold involved in takeoff stage.
    """
    target_agl = TAKEOFF_ALTITUDE

    # 1) Send NAV_TAKEOFF now (commander equivalent)
    try:
      self._send_takeoff_command(target_agl)
    except Exception as e:
      print(f'[ERROR] NAV_TAKEOFF send failed: {e}')
      raise

    # 2) Wait until PX4 is AUTO.LOITER at the target altitude band
    try:
      self._wait_until_loiter_at_alt(target_agl, ALTITUDE_TOLERANCE, timeout_s=TIMEOUT if TIMEOUT < 120 else 60.0)
      print(f'[AUTO] Takeoff complete: AUTO.LOITER @ ~{target_agl:.2f} m AGL')
      self._takeoff_reached_event.set()
    except Exception as e:
      print(f'[ERROR] Wait for LOITER@alt failed: {e}')
      raise

  def _send_takeoff_command(self, target_agl: float):
    """
    EXACT pxh `commander takeoff` equivalent:
      Send MAV_CMD_NAV_TAKEOFF (CommandLong) with current lat/lon and target relative altitude.
      No OFFBOARD, no setpoints.
    """
    self._wait_for_pose()
    if not self._have_gps_fix():
      raise DroneError('[TKOFF] No GNSS fix. NAV_TAKEOFF requires lat/lon.')

    lat = float(self.global_fix['latitude'])
    lon = float(self.global_fix['longitude'])
    yaw_deg = 0.0  # keep yaw as-is for now; wire if you need heading

    print(f'[TKOFF] NAV_TAKEOFF {target_agl:.2f} m AGL at lat={lat:.7f}, lon={lon:.7f}')
    req = roslibpy.ServiceRequest({
      'command': 22,        # MAV_CMD_NAV_TAKEOFF
      'confirmation': 0,
      'param1': 0.0,        # min pitch (FW); 0 for multirotor
      'param2': 0.0,
      'param3': 0.0,
      'param4': yaw_deg,    # yaw deg
      'param5': lat,        # latitude deg
      'param6': lon,        # longitude deg
      'param7': float(target_agl),  # relative altitude meters
    })
    resp = self.cmd_long_srv.call(req)
    if not resp.get('success', False):
      raise DroneError(f'MAV_CMD_NAV_TAKEOFF rejected (result={resp.get("result")})')
    print('[TKOFF] Command accepted')

  def _wait_until_loiter_at_alt(self, target_rel_alt_m: float, tol_m: float, timeout_s: float):
    """
    Block until mode == AUTO.LOITER and relative altitude within tolerance.
    Uses /mavros/state.mode and /mavros/altitude.relative
    """
    print('[WAIT] Waiting for AUTO.LOITER at target altitude…')
    t0 = time.time()
    while True:
      mode = (self.state.get('mode') or '').upper() if self.state else ''
      rel = self.altitude.get('relative', float('nan')) if self.altitude else float('nan')
      try:
        rel = float(rel)
      except Exception:
        rel = float('nan')
      in_band = (not math.isnan(rel)) and abs(rel - target_rel_alt_m) <= tol_m

      if mode == 'AUTO.LOITER' and in_band:
        print(f'[WAIT] Reached AUTO.LOITER @ {rel:.2f} m (target {target_rel_alt_m:.2f} ± {tol_m})')
        return

      if time.time() - t0 > timeout_s:
        raise DroneError(f'Timeout waiting for AUTO.LOITER @ {target_rel_alt_m:.2f} m '
                         f'(mode={mode}, rel_alt={rel if not math.isnan(rel) else "NaN"})')

      # Early failure: auto-disarmed on ground
      if self.state and (not self.state.get('armed', True)):
        raise DroneError('Vehicle disarmed before reaching LOITER at altitude')

      time.sleep(0.1)
  # ------------------ END TAKEOFF CHANGES ------------------

  def _start_altitude_hold(self, target_agl: float):
    """
    (UNCHANGED UTIL) Holds XY at current and drives Z to home_z + target_agl using OFFBOARD PoseStamped.
    Not used by new takeoff stage, but kept for your mission tools.
    """
    self._wait_for_pose()
    pos = self.current_pose['pose']['position']
    x0, y0 = pos['x'], pos['y']
    z_target = (self.home_z or 0.0) + float(target_agl)

    self._set_target_pose(x0, y0, z_target, yaw=None)

    def _monitor():
      best_err = float('inf')
      last_better = time.time()
      start = time.time()
      while time.time() - start < TIMEOUT:
        if (self.state.get('mode') or '').upper() != 'OFFBOARD':
          try:
            self.ensure_offboard()
          except Exception:
            pass

        agl = self._get_agl()
        err = abs(agl - target_agl)

        if err < best_err - 0.02:
          best_err = err
          last_better = time.time()

        if err <= ALTITUDE_TOLERANCE:
          print(f'Altitude reached: agl {agl:.2f} m (target {target_agl:.2f} m)')
          self._takeoff_reached_event.set()
          return

        if time.time() - last_better > 5.0:
          self._set_target_pose(x0, y0, z_target, yaw=None)
          try:
            self.ensure_offboard()
          except Exception:
            pass
          last_better = time.time()

        time.sleep(0.05)

      print('[WARN] Altitude hold monitor timeout')
    th = threading.Thread(target=_monitor, daemon=True)
    th.start()

  # ------------------------------------------------------------------
  # Pose setpoint streaming
  # ------------------------------------------------------------------
  def _start_setpoint_stream(self):
    if self._sp_thread and self._sp_thread.is_alive():
      return
    self._sp_stop = False

    def _worker():
      while not self._sp_stop and self.ros.is_connected:
        self._tick_setpoint_stream_once()
        time.sleep(1.0 / SETPOINT_HZ)

    self._sp_thread = threading.Thread(target=_worker, daemon=True)
    self._sp_thread.start()

  def _stop_setpoint_stream(self):
    self._sp_stop = True
    if self._sp_thread and self._sp_thread.is_alive():
      self._sp_thread.join(timeout=1.0)
    self._sp_thread = None

  def _tick_setpoint_stream_once(self):
    with self._sp_lock:
      x = self._sp_target['x']; y = self._sp_target['y']; z = self._sp_target['z']
      yaw = self._sp_target['yaw']
    self._publish_pose_target(x, y, z, yaw)

  def _set_target_pose(self, x, y, z, yaw=None):
    with self._sp_lock:
      self._sp_target.update({'x': float(x), 'y': float(y), 'z': float(z), 'yaw': None if yaw is None else float(yaw)})

  # ------------------------------------------------------------------
  # PoseStamped publishing (ENU; +Z Up)
  # ------------------------------------------------------------------
  def _publish_pose_target(self, x, y, z, yaw=None):
    qx, qy, qz, qw = 0.0, 0.0, 0.0, 1.0
    if yaw is not None:
      cy = math.cos(yaw * 0.5)
      sy = math.sin(yaw * 0.5)
      qx, qy, qz, qw = 0.0, 0.0, sy, cy
    msg = {
      'header': {'frame_id': 'map'},
      'pose': {
        'position': {'x': x, 'y': y, 'z': z},
        'orientation': {'x': qx, 'y': qy, 'z': qz, 'w': qw}
      }
    }
    self.setpoint_pos_pub.publish(roslibpy.Message(msg))

  # ------------------------------------------------------------------
  # Triangle path (300 m edges) in local ENU using Pose setpoints (UNCHANGED)
  # ------------------------------------------------------------------
  def fly_triangle_enu(self, edge_m=300.0):
    self._wait_for_pose()
    start_pos = self.current_pose['pose']['position']
    x0, y0, zf = start_pos['x'], start_pos['y'], start_pos['z']

    Bx = x0 + edge_m
    By = y0
    Cx = Bx + edge_m * 0.5
    Cy = By + edge_m * (math.sqrt(3.0) / 2.0)

    for (x, y) in [(Bx, By), (Cx, Cy), (x0, y0)]:
      self._fly_to_pose(x, y, zf)

  def _fly_to_pose(self, x, y, z, timeout=TIMEOUT):
    self._wait_for_pose()

    if (self.state.get('mode') or '').upper() not in SETPOINT_ACCEPT_MODES:
      self.ensure_offboard()

    print(f'Flying to ({x:.1f}, {y:.1f}, {z:.1f}) via PoseStamped')
    start = time.time()
    last_better = time.time()
    best = float('inf')

    self._set_target_pose(x, y, z)

    def dist():
      pose = self.current_pose['pose']['position']
      dx = pose['x'] - x
      dy = pose['y'] - y
      dz = pose['z'] - z
      return math.sqrt(dx*dx + dy*dy + dz*dz)

    while time.time() - start < timeout:
      d = dist()

      if d <= POSITION_TOLERANCE:
        print(f'Reached waypoint within {d:.2f} m')
        return

      if d < best - 0.2:
        best = d
        last_better = time.time()

      if (self.state.get('mode') or '').upper() != 'OFFBOARD':
        print('[WARN] Dropped out of OFFBOARD; attempting re-entry...')
        self.ensure_offboard()

      if time.time() - last_better > 5.0:
        raise DroneError('Setpoints appear to be ignored (no progress). '
                         'Check OFFBOARD, EKF position, and that no mission/loiter conflicts.')

      time.sleep(0.05)

    raise DroneError('Timeout reaching waypoint')

  # ------------------------------------------------------------------
  # Landing (UNCHANGED)
  # ------------------------------------------------------------------
  def go_home_and_land(self):
    if not self.home_position:
      raise DroneError('Home position not set')
    home_pos = self.home_position['pose']['position']
    self._set_target_pose(home_pos['x'], home_pos['y'], home_pos['z'])
    print('Sending land command...')
    req = roslibpy.ServiceRequest({
      'min_pitch': 0.0, 'yaw': 0.0,
      'latitude': float(self.global_fix['latitude']) if self._have_gps_fix() else 0.0,
      'longitude': float(self.global_fix['longitude']) if self._have_gps_fix() else 0.0,
      'altitude': 0.0,
    })
    resp = self.land_srv.call(req)
    if not resp.get('success', False):
      raise DroneError('Land command failed (response.success == False)')

    start = time.time()
    while self.state.get('armed') and time.time() - start < TIMEOUT:
      time.sleep(0.2)
    if self.state.get('armed'):
      raise DroneError('Vehicle did not disarm after landing timeout')
    print('Landed and disarmed')

  # ------------------------------------------------------------------
  # Status checking & mission orchestration (UNCHANGED)
  # ------------------------------------------------------------------
  def _check_status_ok(self):
    if not self.state:
      raise DroneError('No state from /mavros/state')
    if not self.state.get('connected'):
      raise DroneError('Lost connection to FCU (/mavros/state.connected == False)')
    status = self.state.get('system_status', 0)
    if status in (0, 3, 4):
      return
    raise DroneError(f'Unusual autopilot system_status: {status}')

  def run_mission(self):
    try:
      self.connect()
      self.ensure_armed()

      # With the new takeoff stage, this event is set when AUTO.LOITER@alt is reached
      reached = self._takeoff_reached_event.wait(timeout=TIMEOUT)
      if not reached:
        raise DroneError('Timeout waiting for takeoff altitude confirmation')

      # Triangle with 300 m edges (still uses OFFBOARD)
      self.fly_triangle_enu(edge_m=300.0)
      self.go_home_and_land()

    except DroneError as e:
      print(f'[ERROR] {e}')

    finally:
      print('Shutting down')
      try:
        self._stop_setpoint_stream()
        self._stop_status_loop()
        self.setpoint_pos_pub.unadvertise()
        self.state_sub.unsubscribe()
        self.pose_sub.unsubscribe()
        self.global_sub.unsubscribe()
        self.alt_sub.unsubscribe()
      except Exception:
        pass
      self.ros.terminate()


if __name__ == '__main__':
  import argparse
  parser = argparse.ArgumentParser(description='MAVROS rosbridge controller (PX4 OFFBOARD + commander-style takeoff)')
  parser.add_argument('--r2b_host', type=str, default='172.16.0.10',
                      help='Hostname/IP of rosbridge server (default: 172.16.0.10)')
  parser.add_argument('--r2b_port', type=int, default=9091,
                      help='Port of rosbridge server (default: 9091)')
  args = parser.parse_args()

  ctrl = MavrosBridgeController(host=args.r2b_host, port=args.r2b_port)
  ctrl.run_mission()
