#!/usr/bin/env python3
import time
import math
import threading

import roslibpy


ARM_WAIT_SECONDS = 3.0          # Wait after connect before arming
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

    Pubs:
      /mavros/setpoint_raw/local      (mavros_msgs/PositionTarget)

    Srvs:
      /mavros/cmd/arming              (mavros_msgs/CommandBool)
      /mavros/cmd/takeoff             (mavros_msgs/CommandTOL)
      /mavros/cmd/land                (mavros_msgs/CommandTOL)
      /mavros/cmd/command             (mavros_msgs/CommandLong)
      /mavros/set_mode                (mavros_msgs/SetMode)
      /mavros/sys/set_parameters      (rcl_interfaces/srv/SetParameters)
      /mavros/param/set               (mavros_msgs/ParamSetV2)

    Notes:
      * We now do the PX4 OFFBOARD handshake correctly (pre-stream setpoints, then set OFFBOARD).
      * AGL is |z - home_z| (sign-agnostic).
      * Battery/power arming checks are disabled for SITL, then FCU is rebooted before flight.
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

        # --- Topics (subscribers) ---
        self.state_sub = roslibpy.Topic(self.ros, '/mavros/state', 'mavros_msgs/State')
        self.pose_sub = roslibpy.Topic(self.ros, '/mavros/local_position/pose', 'geometry_msgs/PoseStamped')
        self.global_sub = roslibpy.Topic(self.ros, '/mavros/global_position/global', 'sensor_msgs/NavSatFix')

        # --- Topics (publishers) ---
        self.setpoint_raw_pub = roslibpy.Topic(self.ros, '/mavros/setpoint_raw/local', 'mavros_msgs/PositionTarget')

        # --- Services (MAVROS) ---
        self.arm_srv = roslibpy.Service(self.ros, '/mavros/cmd/arming', 'mavros_msgs/CommandBool')
        self.takeoff_srv = roslibpy.Service(self.ros, '/mavros/cmd/takeoff', 'mavros_msgs/CommandTOL')
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
            time.sleep(0.1)
        print('Connected to rosbridge')

        # Wait 1 second before doing anything else
        time.sleep(1.0)

        # Set ROS 2 params on mavros sys plugin via /mavros/sys/set_parameters
        self._set_heartbeat_params()

        # Subscribe to MAVROS topics
        self.state_sub.subscribe(self._state_cb)
        self.pose_sub.subscribe(self._pose_cb)
        self.global_sub.subscribe(self._global_cb)

        # Wait until we have state & pose so we can talk to FCU
        self._wait_for_state()
        self._wait_for_pose()

        # Disable PX4 battery/power arming checks and reboot FCU (SITL intent)
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

        # Start periodic status updates (once per second)
        self._start_status_loop()

    def _state_cb(self, msg): self.state = msg
    def _pose_cb(self, msg): self.current_pose = msg
    def _global_cb(self, msg): self.global_fix = msg

    def _wait_for_state(self, timeout=5.0):
        start = time.time()
        while self.state is None:
            if time.time() - start > timeout:
                raise DroneError('No /mavros/state received')
            time.sleep(0.05)

    def _wait_for_pose(self, timeout=5.0):
        start = time.time()
        while self.current_pose is None:
            if time.time() - start > timeout:
                raise DroneError('No /mavros/local_position/pose received')
            time.sleep(0.05)

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
    # Altitude helper (sign-agnostic): AGL = |z - home_z|
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
    # PX4 battery/power checks disabling + reboot (SITL)
    # ------------------------------------------------------------------
    def _disable_battery_checks_and_reboot(self):
        # Param types for rcl_interfaces/ParameterValue inside ParamSetV2
        PARAMETER_INTEGER = 2
        PARAMETER_DOUBLE = 3

        # Set CBRK_SUPPLY_CHK (requires reboot to take effect)
        req1 = roslibpy.ServiceRequest({
            'force_set': True,
            'param_id': 'CBRK_SUPPLY_CHK',
            'value': {'type': PARAMETER_INTEGER, 'integer_value': 894281}
        })
        r1 = self.param_set_srv.call(req1)
        if not r1.get('success', True):
            print('[DEV][WARN] Failed to set CBRK_SUPPLY_CHK:', r1)

        # Set COM_ARM_BAT_MIN=0.0 to avoid arming gate on % battery
        req2 = roslibpy.ServiceRequest({
            'force_set': True,
            'param_id': 'COM_ARM_BAT_MIN',
            'value': {'type': PARAMETER_DOUBLE, 'double_value': 0.0}
        })
        r2 = self.param_set_srv.call(req2)
        if not r2.get('success', True):
            print('[DEV][WARN] Failed to set COM_ARM_BAT_MIN:', r2)

        # Reboot FCU
        reboot_req = roslibpy.ServiceRequest({
            'command': 246,  # MAV_CMD_PREFLIGHT_REBOOT_SHUTDOWN
            'confirmation': 0,
            'param1': 1.0, 'param2': 0.0, 'param3': 0.0, 'param4': 0.0,
            'param5': 0.0, 'param6': 0.0, 'param7': 0.0
        })
        _ = self.cmd_long_srv.call(reboot_req)

        # Wait for FCU disconnect -> reconnect
        self._wait_for_fcu_cycle()

    def _wait_for_fcu_cycle(self, disconnect_timeout=10.0, reconnect_timeout=30.0):
        t0 = time.time()
        while self.state and self.state.get('connected', True):
            if time.time() - t0 > disconnect_timeout:
                print('[DEV][WARN] Did not observe FCU disconnect; continuing to wait for reconnect...')
                break
            time.sleep(0.1)

        t1 = time.time()
        while (not self.state) or (not self.state.get('connected', False)):
            if time.time() - t1 > reconnect_timeout:
                raise DroneError('Timeout waiting for FCU to reconnect after reboot')
            time.sleep(0.1)

        time.sleep(1.0)

    # ------------------------------------------------------------------
    # FCU arming, offboard, takeoff/land
    # ------------------------------------------------------------------
    def ensure_armed(self):
        self._wait_for_state()
        if self.state.get('armed'):
            print('Already armed, skipping arming step')
            return

        print(f'Waiting {ARM_WAIT_SECONDS}s before arming...')
        time.sleep(ARM_WAIT_SECONDS)

        print('Sending arm command...')
        req = roslibpy.ServiceRequest({'value': True})
        resp = self.arm_srv.call(req)
        if not resp.get('success', False):
            raise DroneError('Arming command failed (response.success == False)')

        start = time.time()
        while not self.state.get('armed') and time.time() - start < 10.0:
            time.sleep(0.1)
        if not self.state.get('armed'):
            raise DroneError('Vehicle did not arm within timeout')
        print('Vehicle armed')

    def ensure_offboard(self, retries=3, prestream_seconds=1.5):
        """
        PX4 OFFBOARD handshake:
          - stream position setpoints >2 Hz for a short period
          - set mode OFFBOARD
          - verify state.mode == 'OFFBOARD'
        """
        self._wait_for_pose()

        for attempt in range(1, retries + 1):
            # Pre-stream current position so mode switch is accepted
            pos = self.current_pose['pose']['position']
            x, y, z = pos['x'], pos['y'], pos['z']
            t_end = time.time() + prestream_seconds
            while time.time() < t_end:
                self._publish_position_target(x, y, z)
                time.sleep(1.0 / SETPOINT_HZ)

            print(f'Setting mode: OFFBOARD (attempt {attempt}/{retries})')
            req = roslibpy.ServiceRequest({'base_mode': 0, 'custom_mode': 'OFFBOARD'})
            resp = self.mode_srv.call(req)
            if not resp.get('mode_sent', False):
                print('[WARN] FCU rejected OFFBOARD (mode_sent=False)')
                continue

            # Wait for state to report OFFBOARD
            start = time.time()
            while (self.state is None or (self.state.get('mode') or '').upper() != 'OFFBOARD') \
                    and time.time() - start < 3.0:
                # keep streaming during wait
                self._publish_position_target(x, y, z)
                time.sleep(1.0 / SETPOINT_HZ)

            if (self.state.get('mode') or '').upper() == 'OFFBOARD':
                print('Mode is now OFFBOARD')
                return

            print('[WARN] Mode did not switch to OFFBOARD')

        raise DroneError('Unable to enter OFFBOARD after retries')

    def ensure_airborne(self, target_alt):
        self._wait_for_pose()

        current_agl = self._get_agl()
        if self.state.get('armed') and current_agl > 0.5:
            print(f'Already airborne (agl {current_agl:.2f} m), skipping takeoff')
            return

        if self._have_gps_fix():
            lat = float(self.global_fix['latitude'])
            lon = float(self.global_fix['longitude'])
            print(f'Sending takeoff to {target_alt} m via /mavros/cmd/takeoff (lat={lat:.7f}, lon={lon:.7f})...')
            req = roslibpy.ServiceRequest({
                'min_pitch': 0.0,
                'yaw': 0.0,
                'latitude': lat,
                'longitude': lon,
                'altitude': float(target_alt),
            })
            _ = self.takeoff_srv.call(req)
        else:
            print('[WARN] No GNSS fix. cmd/takeoff may be ignored. Will try fallback if AGL does not increase.')

        if self._wait_for_agl_change(min_increase=0.5, timeout=8.0):
            self._wait_for_agl(target_alt, ALTITUDE_TOLERANCE, timeout=TIMEOUT, abort_on_disarm=True)
            return

        # Fallback climb using local setpoints requires OFFBOARD
        raise DroneError('Takeoff did not start and no GNSS; use takeoff-enabled mode or provide GNSS.')

    def _wait_for_agl_change(self, min_increase=0.5, timeout=8.0):
        start_agl = self._get_agl()
        start_time = time.time()
        while time.time() - start_time < timeout:
            if not self.state.get('armed', False):
                raise DroneError(f'Takeoff aborted: vehicle disarmed at agl {self._get_agl():.2f} m')
            agl = self._get_agl()
            if agl - start_agl >= min_increase:
                return True
            time.sleep(0.1)
        return False

    def _wait_for_agl(self, target, tol, timeout, abort_on_disarm=False):
        start = time.time()
        last_agl = self._get_agl()
        while time.time() - start < timeout:
            agl = self._get_agl()
            if abs(agl - target) <= tol:
                print(f'Altitude reached: agl {agl:.2f} m (target {target:.2f} m)')
                return
            if abort_on_disarm and not self.state.get('armed', False):
                raise DroneError(f'Takeoff aborted: vehicle disarmed at agl {agl:.2f} m (target {target:.2f} m)')
            last_agl = agl
            time.sleep(0.1)
        raise DroneError(f'Timeout waiting for target AGL {target:.2f} m (last agl {last_agl:.2f} m)')

    def go_home_and_land(self):
        if not self.home_position:
            raise DroneError('Home position not set')
        home_pos = self.home_position['pose']['position']
        current_z = self.current_pose['pose']['position']['z']
        self.fly_to_raw(home_pos['x'], home_pos['y'], current_z)

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
            time.sleep(0.5)
        if self.state.get('armed'):
            raise DroneError('Vehicle did not disarm after landing timeout')
        print('Landed and disarmed')

    # ------------------------------------------------------------------
    # Setpoint publishing (PositionTarget)
    # ------------------------------------------------------------------
    def _publish_position_target(self, x, y, z, yaw=None):
        # mavros_msgs/PositionTarget (position-only)
        IGNORE_VX = 1 << 3; IGNORE_VY = 1 << 4; IGNORE_VZ = 1 << 5
        IGNORE_AX = 1 << 6; IGNORE_AY = 1 << 7; IGNORE_AZ = 1 << 8
        IGNORE_YAW = 1 << 10; IGNORE_YAWR = 1 << 11
        type_mask = (IGNORE_VX | IGNORE_VY | IGNORE_VZ |
                     IGNORE_AX | IGNORE_AY | IGNORE_AZ |
                     IGNORE_YAW | IGNORE_YAWR)

        msg = {
            'header': {'frame_id': 'map'},
            'coordinate_frame': 1,           # MAV_FRAME_LOCAL_NED (MAVROS handles ENU/NED)
            'type_mask': type_mask,          # position only
            'position': {'x': x, 'y': y, 'z': z},
            'velocity': {'x': 0.0, 'y': 0.0, 'z': 0.0},
            'acceleration_or_force': {'x': 0.0, 'y': 0.0, 'z': 0.0},
            'yaw': 0.0 if yaw is None else float(yaw),
            'yaw_rate': 0.0
        }
        self.setpoint_raw_pub.publish(roslibpy.Message(msg))

    # ------------------------------------------------------------------
    # Goto primitive (raw) with OFFBOARD enforcement & acceptance checks
    # ------------------------------------------------------------------
    def fly_to_raw(self, x, y, z, timeout=TIMEOUT):
        self._wait_for_pose()

        # Ensure OFFBOARD (PX4 requirement) before trying to move
        if (self.state.get('mode') or '').upper() not in SETPOINT_ACCEPT_MODES:
            self.ensure_offboard()

        print(f'Flying to ({x:.1f}, {y:.1f}, {z:.1f}) via PositionTarget')
        start = time.time()

        def dist():
            pose = self.current_pose['pose']['position']
            dx = pose['x'] - x
            dy = pose['y'] - y
            dz = pose['z'] - z
            return math.sqrt(dx*dx + dy*dy + dz*dz)

        d0 = dist()
        last_better = time.time()

        while time.time() - start < timeout:
            # Keep OFFBOARD alive and command the target
            self._publish_position_target(x, y, z)

            d = dist()
            if d < d0 - 0.5:
                last_better = time.time()
                d0 = d

            if d <= POSITION_TOLERANCE:
                print(f'Reached waypoint within {d:.2f} m')
                return

            # If PX4 dropped out of OFFBOARD (e.g., timeout), try to re-enter once
            if (self.state.get('mode') or '').upper() != 'OFFBOARD':
                print('[WARN] Dropped out of OFFBOARD; attempting re-entry...')
                self.ensure_offboard()

            # If after 3s we haven’t improved by at least 0.5 m, assume setpoints are ignored
            if time.time() - last_better > 3.0:
                raise DroneError('Setpoints appear to be ignored (no progress). '
                                 'Check OFFBOARD, EKF position, and that no mission/loiter conflicts.')

            time.sleep(1.0 / SETPOINT_HZ)

        raise DroneError('Timeout reaching waypoint')

    # ------------------------------------------------------------------
    # Triangle path (300 m edges) in local ENU
    # ------------------------------------------------------------------
    def fly_triangle_enu(self, edge_m=300.0):
        self._wait_for_pose()
        start_pos = self.current_pose['pose']['position']
        x0, y0, zf = start_pos['x'], start_pos['y'], start_pos['z']

        # Equilateral triangle: A(start)->B(east)->C(60deg)->A
        Bx = x0 + edge_m
        By = y0
        Cx = Bx + edge_m * 0.5
        Cy = By + edge_m * (math.sqrt(3.0) / 2.0)

        waypoints = [(Bx, By, zf), (Cx, Cy, zf), (x0, y0, zf)]
        for (x, y, z) in waypoints:
            self.fly_to_raw(x, y, z)

    # ------------------------------------------------------------------
    # Status checking & mission orchestration
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
            self.ensure_airborne(TAKEOFF_ALTITUDE)
            # Required for PX4 to accept external setpoints:
            self.ensure_offboard()
            # Triangle with 300 m edges
            self.fly_triangle_enu(edge_m=300.0)
            self.go_home_and_land()

        except DroneError as e:
            print(f'[ERROR] {e}')

        finally:
            print('Shutting down')
            try:
                self._stop_status_loop()
                self.setpoint_raw_pub.unadvertise()
                self.state_sub.unsubscribe()
                self.pose_sub.unsubscribe()
                self.global_sub.unsubscribe()
            except Exception:
                pass
            self.ros.terminate()


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='MAVROS rosbridge controller (PX4 OFFBOARD)')
    parser.add_argument('--r2b_host', type=str, default='172.16.0.10',
                        help='Hostname/IP of rosbridge server (default: 172.16.0.10)')
    parser.add_argument('--r2b_port', type=int, default=9091,
                        help='Port of rosbridge server (default: 9091)')
    args = parser.parse_args()

    ctrl = MavrosBridgeController(host=args.r2b_host, port=args.r2b_port)
    ctrl.run_mission()
