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
        self.dt = 0 # Time step

        self.distancia_alvo = None  # Distância alvo a ser mantida
        self.tolerancia_distancia = None  # Tolerância de comparação
        self.v_base = None # Velocidade linear base
        self.w_base = None # Velocidade angular base

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

        self.db.SearchSimilarCase(min_dist, angle, scenario)

    def prever_distancia_apos(self, distancia_inicial, v, w, delta_t):
        """
        Prever a nova distância após o DWA e fuzzy com base na velocidade linear (v) e angular (w).
        
        Args:
            distancia_inicial (float): Distância inicial ao obstáculo.
            v (float): Velocidade linear.
            w (float): Velocidade angular.
            delta_t (float): Intervalo de tempo para o movimento.

        Returns:
            float: Nova distância ao obstáculo.
        """
        deslocamento = v * delta_t  # Deslocamento linear
        delta_theta = w * delta_t  # Rotação angular

        # A nova distância ao obstáculo pode ser estimada como uma aproximação
        distancia_final = distancia_inicial - (deslocamento * math.cos(delta_theta))
        
        return distancia_final

    def AdjustSpeed(self, distancia_media, distancia_anterior):

        """Ajusta as velocidades baseadas na comparação da distância média com a distância alvo"""
        np.mean(distancias_lidar)

        if distancia_media > self.distancia_alvo + tolerancia_distancia:
            # Se a distância média for maior do que a desejada, reduzir velocidade
            v_ajustada = self.v_base * 0.8  # Exemplo de redução
            w_ajustada = self.w_base * 0.9  # Exemplo de redução
        elif distancia_media < self.distancia_alvo - tolerancia_distancia:
            # Se a distância média for menor, aumentar velocidade
            v_ajustada = self.v_base * 1.2  # Exemplo de aumento
            w_ajustada = self.w_base * 1.1  # Exemplo de aumento
        else:
            # Se a distância estiver dentro da tolerância, manter as velocidades
            v_ajustada = self.v_base
            w_ajustada = self.w_base

        return v_ajustada, w_ajustada

    def Revise(self, min_dist, angle, v, w):
        
        new_v, new_w = self.AdjustSpeed(distancia_media, distancia_anterior)
        
        return new_v, new_w

    def Retain(self, min_dist, angle, scenario, dist_after, angle_after):

        self.db.AddCase(min_dist, angle, scenario, dist_after, angle_after)
