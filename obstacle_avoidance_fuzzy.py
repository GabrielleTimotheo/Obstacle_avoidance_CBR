#!/usr/bin/env python3
import rospy
from mavros_msgs.msg import State, GlobalPositionTarget, WaypointList, HomePosition, PositionTarget
from mavros_msgs.srv import SetMode, WaypointSetCurrent, CommandTOL
from sensor_msgs.msg import NavSatFix, LaserScan
from std_msgs.msg import Float64, Header
from sensor_msgs.msg import LaserScan
from geometry_msgs.msg import TwistStamped
from visualization_msgs.msg import MarkerArray, Marker
import numpy as np
from time import time
from collision_lib import *
from frame_convertions import *
from log_debug import *
from tf.transformations import euler_from_quaternion
from nav_msgs.msg import Odometry
import fuzzy_cbr
import cbr

class ObstacleAvoidance:
    ############################################################################
    # region CONSTRUCTOR
    ############################################################################
    def __init__(self) -> None:
        rospy.init_node("obstacle_avoidance_node", anonymous=False)

        # Control the time when we last sent a guided point
        self.last_command_time = time()
        # Variables
        self.current_yaw = 0.0  # [RAD]
        self.current_location = None  # GPS data
        self.current_state = State()  # vehicle driving mode
        self.debug_mode = True  # debug mode to print more information
        self.home_waypoint = None  # home waypoint data, contains home lat and lon
        self.waypoints_list = None  # list of waypoints in the autonomous mission
        self.current_waypoint_index = -1  # autonomous mission waypoint we are tracking
        self.current_target = None  # target waypoint data in AUTO mode
        self.previous_guided_point_angle = None  # [RAD]

        # Parameters from obstacle avoidance algorithm
        self.dt = 0.17  # Time step [s]
        self.closest_obstacle_distance = 0
        self.x = 0  # Actual x position from odometry
        self.y = 0  # Actual y position from odometry
        self.theta = 0  # Actual orientation from odometry
        self.v = 0  # Actual linear velocity from odometry
        self.w = 0  # Actual angular velocity from odometry
        self.max_v = 2.55  # Maximum linear velocity 2.55
        self.max_w = np.pi  # Maximum angular velocity np.pi/2
        self.best_v = None  # Best linear velocity
        self.best_w = None  # Best angular velocity
        self.min_v = 0.0  # Minimum linear velocity
        self.max_acc_v = 0.9 #0.5  # Maximum linear acceleration 0.5
        self.max_acc_w = np.pi/2  # Maximum angular acceleration
        self.safety_distance_to_start = 6.0  # [meters] 5
        self.valid_ranges = None  # Lidar valid ranges
        self.next_waypoint_dist = 3.5  # [meters] 3
        self.lidar_subdivisions = []  # Subdivion of lidar field of view
        self.actual_lidar_subdivisions = []  # Actual lidar subdivisions values
        self.min_dist_lidar_subdivisions = []  # Minimum distance of lidar subdivisions
        self.waypoints_reached = 0  # Waypoints reached counter

        self.v_reso = 12  # Linear velocity resolution 25
        self.w_reso = 12  # Angular velocity resolution 25

        self.alpha = 0  # Robot alignment to the objective
        self.beta = 0  # Distance to the obstacle
        self.gamma = 0  # Foward speed

        self.angle_min = -2.268889904022217
        self.angle_max = 2.268899917602539
        self.goal_angle = 0

        # CBR parameters
        self.cbr = cbr.CBR()
        self.scenario = None

        # Fuzzy parameters
        self.fuzzy = fuzzy_cbr.Fuzzy()

        # Subscribers to mavros and laserscan messages
        running_on_rover = False
        if running_on_rover:
            rospy.Subscriber("/livox/scan", LaserScan,
                             self.laserScanCallback, queue_size=1)
        else:
            rospy.Subscriber("/mavros/lidar", LaserScan,
                             self.laserScanCallback, queue_size=1)
        rospy.Subscriber("/mavros/state", State,
                         self.stateCallback, queue_size=1)
        rospy.Subscriber("/mavros/global_position/global",
                         NavSatFix, self.gpsCallback, queue_size=1)
        rospy.Subscriber("/mavros/global_position/compass_hdg",
                         Float64, self.compassCallback, queue_size=1)
        rospy.Subscriber("/mavros/setpoint_raw/target_global",
                         GlobalPositionTarget, self.currentTargetCallback, queue_size=1)
        rospy.Subscriber("/mavros/mission/waypoints",
                         WaypointList, self.missionWaypointsCallback, queue_size=1)
        rospy.Subscriber("/mavros/home_position/home",
                         HomePosition, self.homePositionCallback, queue_size=1)
        rospy.Subscriber('/mavros/local_position/odom',
                         Odometry, self.odomCallback)

        # Publishers
        self.setpoint_global_pub = rospy.Publisher(
            '/mavros/setpoint_raw/global', GlobalPositionTarget, queue_size=1)
        self.setpoint_local_pub = rospy.Publisher(
            '/mavros/setpoint_raw/local', PositionTarget, queue_size=1)
        self.obstacles_pub = rospy.Publisher(
            '/obstacle_avoidance/obstacles', MarkerArray, queue_size=1)
        self.goal_guided_point_pub = rospy.Publisher(
            '/obstacle_avoidance/goal_guided_point', MarkerArray, queue_size=1)
        self.robot_path_area_pub = rospy.Publisher(
            '/obstacle_avoidance/robot_path_area', Marker, queue_size=1)

        # Services
        rospy.wait_for_service('/mavros/set_mode')
        rospy.wait_for_service('/mavros/mission/set_current')
        rospy.wait_for_service('/mavros/cmd/command')
        self.set_mode_service = rospy.ServiceProxy('/mavros/set_mode', SetMode)
        self.set_current_wp_srv = rospy.ServiceProxy(
            '/mavros/mission/set_current', WaypointSetCurrent)
        self.command_tol_srv = rospy.ServiceProxy(
            '/mavros/cmd/command', CommandTOL)

        rospy.loginfo("Obstacle avoidance node initialized.")
        rospy.spin()

    # endregion
    ############################################################################
    # region MAVLINK CALLBACKS
    ############################################################################

    def odomCallback(self, msg: Odometry) -> None:
        """Receive odometry data and update robot position and orientation. 

        Args:
            msg (Odometry): Odometry message from mavros
        """
        position = msg.pose.pose.position
        orientation = msg.pose.pose.orientation
        self.x = position.x  # [meters]
        self.y = position.y  # [meters]
        orientation_list = [orientation.x,
                            orientation.y, orientation.z, orientation.w]
        # Converte quaternionic orientation representation into Euler angles (X,Y,Z)
        _, _, self.theta = euler_from_quaternion(orientation_list)  # [rad]
        self.v = msg.twist.twist.linear.x  # [m/s]
        self.w = msg.twist.twist.angular.z  # [rad/s]

        current_time = msg.header.stamp.to_sec()

        # rospy.loginfo(self.v)

        # Calcula aceleração se houver uma velocidade anterior registrada
        if hasattr(self, 'previous_velocity') and hasattr(self, 'previous_time'):
            self.dt = current_time - self.previous_time
            # if self.dt > 0:
            #     self.acceleration = (self.v - self.previous_velocity) / self.dt
            #     rospy.loginfo(self.acceleration)

        # Armazena a velocidade e o tempo atuais para a próxima leitura
        self.previous_velocity = self.v
        self.previous_time = current_time

    def stateCallback(self, state: State) -> None:
        """Current vehicle driving state.

        Args:
            state (State): current vehicle driving state
        """
        self.current_state = state

    def gpsCallback(self, data: NavSatFix) -> None:
        """Get GPS data.

        Args:
            data (NavSatFix): gps data from mavros
        """
        self.current_location = data

    def compassCallback(self, data: Float64) -> None:
        """Compass data for orientation.

        Args:
            data (Float64): yaw angle, from 0~360 degrees, 0 to the north, increasing clockwise. 
        """
        self.current_yaw = np.radians(data.data)  # [RAD]

    def currentTargetCallback(self, data: GlobalPositionTarget) -> None:
        """Current target from mavros, usually the next item in the autonomous mission.

        Args:
            data (GlobalPositionTarget): Next mission point in global coordinates
        """
        # We use this callback to have a reference if the mission is not updated yet
        if not self.current_target or not self.waypoints_list:
            self.current_target = data
            if self.debug_mode:
                rospy.logwarn(
                    f"Received new target point in current target callback: {self.current_target.latitude} {self.current_target.longitude}.")

    def missionWaypointsCallback(self, data: WaypointList) -> None:
        """Mission currently set in the pixhawk board.

        Args:
            data (WaypointList): list of waypoints in global coordinates, with the current one marked in the properties
        """
        self.waypoints_list = data.waypoints
        if len(self.waypoints_list) == 0:
            return

        if self.home_waypoint:
            # If the last waypoint coordinates are 0, that means it is a return to launch waypoint, so we add the home waypoint values to this waypoint
            if self.waypoints_list[-1].x_lat == 0 and self.waypoints_list[-1].y_long == 0:
                self.waypoints_list[-1].x_lat = self.home_waypoint.geo.latitude
                self.waypoints_list[-1].y_long = self.home_waypoint.geo.longitude
            # Set the first point in the mission to be the home as well, to make sure we know it when coming back from a blocked region
            self.waypoints_list[0].x_lat = self.home_waypoint.geo.latitude
            self.waypoints_list[0].y_long = self.home_waypoint.geo.longitude

        # If we are in GUIDED mode, no need to update the current target
        if self.current_state.mode == "GUIDED":
            return

        # Get the current target waypoint if we are in a mission and not in GUIDED mode
        for i, waypoint in enumerate(self.waypoints_list):
            if waypoint.is_current:

                new_waypoint = waypoint
                self.current_waypoint_index = i

                self.current_target = GlobalPositionTarget()
                self.current_target.latitude = new_waypoint.x_lat
                self.current_target.longitude = new_waypoint.y_long
                self.current_target.altitude = new_waypoint.z_alt

                if self.debug_mode:
                    rospy.logwarn(
                        f"Target point set to {self.current_target.latitude}, {self.current_target.longitude} in mission callback, index: {i}.")

                break

    def homePositionCallback(self, data: HomePosition) -> None:
        """Last home waypoint set by the board, before or right at the mission start.

        Args:
            data (HomePosition): home position in global coordinates
        """
        # Set the home point so we know what to do if we are returning to launch
        if not self.home_waypoint:
            self.home_waypoint = data
        else:
            if self.home_waypoint.geo.latitude != data.geo.latitude or self.home_waypoint.geo.longitude != data.geo.longitude:
                self.home_waypoint = data
        if self.debug_mode and self.home_waypoint:
            rospy.logwarn(
                f"Home waypoint set to {self.home_waypoint.geo.latitude}, {self.home_waypoint.geo.longitude}")

    # endregion
    ############################################################################
    # region CONTROL FUNCTIONS
    ############################################################################
    def setFlightMode(self, mode: str) -> None:
        """Set the flight mode we want to navigate with.

        Args:
            mode (str): mode name, either MANUAL, GUIDED or AUTO
        """
        # If we are already in the right mode, don't do anything
        if self.current_state.mode == mode:
            return
        try:
            response = self.set_mode_service(custom_mode=mode)
            if response.mode_sent:
                rospy.logwarn(f"Changing navigation mode to {mode}...")
                while self.current_state.mode != mode:
                    response = self.set_mode_service(custom_mode=mode)
                    rospy.logwarn(
                        "Waiting for mode change request confirmation ...")
                    rospy.sleep(0.1)
                rospy.logwarn(f"Mode {mode} activated.")
        except rospy.ServiceException as e:
            rospy.logerr(f"Failed to change navigation mode to {mode}: {e}")

    def advanceToNextWaypoint(self, index) -> None:
        """Advance to the next waypoint in the list."""

        if not self.current_waypoint_index:
            return

        # Check if we have reached the end of the waypoint list
        if index >= len(self.waypoints_list):
            rospy.logwarn("All waypoints completed.")
            self.current_target = None  # No more waypoints to follow
            return

        # New waypoint index
        next_waypoint_index = index

        try:
            response = self.set_current_wp_srv(next_waypoint_index)
            if response.success:
                rospy.logwarn(
                    f"Successfully set current waypoint to {next_waypoint_index}")
            else:
                rospy.logwarn(
                    f"Failed to set current waypoint to {next_waypoint_index}")
        except rospy.ServiceException as e:
            rospy.logerr(
                f"Waypoint set service call failed for index {next_waypoint_index}: {e}")

        # Set the next waypoint as the current target
        self.current_waypoint_index = next_waypoint_index
        self.current_target = GlobalPositionTarget()
        self.current_target.latitude = self.waypoints_list[next_waypoint_index].x_lat
        self.current_target.longitude = self.waypoints_list[next_waypoint_index].y_long
        self.current_target.altitude = self.waypoints_list[next_waypoint_index].z_alt

        if self.debug_mode:
            rospy.loginfo(
                f"Target point set to {self.current_target.latitude}, {self.current_target.longitude} during obstacle avoidance.")

    def sendGuidedPointLocalFrame(self, best_v, best_w) -> None:
        """Send a specified velocity.

        Args:
            best_v (float): best linear velocity.
            best_w (float): best angular velocity.
        """
        # Create local velocity message (PositionTarget)
        guided_point_local_frame_msg = PositionTarget()
        guided_point_local_frame_msg.header = Header()
        guided_point_local_frame_msg.header.stamp = rospy.Time.now()

        # Ignore position, acceleration and focus only on velocity
        guided_point_local_frame_msg.type_mask = (
            PositionTarget.IGNORE_PX | PositionTarget.IGNORE_PY | PositionTarget.IGNORE_PZ |
            PositionTarget.IGNORE_AFX | PositionTarget.IGNORE_AFY | PositionTarget.IGNORE_AFZ |
            PositionTarget.IGNORE_YAW  # You can control YAW separately, if it's necessary
        )

        # Define frame coordenation (BODY_NED, for example)
        guided_point_local_frame_msg.coordinate_frame = PositionTarget.FRAME_BODY_NED

        # Configurate desired velocities [m/s] and [rad/s]
        guided_point_local_frame_msg.velocity.x = best_v  # Velocity in x direction
        guided_point_local_frame_msg.velocity.y = 0.0     # No lateral movement
        guided_point_local_frame_msg.velocity.z = 0.0     # No vertical movement
        # Angular velocity in z direction
        guided_point_local_frame_msg.yaw_rate = best_w

        # Publish message
        self.setpoint_local_pub.publish(guided_point_local_frame_msg)

    def targetWaypoint(self, standard=True):
        """Calculate the target waypoint in baselink frame.
        """
        try:

            if standard or self.waypoints_reached == 0:
                lat = self.current_target.latitude
                lon = self.current_target.longitude
            else:
                lat = self.waypoints_list[self.current_waypoint_index +
                                        self.waypoints_reached].x_lat
                lon = self.waypoints_list[self.current_waypoint_index +
                                        self.waypoints_reached].y_long

            goal_baselink_frame = worldToBaselink(
                target_lat=lat, target_lon=lon,
                current_location_lat=self.current_location.latitude, current_location_lon=self.current_location.longitude,
                current_yaw=self.current_yaw)

            goal_distance = np.linalg.norm(goal_baselink_frame)  # [m]
            goal_angle = np.degrees(np.arctan2(
                goal_baselink_frame[1], goal_baselink_frame[0]))  # [degrees]

            return goal_distance, goal_angle
        
        except:
            return 0, 0

    # endregion
    ############################################################################
    # region AVOIDANCE METHODS
    ############################################################################

    def dynamicWindow(self):
        """Calculate dynamic window obtaining the possible velocities for the next interval of time. 

        Returns:
            min_v (float): minimal linear velocity,
            max_v (float): maximal linear velocity,
            min_w (float): minimal angular velocity,
            max_w (float): maximal angular velocity."""

        # Calculate dynamic window
        min_v = max(self.min_v, self.v - self.max_acc_v * self.dt) # The second part simulates the maximum deceleration
        max_v = min(self.max_v, self.v + self.max_acc_v * self.dt) # The second part simulates the maximum acceleration
        min_w = max(-self.max_w, self.w - self.max_acc_w * self.dt)
        max_w = min(self.max_w, self.w + self.max_acc_w * self.dt)

        return min_v, max_v, min_w, max_w

    def dynamicWindowSafetyStop(self, dist_obst, w):
        """
        Calculate dynamic window to ensure that the robot can stop in time to avoid a collision.
        Based on dynamic restriction.

        Args:
            dist_obst (float): distance to the closest obstacle.
            w (float): angular velocity.
        Returns:
            safe_v_max (float): maximal linear velocity to stop in time,
            safe_w_max (float): maximal angular velocity to stop in time."""

        safe_v_max = min(np.sqrt(2 * dist_obst * self.max_acc_v), self.max_v)
        safe_w_max = np.sign(w) * np.sqrt(2 * dist_obst * self.max_acc_w)

        # Guarantees that the velocities are within the robot limits
        safe_w_max = np.clip(safe_w_max, -self.max_w, self.max_w)

        return safe_v_max, safe_w_max

    def getFovIndexFromTheta(self, theta):
        """
        Convert an angle (theta) in relation to the global frame to the Lidar index.

        Args:
            theta: the angle in relation to the global frame (in radians).

        Returns:
            The corresponding index in the Lidar field of view.
        """
        angle_min = self.angle_min  # Assume that the Lidar has a 260 degree FOV 
        angle_max = self.angle_max
        num_readings = len(self.valid_ranges)

        # Convert angle to the corresponding index in the Lidar
        fov_index = int((theta - angle_min) /
                (angle_max - angle_min) * num_readings)

        # Guarantees that the index is within the array limits
        fov_index = np.clip(fov_index, 0, num_readings - 1)

        return fov_index

    def objectiveFunction(self, min_v, max_v, min_w, max_w):
        """Objective function to be maximazed.
        Args:
            min_v (float): minimal linear velocity,
            max_v (float): maximal linear velocity,
            min_w (float): minimal angular velocity,
            max_w (float): maximal angular velocity.
        Returns:
            best_v (float): best linear velocity,
            best_w (float): best angular velocity."""

        max_cost = -float('inf')  # Initialize cost with negative infinity
        best_v, best_w = 0, 0

        if np.isinf(self.closest_obstacle_distance):
            dist_obst = 1000
        else:
            dist_obst = self.closest_obstacle_distance

        # Change angle from rad to degree just for the fuzzy logic
        obstacle_angle = np.degrees(self.obstacle_angle)

        # Apply fuzzy logic to discover alpha, beta and gamma
        self.alpha, self.beta, self.gamma = self.fuzzy.IsolatedObstacle(obstacle_angle, dist_obst)

        for v in np.linspace(min_v, max_v, num=self.v_reso):
            for w in np.linspace(min_w, max_w, num=self.w_reso):

                # Preview the new robot orientation (theta) after applying w
                theta_real = w * self.dt # Robot body frame
                theta_next = self.theta + theta_real # Robot global frame

                # Find the corresponding direction in the Lidar field of view
                fov_index = self.getFovIndexFromTheta(theta_real)

                # Obtain the distance to the obstacle in that direction
                dist_obst = self.valid_ranges[fov_index]

                # If no obstacle is on the curvature, this value is set to a large constant
                if np.isinf(dist_obst):
                    dist_obst = self.safety_distance_to_start #1000

                else:
                    safe_v_max, safe_w_max = self.dynamicWindowSafetyStop(
                        dist_obst, w)
                    
                    if safe_w_max > 0 and w > 0:

                        if safe_v_max < v or safe_w_max < w:
                            continue
                    else:
                        if safe_v_max < v or safe_w_max > w:
                            continue

                cost = self.alpha * \
                    self.headingCost(theta_next) + self.beta * \
                    dist_obst + self.gamma * v

                if cost > max_cost:

                    max_cost = cost
                    best_v, best_w = v, w

        return best_v, best_w

    def headingCost(self, theta_next):
        """Evaluate the alignment of the robot with the goal.

        Args:
            v (float): linear velocity,
            w (float): angular velocity.
        Returns:
            angle (float): angle between the robot heading and the goal angle."""
        
        # Calculate the goal angle in the global frame
        goal_angle_global = np.deg2rad(self.goal_angle)

        # Diference between test angle and heading
        angle_diff = theta_next - goal_angle_global

        # This is necessary to find the smallest angle
        angle_diff = angle_diff % (2 * np.pi)
        if angle_diff > np.pi:
            angle_diff -= 2 * np.pi

        angle = np.abs(angle_diff)
        angle = np.pi - angle

        return angle

    def replanVelocity(self):
        """Method to plan dynamic route.

        Returns:
            best_v (float): best linear velocity,
            best_w (float): best angular velocity."""

        min_v, max_v, min_w, max_w = self.dynamicWindow()

        best_v, best_w = self.objectiveFunction(min_v, max_v, min_w, max_w)

        best_v = min(best_v, self.max_v)
        best_w = np.clip(best_w, -self.max_w, self.max_w)

        return best_v, best_w

    def closestObstacleInCentralFov(self, fov_positions=160, center_index=320):
        """
        Return the distance of the closest obstacle in the robot's central field of view (degrees)
        and its angle relative to the LIDAR.

        Args:
            fov_positions: Number of positions in the central field of view.
            center_index: Central index of the Lidar readings list (approximately 320).

        Returns:
            Distance of the closest obstacle in the central field of view, or float('inf') if no obstacles are detected.
        """

        # New index for the angle range considered
        half_fov = fov_positions // 2
        start_index = center_index - half_fov
        end_index = center_index + half_fov

        # Get the distances within the central field of view
        central_fov_distances = self.valid_ranges[start_index:end_index]

        min_distance = min(central_fov_distances)
        min_index = np.argmin(central_fov_distances)

        # Calculate the relative angle between the robot and the closest obstacle
        angle_increment = (
            self.angle_max - self.angle_min) / len(self.valid_ranges)
        obstacle_angle = ( (start_index + min_index) - 
                            center_index) * angle_increment

        if min_distance == float('inf'):
            return 1000, obstacle_angle

        return min_distance, obstacle_angle

    def averageFilter(self, window_size=10):
        """
        Apply average filter to smooth Lidar distance readings.

        Args:
            window_size: Size of the moving average window.

        Returns:
            Readings of smoothed distance.
        """

        # The moving average window should be normalized by dividing by the window size
        kernel = np.ones(window_size) / window_size

        # Apply the moving average filter
        smoothed_ranges = np.convolve(self.valid_ranges, kernel, mode='same')

        return smoothed_ranges
    
    ############################################################################
    # region AUXILIARY FUNCTIONS
    ############################################################################

    def CBRAnalysis(self, main_dt):
        """
        Perform the CBR analysis to adjust the solution.
        
        Args:
            main_dt (float): Main time step.

        Returns:
            str: Case status (New case or Old case).
        """
        
        # Retrive case information
        case = self.cbr.Retrieve(self.closest_obstacle_distance, self.obstacle_angle, self.scenario)

        # If there is no similar case
        if case is None:

            print("No similar case")

            return "New case"
        
        v_case = case[4]
        w_case = case[5]

        # Revise and adjust new solution after DWA and Fuzzy
        new_v, new_w, situation = self.cbr.Revise(self.closest_obstacle_distance, self.best_v, self.best_w, v_case, w_case, main_dt)

        # If the new solution is better then the case one, update velocities
        if new_v is not None and new_w is not None:
            
            self.best_v = new_v
            self.best_w = new_w

            print("Modified case")

            return situation

        else:

            print("New case")

            return situation

    def AdjustLaserScan(self, scan):
        """
        Adjust the Lidar scan data before processing it.
        
        Args:
            scan (LaserScan): Lidar scan data.
        """

        # Make sure the scan values are valid before doing any math
        self.valid_ranges = np.array(scan.ranges)
        self.valid_ranges[self.valid_ranges == 0] = 1e6

        # Apply average filter to smooth the Lidar readings and reduce noise
        self.valid_ranges = self.averageFilter(window_size=5)

    ############################################################################
    # region MAIN CONTROL LOOP CALLBACK
    ############################################################################

    def laserScanCallback(self, scan) -> None:
        """ 
        We use lidar points to define obstacle in baselink frame and find the available path that is the closest to the waypoint we should travel to.
        We work with two main frames: baselink and world

        Baselink: X forward, Y left of the vehicle. 0~360 degrees, counter-clockwise, 0 is in the back
        World: latlon, so X (lat) points up and Y (lon) points to the right. 0~360 degrees, clockwise, 0 is in positive X 
        """

        # Avoiding the callback if the conditions are not met
        if not scan.ranges or self.current_state.mode == "MANUAL" or not self.current_target or not self.current_location or not self.home_waypoint:
            return

        # Adjust laser scan data
        self.AdjustLaserScan(scan)

        # If we are in AUTO mode we must reset the previous guided point angle
        if self.current_state.mode == "AUTO":
            self.previous_guided_point_angle = None

        # Verify the distance to the closest obstacle for 60 degrees in front of the robot
        closest_in_fov_60, obstacle_angle_60 = self.closestObstacleInCentralFov(
            fov_positions=148)

        # # Verify the distance to the closest obstacle for 260 degrees in front of the robot
        # closest_in_fov_260, obstacle_angle_260 = self.closestObstacleInCentralFov(
        #     fov_positions=640)
        
        # Verify the distance to the closest obstacle for 260 degrees in front of the robot
        closest_in_fov_180, obstacle_angle_180 = self.closestObstacleInCentralFov(
            fov_positions=443)

        if closest_in_fov_60 > self.safety_distance_to_start:
            closest_in_fov = closest_in_fov_180
            self.obstacle_angle = obstacle_angle_180
            safety_distance = 2.5
            fov = 443

        else:
            # Minimun distance to start the avoidance behavior
            closest_in_fov = closest_in_fov_60
            self.obstacle_angle = obstacle_angle_60
            safety_distance = self.safety_distance_to_start
            fov = 148

        # Apply DBSCAN to find clusters and classify the scenario
        self.scenario = self.cbr.FindScenario(self.valid_ranges, self.v, time(), fov_positions=fov)

        if closest_in_fov < safety_distance:
            self.closest_obstacle_distance = closest_in_fov

            # REPLAN VELOCITY - DWA
            self.best_v, self.best_w = self.replanVelocity()

            main_dt = time() - self.last_command_time

            if main_dt >= self.dt:

                rospy.loginfo(
                    f"BEFORE CBR -> Best v: {self.best_v} m/s, Best w: {self.best_w} rad/s")
                
                # CBR Analysis
                case = self.CBRAnalysis(main_dt)

                # Adjust velocities
                self.best_v = min(self.best_v, self.max_v)
                self.best_w = np.clip(self.best_w, -self.max_w, self.max_w)

                self.setFlightMode(mode="GUIDED")
                self.sendGuidedPointLocalFrame(
                    self.best_v, self.best_w)
                self.last_command_time = time()

                # Retain performed obstacle avoidance
                self.cbr.Retain(case, self.closest_obstacle_distance, self.obstacle_angle, self.scenario, self.best_v, self.best_w)

                # Results conference
                rospy.loginfo(
                    f"obst_dist: {self.closest_obstacle_distance} m, obstacle_angle: {self.obstacle_angle} degrees")
                rospy.loginfo(
                    f"Alpha: {self.alpha}, Beta: {self.beta}, Gamma: {self.gamma}")
                rospy.loginfo(
                    f"Best v: {self.best_v} m/s, Best w: {self.best_w} rad/s")
                rospy.loginfo(
                    " ")

                self.goal_distance, self.goal_angle = self.targetWaypoint(
                    False)
                
                if self.goal_distance == 0 and self.goal_angle == 0:
                    return

                if self.goal_distance < self.next_waypoint_dist:

                    self.waypoints_reached += 1
                    rospy.loginfo(
                        f"Waypoint counted {self.waypoints_reached}.")

        else:
            # Verify if the path is completely free ahead and on the sides, if so, finish the obstacle avoidance
            if time() - self.last_command_time > 1.1*self.dt and self.current_state.mode != "AUTO" and closest_in_fov_180 > 2.5 and closest_in_fov_60 > self.safety_distance_to_start:
                self.best_v = None
                self.best_w = None
                self.lidar_subdivisions = []

                rospy.logwarn("Obstacle avoidance finished.")
                self.setFlightMode(mode="AUTO")

                if self.waypoints_reached != 0:
                    self.advanceToNextWaypoint(
                        self.current_waypoint_index + self.waypoints_reached)
                    rospy.loginfo(
                        f"Next waypoint to go: {self.current_waypoint_index}.")
                    self.waypoints_reached = 0


if __name__ == "__main__":
    try:
        obst_avoid_node = ObstacleAvoidance()
    except rospy.ROSInterruptException:
        pass
