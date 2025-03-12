import numpy as np
from sklearn.cluster import DBSCAN
import matplotlib.pyplot as plt
import cases
import math

class CBR:
    def __init__(self):

        self.previous_clusters = None # Store previous clusters
        self.extra_margin = 0.2 # Extra margin to consider noise
        self.previous_time = None # Store previous time

        self.tol = 0.2 # Tolerance for distance

        self.max_v = 2.55  # Maximum linear velocity 2.55
        self.max_w = np.pi  # Maximum angular velocity np.pi/2
        self.max_acc_v = 0.5  # Maximum linear acceleration 0.5
        self.max_acc_w = np.pi/2  # Maximum angular acceleration

        # DataBase
        self.db = cases.CaseDatabase()

    def FindScenario(self, valid_ranges, v, current_time, fov_positions=160, center_index=320):
        """
        Identify scenario based on the clusters found in the data.
        
        Args:
            valid_ranges (np.array): Array with valid ranges from the LiDAR sensor.
            v (float): Linear velocity of the robot.
            current_time (float): Current time.
        
        Returns:
            str: Detected scenario.
        """

        # New index for the angle range considered
        half_fov = fov_positions // 2
        start_index = center_index - half_fov
        end_index = center_index + half_fov

        # Get the distances within the central field of view
        valid_ranges = valid_ranges[start_index:end_index]

        # Filter long distances
        valid_ranges = valid_ranges[valid_ranges < 1e6]

        if valid_ranges.size == 0:
            return

        # Apply DBSCAN to find clusters
        db = DBSCAN(eps=0.1, min_samples=10).fit(valid_ranges.reshape(-1, 1))
        labels = db.labels_ # Labels from each point (identified cluster)        
        n_clusters = len(np.unique(labels[labels != -1])) # Number of clusters in labels, ignoring noise if present

        # First iteration: store data and return
        if self.previous_clusters is None:
            self.previous_clusters = valid_ranges.copy() # Store current clusters
            self.previous_time = current_time
            return
        
        # Calculate time step
        self.dt = current_time - self.previous_time

        # Compare with previous clusters
        moving_obstacle = self.DetectMovingObstacle(valid_ranges, labels, v)

        # Update stored values
        self.previous_clusters = valid_ranges.copy()
        self.previous_time = current_time

        # Classify scenario

        # Moving obstacle
        if moving_obstacle:
            return "Moving obstacle"
        # Isolated obstacle
        if n_clusters == 1:
            return "Isolated obstacle"
        # Narrow corridor
        elif n_clusters == 2:
            return "Narrow corridor"
        # Unknown scenario
        elif n_clusters > 2:
            return "Unknown scenario"
        else:
            return None

    def DetectMovingObstacle(self, valid_ranges, labels, v):
        """
        Detect if there is a moving obstacle based on the displacement of the clusters.
        
        Args:
            valid_ranges (np.array): Array with valid ranges from the LiDAR sensor.
            labels (np.array): Array with the cluster labels.
            v (float): Linear velocity of the robot.
        
        Returns:
            bool: True if movement is detected, False otherwise.
        """

        prev = self.previous_clusters

        for cluster_label in np.unique(labels):
            if cluster_label == -1:  # Ignore noise
                continue
            
            try:
                # Get points from current and previous cluster
                current_cluster = valid_ranges[labels == cluster_label]
                previous_cluster = prev[labels == cluster_label]
            except:
                continue

            if current_cluster.size == 0 or previous_cluster.size == 0:
                continue

            # Define limit of variation to consider movement
            expected_displacement = v * self.dt
            threshold = expected_displacement + self.extra_margin

            # Calculate the average displacement of the cluster
            real_displacement = np.abs(np.mean(current_cluster) - np.mean(previous_cluster))

            if real_displacement > threshold:
                return True  # Movement detected

        return False  # No movement detected
    
    def dynamicWindowSafetyStop(self, dist_obst, w):
        """
        Calculate dynamic window to ensure that the robot can stop in time to avoid a collision.
        Based on dynamic restriction.

        Args:
            dist_obst (float): distance to the closest obstacle.
        Returns:
            safe_v_max (float): maximal linear velocity to stop in time,
            safe_w_max (float): maximal angular velocity to stop in time."""

        safe_v_max = min(np.sqrt(2 * dist_obst * self.max_acc_v), self.max_v)
        safe_w_max = np.sign(w) * np.sqrt(2 * dist_obst * self.max_acc_w)

        # Guarantees that the velocities are within the robot limits
        safe_w_max = np.clip(safe_w_max, -self.max_w, self.max_w)

        return safe_v_max, safe_w_max

    def Retrieve(self, min_dist, angle, scenario):
        """
        Retrieve similar cases from the database.
        
        Args:
            min_dist (float): Minimum distance to the obstacle.
            angle (float): Angle to the obstacle.
            scenario (str): Scenario.
        
        Returns:
            list: List of similar cases.
        """

        return self.db.SearchSimilarCase(min_dist, angle, scenario)

    def PredictDistance(self, dist_inicial, v, w, dt):
        """
        Predict the distance to the obstacle after a time step.
        
        Args:
            dist_inicial (float): Initial distance to the obstacle.
            v (float): Linear velocity.
            w (float): Angular velocity.
            dt (float): Time step.
        
        Returns:
            float: Predicted distance to the obstacle.
        """

        dS = v*dt # Linear displacement
        dTheta = w*dt # Angular displacement

        # Cosine rule
        new_min_dist = dS**2 + dist_inicial**2 + -2*dS*dist_inicial*math.cos(dTheta)

        return new_min_dist

    def Revise(self, min_dist, best_v, best_w, dt, v_case, w_case):
        """
        Revise and adjust new solution after DWA and Fuzzy.
        
        Args:
            min_dist (float): Minimum distance to the obstacle.
            best_v (float): Best linear velocity.
            best_w (float): Best angular velocity.
            dt (float): Time step.
        
        Returns:
            tuple: New linear and angular velocities.
        """

        # Distance to the obstacle after performing the best velocities
        dist_predicted_best = self.PredictDistance(min_dist, best_v, best_w, dt) # Use velocities from DWA and Fuzzy
        dist_predicted_case = self.PredictDistance(min_dist, v_case, w_case, dt) # Use velocities from past case

        # Distance difference between the predicted and the actual distance
        diff_dist_best = abs(min_dist - dist_predicted_best)
        diff_dist_case = abs(min_dist - dist_predicted_case)

        #-------------------------PROPOSE NEW VELOCITIES MODIFYING THE BEST-------------------------#
        if diff_dist_best > self.tol:
            # If the distance is greater than the desired, decrease the velocity
            new_v = best_v * 0.8  
            new_w = best_w * 0.9 

        elif diff_dist_best < self.tol:
            # If the distance is smaller than the desired, increase the velocity
            new_v = best_v * 1.2
            new_w = best_w * 1.1

        dist_predicted_modified = self.PredictDistance(min_dist, new_v, new_w , dt)
        diff_modified = abs(min_dist - dist_predicted_modified)
    
        #---------------CHECK IF IT'LL WON'T CRASH------------------#

        safe_v_max, safe_w_max = self.dynamicWindowSafetyStop(
            min_dist, new_w)
        
        if safe_w_max > 0 and new_w > 0:

            if safe_v_max < new_v or safe_w_max < new_w:
                return None, None, "New case" # Send the best if it's not safe
        else:
            if safe_v_max < new_v or safe_w_max > new_w:
                return None, None, "New case"  # Send the best if it's not safe

        #---------------COMPARE TO SEE WHICH VELOCITY IS BETTER------------------#

        if diff_modified < diff_dist_case:
            return new_v, new_w, "New case"
        else:
            return v_case, w_case, "Old Case"   
            
    def Retain(self, case, min_dist, angle, scenario, v, w):

        if case == "New case":

            self.db.AddCase(min_dist, angle, scenario, v, w)
