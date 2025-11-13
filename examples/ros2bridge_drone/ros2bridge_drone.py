#!/usr/bin/env python3
import time
import math
import threading

import roslibpy


ARM_WAIT_SECONDS = 3.0         # Wait after connect before arming
TAKEOFF_ALTITUDE = 3.0         # Target takeoff altitude (m)
POSITION_TOLERANCE = 0.5       # Waypoint distance tolerance (m)
ALTITUDE_TOLERANCE = 0.3       # Altitude tolerance (m)
TIMEOUT = 60.0                 # Generic timeout for waits (s)


class DroneError(Exception):
    """Simple error type so we can bail cleanly."""
    pass


class MavrosBridgeController:
    """
    Example controller using roslibpy to talk to MAVROS over rosbridge.

    Assumes:
      - rosbridge_server is running (ws://host:port)
      - MAVROS (ROS 2) is running with:
          /mavros/state                   (mavros_msgs/State)
          /mavros/local_position/pose     (geometry_msgs/PoseStamped)
          /mavros/setpoint_position/local (geometry_msgs/PoseStamped)
          /mavros/cmd/arming              (mavros_msgs/CommandBool)
          /mavros/cmd/takeoff             (mavros_msgs/CommandTOL)
          /mavros/cmd/land                (mavros_msgs/CommandTOL)
      - MAVROS sys plugin node:
          node: /mavros/sys
          params: heartbeat_rate, heartbeat_mav_type
          service: /mavros/sys/set_parameters (rcl_interfaces/srv/SetParameters)
    """

    def __init__(self, host='172.16.0.10', port=9091):
        self.ros = roslibpy.Ros(host=host, port=port)

        self.state = None
        self.current_pose = None
        self.home_position = None

        # status thread control
        self._status_thread = None
        self._status_thread_stop = False

        # --- Topics ---
        self.state_sub = roslibpy.Topic(
            self.ros, '/mavros/state', 'mavros_msgs/State'
        )
        self.pose_sub = roslibpy.Topic(
            self.ros, '/mavros/local_position/pose', 'geometry_msgs/PoseStamped'
        )
        self.setpoint_pub = roslibpy.Topic(
            self.ros, '/mavros/setpoint_position/local', 'geometry_msgs/PoseStamped'
        )

        # --- Services (MAVROS) ---
        self.arm_srv = roslibpy.Service(
            self.ros, '/mavros/cmd/arming', 'mavros_msgs/CommandBool'
        )
        self.takeoff_srv = roslibpy.Service(
            self.ros, '/mavros/cmd/takeoff', 'mavros_msgs/CommandTOL'
        )
        self.land_srv = roslibpy.Service(
            self.ros, '/mavros/cmd/land', 'mavros_msgs/CommandTOL'
        )

        # --- ROS 2 parameter service on MAVROS sys plugin node ---
        # Node: /mavros/sys  →  /mavros/sys/set_parameters
        self.param_srv = roslibpy.Service(
            self.ros,
            '/mavros/sys/set_parameters',
            'rcl_interfaces/srv/SetParameters'
        )

    # ------------------------------------------------------------------
    # Connection & basic callbacks
    # ------------------------------------------------------------------
    def connect(self):
        # Start background rosbridge event loop and wait for connection.
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

        # Wait until we have state & pose and cache home
        self._wait_for_state()
        self._wait_for_pose()
        self._check_status_ok()

        # Treat the very first pose as "home"
        self.home_position = self.current_pose.copy()
        print('Got initial state and pose, home position set')
        print(f"Current FCU mode at connect: {self.state.get('mode')}")

        # We do NOT try to change mode here anymore.
        # Assume external system (you) already set GUIDED / OFFBOARD etc.

        # Start periodic status updates (once per second)
        self._start_status_loop()

    def _state_cb(self, msg):
        # message is a dict: {'connected': bool, 'armed': bool, 'mode': 'GUIDED', ...}
        self.state = msg

    def _pose_cb(self, msg):
        # message is a dict: {'pose': {'position': {x,y,z}, ...}, ...}
        self.current_pose = msg

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

    # ------------------------------------------------------------------
    # Periodic status updates (1 Hz)
    # ------------------------------------------------------------------
    def _start_status_loop(self):
        if self._status_thread is not None:
            return
        self._status_thread_stop = False
        self._status_thread = threading.Thread(
            target=self._status_loop, daemon=True
        )
        self._status_thread.start()

    def _stop_status_loop(self):
        self._status_thread_stop = True
        if self._status_thread is not None:
            self._status_thread.join(timeout=1.0)
        self._status_thread = None

    def _status_loop(self):
        """
        Prints status once per second:
          [STATUS] mode=GUIDED armed=True sys_status=4 pos=(x, y, z)
        """
        while not self._status_thread_stop and self.ros.is_connected:
            try:
                if self.state and self.current_pose:
                    pos = self.current_pose['pose']['position']
                    mode = self.state.get('mode')
                    armed = self.state.get('armed')
                    status = self.state.get('system_status')
                    print(
                        f"[STATUS] mode={mode} armed={armed} "
                        f"sys_status={status} "
                        f"pos=({pos['x']:.2f}, {pos['y']:.2f}, {pos['z']:.2f})"
                    )
                else:
                    print("[STATUS] waiting for telemetry (no state/pose yet)")
            except Exception as e:
                print(f"[STATUS] error while printing status: {e}")
            time.sleep(1.0)

    # ------------------------------------------------------------------
    # ROS 2 parameter setting (sys plugin heartbeat)
    # ------------------------------------------------------------------
    def _set_heartbeat_params(self):
        """
        Set ROS 2 parameters on MAVROS sys plugin node /mavros/sys:

          heartbeat_mav_type = "GCS"   (string)
          heartbeat_rate     = 2.0     (double)

        This is equivalent to:
          ros2 param set /mavros/sys heartbeat_mav_type GCS
          ros2 param set /mavros/sys heartbeat_rate 2.0
        """

        # ParameterType constants from rcl_interfaces/msg/ParameterType.msg
        PARAMETER_DOUBLE = 3
        PARAMETER_STRING = 4

        req = roslibpy.ServiceRequest({
            'parameters': [
                {
                    'name': 'heartbeat_mav_type',
                    'value': {
                        'type': PARAMETER_STRING,
                        'string_value': 'GCS'
                    }
                },
                {
                    'name': 'heartbeat_rate',
                    'value': {
                        'type': PARAMETER_DOUBLE,
                        'double_value': 2.0
                    }
                }
            ]
        })

        resp = self.param_srv.call(req)

        # rcl_interfaces/srv/SetParameters response:
        #   SetParametersResult[] results
        results = resp.get('results', [])
        if len(results) != 2:
            raise DroneError(
                f'Expected 2 SetParameters results, got {len(results)} – response: {resp}'
            )

        for param_name, result in zip(
            ['heartbeat_mav_type', 'heartbeat_rate'],
            results
        ):
            if not result.get('successful', False):
                reason = result.get('reason', 'no reason provided')
                raise DroneError(
                    f'Failed to set parameter {param_name}: {reason}'
                )

        print('MAVROS sys heartbeat params set: '
              'heartbeat_mav_type=GCS, heartbeat_rate=2.0 Hz')

    # ------------------------------------------------------------------
    # FCU arming, takeoff/land
    # ------------------------------------------------------------------
    def ensure_armed(self):
        self._wait_for_state()
        self._check_status_ok()

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

    def ensure_airborne(self, target_alt):
        self._wait_for_pose()
        self._check_status_ok()

        current_alt = self.current_pose['pose']['position']['z']
        if self.state.get('armed') and current_alt > 0.5:
            print('Already airborne (alt > 0.5 m), skipping takeoff')
            return

        print(f'Sending takeoff to {target_alt} m...')
        req = roslibpy.ServiceRequest({
            'min_pitch': 0.0,
            'yaw': 0.0,
            # For real hardware, use actual lat/lon
            'latitude': 0.0,
            'longitude': 0.0,
            'altitude': target_alt,
        })
        resp = self.takeoff_srv.call(req)
        if not resp.get('success', False):
            raise DroneError('Takeoff command failed (response.success == False)')

        self._wait_for_altitude(target_alt, ALTITUDE_TOLERANCE, timeout=TIMEOUT)

    def _wait_for_altitude(self, target, tol, timeout):
        start = time.time()
        while time.time() - start < timeout:
            self._check_status_ok()
            self._wait_for_pose()
            alt = self.current_pose['pose']['position']['z']
            if abs(alt - target) <= tol:
                print(f'Altitude reached: {alt:.2f} m')
                return
            time.sleep(0.1)
        raise DroneError('Timeout waiting for target altitude')

    def go_home_and_land(self):
        if not self.home_position:
            raise DroneError('Home position not set')

        home_pos = self.home_position['pose']['position']

        # Fly back above home at current altitude
        self.fly_to(home_pos['x'], home_pos['y'],
                    self.current_pose['pose']['position']['z'])

        print('Sending land command...')
        req = roslibpy.ServiceRequest({
            'min_pitch': 0.0,
            'yaw': 0.0,
            'latitude': 0.0,   # For real aircraft, use actual current lat/lon
            'longitude': 0.0,
            'altitude': 0.0,
        })
        resp = self.land_srv.call(req)
        if not resp.get('success', False):
            raise DroneError('Land command failed (response.success == False)')

        # Wait until disarmed
        start = time.time()
        while self.state.get('armed') and time.time() - start < TIMEOUT:
            time.sleep(0.5)

        if self.state.get('armed'):
            raise DroneError('Vehicle did not disarm after landing timeout')

        print('Landed and disarmed')

    # ------------------------------------------------------------------
    # Setpoint publishing & trajectory
    # ------------------------------------------------------------------
    def _distance_to(self, x, y, z):
        pose = self.current_pose['pose']['position']
        dx = pose['x'] - x
        dy = pose['y'] - y
        dz = pose['z'] - z
        return math.sqrt(dx * dx + dy * dy + dz * dz)

    def _publish_setpoint(self, x, y, z):
        # Simple PoseStamped in 'map' frame; adjust to your MAVROS frame if needed.
        msg = {
            'header': {'frame_id': 'map'},
            'pose': {
                'position': {'x': x, 'y': y, 'z': z},
                'orientation': {'x': 0.0, 'y': 0.0, 'z': 0.0, 'w': 1.0},
            },
        }
        self.setpoint_pub.publish(roslibpy.Message(msg))

    def fly_to(self, x, y, z, timeout=TIMEOUT):
        """
        Custom trajectory primitive:
        - Keep publishing a setpoint at ~10 Hz.
        - Poll local pose and stop when within POSITION_TOLERANCE.
        - Abort on any unusual FCU status.
        """
        self._wait_for_pose()
        print(f'Flying to ({x:.1f}, {y:.1f}, {z:.1f})')
        start = time.time()

        while time.time() - start < timeout:
            self._check_status_ok()
            self._publish_setpoint(x, y, z)

            dist = self._distance_to(x, y, z)
            if dist <= POSITION_TOLERANCE:
                print(f'Reached waypoint within {dist:.2f} m')
                return

            time.sleep(0.1)  # ~10 Hz

        raise DroneError('Timeout reaching waypoint')

    # ------------------------------------------------------------------
    # Status checking & mission orchestration
    # ------------------------------------------------------------------
    def _check_status_ok(self):
        """
        Check for "unusual" system status and connection problems.

        /mavros/state.system_status uses MAV_STATE_* enum.
        We'll treat:
          0 (UNINIT / unknown), 3 (STANDBY), 4 (ACTIVE)
        as "ok enough" for this example, and bail only on other values.
        """
        if not self.state:
            raise DroneError('No state from /mavros/state')
        if not self.state.get('connected'):
            raise DroneError('Lost connection to FCU (/mavros/state.connected == False)')

        status = self.state.get('system_status', 0)
        if status in (0, 3, 4):
            return

        raise DroneError(f'Unusual autopilot system_status: {status}')

    def run_mission(self):
        """
        High-level mission:
          1. Connect + configure + set ROS 2 heartbeat params + set home.
          2. Wait 3s then arm (skip if already armed).
          3. Take off (skip if armed & already airborne).
          4. Fly a small square.
          5. Return home, land, disarm.
          6. If anything odd happens, print error and return.
        """
        try:
            self.connect()

            # 1) Configure & arm (with 3s delay) unless already armed
            self.ensure_armed()

            # 2) Take off unless we detect we're already airborne
            self.ensure_airborne(TAKEOFF_ALTITUDE)

            # 3) Custom programmed trajectory
            start_pos = self.current_pose['pose']['position']
            waypoints = [
                # Move forward 2 m
                (start_pos['x'] + 2.0, start_pos['y'], TAKEOFF_ALTITUDE),
                # Move right 2 m
                (start_pos['x'] + 2.0, start_pos['y'] + 2.0, TAKEOFF_ALTITUDE),
                # Move back to align over home Y
                (start_pos['x'], start_pos['y'] + 2.0, TAKEOFF_ALTITUDE),
            ]

            for wp in waypoints:
                self.fly_to(*wp)

            # 4) Return to home, land and disarm
            self.go_home_and_land()

        except DroneError as e:
            print(f'[ERROR] {e}')

        finally:
            print('Shutting down')
            try:
                self._stop_status_loop()
                self.setpoint_pub.unadvertise()
                self.state_sub.unsubscribe()
                self.pose_sub.unsubscribe()
            except Exception:
                pass
            self.ros.terminate()


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='MAVROS rosbridge controller')
    parser.add_argument(
        '--r2b_host',
        type=str,
        default='172.16.0.10',
        help='Hostname/IP of rosbridge server (default: 172.16.0.10)'
    )
    parser.add_argument(
        '--r2b_port',
        type=int,
        default=9091,
        help='Port of rosbridge server (default: 9091)'
    )

    args = parser.parse_args()

    ctrl = MavrosBridgeController(host=args.r2b_host, port=args.r2b_port)
    ctrl.run_mission()
