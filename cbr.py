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

        self.tol = 0.1 # Tolerance for distance

        # DataBase
        self.db = cases.CaseDatabase()

    def FindScenario(self, valid_ranges, v, current_time):
        """
        Identify scenario based on the clusters found in the data.
        
        Args:
            valid_ranges (np.array): Array with valid ranges from the LiDAR sensor.
            v (float): Linear velocity of the robot.
            current_time (float): Current time.
        
        Returns:
            None
        """

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
        dist_predicted = self.PredictDistance(min_dist, best_v, best_w, dt)
        dist_after = self.PredictDistance(min_dist, v_case, w_case, dt)

        # Distance difference between the predicted and the actual distance
        diff_dist = abs(min_dist - dist_predicted)
        diff_dist_case = abs(min_dist - dist_after)

        if diff_dist > self.tol:
            # If the average distance is greater than the desired, decrease the velocity
            new_v = best_v * 0.8  
            new_w = best_w * 0.9 

        elif diff_dist < self.tol:
            # If the average distance is smaller, increase the velocity
            new_v = best_v * 1.2  
            new_w = best_w * 1.1  
        else:
            return None, None

        if diff_dist < diff_dist_case:
            return new_v, new_w
        
        else:
            return None, None

    def Retain(self, case, min_dist, angle, scenario, v, w):

        if case == "New case":

            self.db.AddCase(min_dist, angle, scenario, v, w)
