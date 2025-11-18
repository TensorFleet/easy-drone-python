#!/usr/bin/env python3
import time
import math
import roslibpy


ALT_TARGET = 3.0          # m AGL
EDGE_M = 200.0            # waypoint distance from home
RADIUS = 2.0              # waypoint radius (m)
SLOW_RADIUS = 10.0        # start slowing here (m)
V_FAST = 20.0             # m/s far from target
V_MIN = 1.0               # m/s near target
ARM_WAIT = 3.0            # seconds
TAKEOFF_TIMEOUT = 60.0
LAND_TIMEOUT = 300.0
SETPOINT_HZ = 20.0        # OFFBOARD velocity stream


class DroneError(Exception):
    pass


class GuidedMissionController:
    """
    PX4 via MAVROS + rosbridge.
    NO mission, NO GUIDED, NO DO_REPOSITION.

    Uses:
      - AUTO.TAKEOFF -> AUTO.LOITER
      - OFFBOARD + /mavros/setpoint_velocity/cmd_vel for live “manual-style” control
      - AUTO.LAND (no RTL)
    """

    def __init__(self, host='172.16.0.10', port=9091):
        self.ros = roslibpy.Ros(host, port)

        self.state = None
        self.pose = None
        self.fix = None
        self.alt_msg = None
        self.home = None
        self.home_fix = None

        # subs
        self.state_sub = roslibpy.Topic(self.ros, '/mavros/state', 'mavros_msgs/State')
        self.pose_sub = roslibpy.Topic(self.ros, '/mavros/local_position/pose', 'geometry_msgs/PoseStamped')
        self.fix_sub = roslibpy.Topic(self.ros, '/mavros/global_position/global', 'sensor_msgs/NavSatFix')
        self.alt_sub = roslibpy.Topic(self.ros, '/mavros/altitude', 'mavros_msgs/Altitude')

        # pubs
        self.vel_pub = roslibpy.Topic(
            self.ros, '/mavros/setpoint_velocity/cmd_vel', 'geometry_msgs/TwistStamped'
        )

        # srvs
        self.mode_srv = roslibpy.Service(self.ros, '/mavros/set_mode', 'mavros_msgs/SetMode')
        self.arm_srv = roslibpy.Service(self.ros, '/mavros/cmd/arming', 'mavros_msgs/CommandBool')
        self.cmd_long_srv = roslibpy.Service(self.ros, '/mavros/cmd/command', 'mavros_msgs/CommandLong')
        self.param_srv = roslibpy.Service(self.ros, '/mavros/sys/set_parameters', 'rcl_interfaces/srv/SetParameters')
        self.sim_srv = roslibpy.Service(self.ros, '/simulation_manager/start_simulation', 'std_srvs/Trigger')

    # ----------------- callbacks -----------------
    def _cb_state(self, msg):
        self.state = msg

    def _cb_pose(self, msg):
        self.pose = msg

    def _cb_fix(self, msg):
        self.fix = msg

    def _cb_alt(self, msg):
        self.alt_msg = msg

    # ----------------- connection & setup -----------------
    def connect(self):
        print('[SYS] Connecting to rosbridge…')
        self.ros.run()
        t0 = time.time()
        while not self.ros.is_connected:
            if time.time() - t0 > 10.0:
                raise DroneError('rosbridge connection timeout')
            time.sleep(0.05)
        print('[SYS] Connected to rosbridge')

        self.state_sub.subscribe(self._cb_state)
        self.pose_sub.subscribe(self._cb_pose)
        self.fix_sub.subscribe(self._cb_fix)
        self.alt_sub.subscribe(self._cb_alt)

        # heartbeat params
        self._set_heartbeat_params()

        # wait for initial telemetry
        self._wait_state()
        self._wait_pose()
        self._wait_fix()
        print(f"[SYS] Initial FCU mode: {self.state.get('mode')}")

        # optional sim restart
        self._restart_sim_if_available()

        # fresh telemetry after sim restart
        self.state = None
        self.pose = None
        self.fix = None
        self.alt_msg = None
        self._wait_state()
        self._wait_pose()
        self._wait_fix()

        self.home = self.pose['pose']['position'].copy()
        self.home_fix = self.fix.copy()
        print(f"[SYS] Home local: x={self.home['x']:.2f}, y={self.home['y']:.2f}, z={self.home['z']:.2f}")
        print(f"[SYS] Home GPS : lat={self.home_fix['latitude']:.7f}, lon={self.home_fix['longitude']:.7f}")

    def _wait_state(self):
        while self.state is None:
            print('[WAIT] /mavros/state…')
            time.sleep(0.1)

    def _wait_pose(self):
        while self.pose is None:
            print('[WAIT] /mavros/local_position/pose…')
            time.sleep(0.1)

    def _wait_fix(self):
        while not (self.fix and isinstance(self.fix.get('latitude'), (float, int))):
            print('[WAIT] /mavros/global_position/global…')
            time.sleep(0.2)

    def _set_heartbeat_params(self):
        print('[SYS] Setting MAVROS heartbeat params…')
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
        try:
            resp = self.param_srv.call(req)
            print('[SYS] Heartbeat param response:', resp.get('results', []))
        except Exception as e:
            print('[SYS][WARN] Heartbeat param set failed:', e)

    def _restart_sim_if_available(self):
        print('[SIM] Requesting simulation restart…')
        try:
            resp = self.sim_srv.call(roslibpy.ServiceRequest({}), timeout=20.0)
            print(f"[SIM] success={resp.get('success', False)} msg={resp.get('message','')}")
        except Exception as e:
            print('[SIM][WARN] restart failed or service missing:', e)

    # ----------------- mode / arming / takeoff -----------------
    def _set_mode(self, custom_mode):
        print(f'[MODE] Setting mode: {custom_mode}')
        resp = self.mode_srv.call({'base_mode': 0, 'custom_mode': custom_mode})
        if not resp.get('mode_sent', False):
            print(f'[MODE][WARN] mode_sent=False for {custom_mode}')
            return False
        t0 = time.time()
        while time.time() - t0 < 5.0:
            m = (self.state.get('mode') or '').upper()
            if m == custom_mode.upper():
                print(f'[MODE] Mode is now {m}')
                return True
            time.sleep(0.1)
        print(f'[MODE][WARN] Mode did not switch to {custom_mode}, current={self.state.get("mode")}')
        return False

    def _arm(self):
        print(f'[ARM] Waiting {ARM_WAIT:.1f}s before arming…')
        time.sleep(ARM_WAIT)
        print('[ARM] Sending arm command…')
        resp = self.arm_srv.call({'value': True})
        if not resp.get('success', False):
            raise DroneError('Arming command rejected')
        t0 = time.time()
        while not self.state.get('armed', False):
            if time.time() - t0 > 7.0:
                raise DroneError('Vehicle did not arm in time')
            time.sleep(0.1)
        print('[ARM] Vehicle armed')

    def _relative_alt(self):
        if self.alt_msg and 'relative' in self.alt_msg:
            try:
                return float(self.alt_msg['relative'])
            except Exception:
                pass
        z = float(self.pose['pose']['position']['z'])
        return abs(z - float(self.home['z']))

    def _takeoff_to_alt(self, alt):
        print(f'[TKOFF] Sending MAV_CMD_NAV_TAKEOFF to {alt:.2f} m AGL')
        lat = float(self.fix['latitude'])
        lon = float(self.fix['longitude'])
        req = {
            'command': 22,      # MAV_CMD_NAV_TAKEOFF
            'confirmation': 0,
            'param1': 0.0,
            'param2': 0.0,
            'param3': 0.0,
            'param4': 0.0,
            'param5': lat,
            'param6': lon,
            'param7': float(alt)
        }
        resp = self.cmd_long_srv.call(req)
        if not resp.get('success', False):
            raise DroneError(f'NAV_TAKEOFF rejected (result={resp.get("result")})')
        print('[TKOFF] Command accepted, waiting for AUTO.LOITER @ altitude…')
        t0 = time.time()
        while True:
            mode = (self.state.get('mode') or '').upper()
            rel = self._relative_alt()
            print(f'[TKOFF] mode={mode} rel_alt={rel:.2f}')
            if mode == 'AUTO.LOITER' and abs(rel - alt) < 0.4:
                print('[TKOFF] Takeoff complete, in AUTO.LOITER near target alt')
                return
            if time.time() - t0 > TAKEOFF_TIMEOUT:
                raise DroneError('Timeout waiting for AUTO.LOITER at altitude')
            if not self.state.get('armed', True):
                raise DroneError('Vehicle disarmed during takeoff')
            time.sleep(0.2)

    # ----------------- OFFBOARD velocity control -----------------
    def _publish_velocity(self, vx, vy, vz=0.0):
        msg = {
            'header': {'frame_id': 'map'},
            'twist': {
                'linear': {'x': float(vx), 'y': float(vy), 'z': float(vz)},
                'angular': {'x': 0.0, 'y': 0.0, 'z': 0.0}
            }
        }
        self.vel_pub.publish(roslibpy.Message(msg))

    def _ensure_offboard(self):
        print('[OFFB] Pre-streaming zero velocities…')
        t_end = time.time() + 1.5
        while time.time() < t_end:
            self._publish_velocity(0.0, 0.0, 0.0)
            time.sleep(1.0 / SETPOINT_HZ)

        print('[OFFB] Switching to OFFBOARD…')
        if not self._set_mode('OFFBOARD'):
            raise DroneError('Failed to enter OFFBOARD mode')

    def _goto_local_enu(self, tx, ty, label=''):
        """
        Live velocity control in OFFBOARD.
        vx,vy are in local ENU (map frame).
        """
        print(f'[LEG] {label}: target local ENU ({tx:.1f}, {ty:.1f})')
        t0 = time.time()
        while True:
            p = self.pose['pose']['position']
            cx = float(p['x'])
            cy = float(p['y'])
            dx = tx - cx
            dy = ty - cy
            dist = math.hypot(dx, dy)
            rel_alt = self._relative_alt()
            print(f'[LEG] {label}: dist={dist:.2f} m, pos=({cx:.2f},{cy:.2f}), alt={rel_alt:.2f}')

            if dist < RADIUS:
                print(f'[LEG] {label}: within radius, leg complete')
                self._publish_velocity(0.0, 0.0, 0.0)
                return

            if time.time() - t0 > LAND_TIMEOUT:
                raise DroneError(f'[LEG] {label}: timeout reaching target')

            # horizontal speed
            if dist > SLOW_RADIUS:
                v = V_FAST
            else:
                v = max(V_MIN, V_FAST * (dist / SLOW_RADIUS))

            vx = (dx / dist) * v
            vy = (dy / dist) * v

            # simple altitude nudging (ENU: +Z up)
            alt_err = ALT_TARGET - rel_alt
            if abs(alt_err) < 0.2:
                vz = 0.0
            else:
                vz = max(-1.0, min(1.0, alt_err))  # clamp climb/descend

            self._publish_velocity(vx, vy, vz)
            time.sleep(1.0 / SETPOINT_HZ)

    # ----------------- LAND / shutdown -----------------
    def _land_and_wait_disarm(self):
        print('[LAND] Stopping OFFBOARD velocities before landing')
        # send zeros for a short time so no climb/descent is commanded
        for _ in range(int(0.5 * SETPOINT_HZ)):
            self._publish_velocity(0.0, 0.0, 0.0)
            time.sleep(1.0 / SETPOINT_HZ)

        # leave OFFBOARD first
        print('[LAND] Leaving OFFBOARD to AUTO.LOITER')
        self._set_mode('AUTO.LOITER')
        time.sleep(0.5)

        print('[LAND] Setting AUTO.LAND')
        ok = self._set_mode('AUTO.LAND')
        if not ok:
            print('[LAND][WARN] AUTO.LAND not confirmed, still waiting for disarm…')

        t0 = time.time()
        while time.time() - t0 < LAND_TIMEOUT:
            armed = self.state.get('armed', False)
            mode = self.state.get('mode')
            print(f'[LAND] mode={mode} armed={armed}')
            if not armed:
                print('[LAND] Vehicle disarmed, landing complete')
                return
            time.sleep(1.0)
        print('[LAND][WARN] Disarm not observed within timeout')

    # ----------------- mission orchestration -----------------
    def run_mission(self):
        try:
            self.connect()

            # ensure AUTO.LOITER (start mode)

            self._arm()
            self._takeoff_to_alt(ALT_TARGET)

            # OFFBOARD for live velocity control
            self._ensure_offboard()

            # two ENU points 200 m away from home
            hx = float(self.home['x'])
            hy = float(self.home['y'])
            wp1 = (hx + EDGE_M, hy)
            wp2 = (hx + EDGE_M, hy + EDGE_M)

            self._goto_local_enu(wp1[0], wp1[1], label='WP1')
            self._goto_local_enu(wp2[0], wp2[1], label='WP2')

            # just land + disarm
            self._land_and_wait_disarm()

        except DroneError as e:
            print(f'[ERROR] {e}')
        finally:
            print('[SYS] Shutting down')
            try:
                self.vel_pub.unadvertise()
                self.state_sub.unsubscribe()
                self.pose_sub.unsubscribe()
                self.fix_sub.unsubscribe()
                self.alt_sub.unsubscribe()
            except Exception:
                pass
            self.ros.terminate()


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(
        description='PX4 OFFBOARD velocity demo via MAVROS rosbridge (2 waypoints + land)'
    )
    parser.add_argument('--r2b_host', type=str, default='172.16.0.10',
                        help='Hostname/IP of rosbridge server (default: 172.16.0.10)')
    parser.add_argument('--r2b_port', type=int, default=9091,
                        help='Port of rosbridge server (default: 9091)')
    args = parser.parse_args()

    ctrl = GuidedMissionController(host=args.r2b_host, port=args.r2b_port)
    ctrl.run_mission()
