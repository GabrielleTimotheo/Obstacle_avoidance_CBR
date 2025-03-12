import numpy as np
import skfuzzy as fuzz
from skfuzzy import control as ctrl

class Fuzzy:
    def __init__(self):
                
        # Define fuzzy variables, each variable is created as Antecedent (input) or Consequent (output).
        self.distance_to_obstacle = ctrl.Antecedent(np.arange(0, 6, 0.1), 'distance_to_obstacle')
        self.angle = ctrl.Antecedent(np.arange(-120, 120, 1), 'angle')

        self.alpha = ctrl.Consequent(np.arange(0, 1, 0.1), 'alpha')
        self.beta = ctrl.Consequent(np.arange(0, 10, 1), 'beta')
        self.gamma = ctrl.Consequent(np.arange(0, 1, 0.1), 'gamma')

        # # Define membership functions for input variables
        # self.distance_to_obstacle['near'] = fuzz.sigmf(
        # self.distance_to_obstacle.universe, 2.5, -6)
        # self.distance_to_obstacle['medium'] = fuzz.gaussmf(
        # self.distance_to_obstacle.universe, 3.5, 0.3)
        # self.distance_to_obstacle['distant'] = fuzz.sigmf(
        # self.distance_to_obstacle.universe, 4.5, 6)

        # Define membership functions for input variables
        self.distance_to_obstacle['near'] = fuzz.sigmf(
        self.distance_to_obstacle.universe, 2.0, -6)
        self.distance_to_obstacle['medium'] = fuzz.gaussmf(
        self.distance_to_obstacle.universe, 3.0, 0.3)
        self.distance_to_obstacle['distant'] = fuzz.sigmf(
        self.distance_to_obstacle.universe, 4.0, 6)

        self.angle['lateral_left'] = fuzz.trapmf(self.angle.universe, [-180, -120, -60, -30])
        self.angle['frontal'] = fuzz.gaussmf(self.angle.universe, 0, 10)  # Média 0, desvio 20 para suavizar
        self.angle['lateral_right'] = fuzz.trapmf(self.angle.universe, [30, 60, 120, 180])

        # Define membership functions for output variables
        self.alpha['low'] = fuzz.trimf(self.alpha.universe, [0, 0, 0.5])
        self.alpha['medium'] = fuzz.trimf(self.alpha.universe, [0.4, 0.6, 0.6])
        self.alpha['high'] = fuzz.trimf(self.alpha.universe, [0.6, 1, 1])

        self.beta['low'] = fuzz.trimf(self.beta.universe, [0, 3.0, 6.0])
        self.beta['medium'] = fuzz.trimf(self.beta.universe, [5.0, 7.0, 7.0])
        self.beta['high'] = fuzz.trimf(self.beta.universe, [7.0, 10, 10])

        self.gamma['low'] = fuzz.trimf(self.gamma.universe, [0, 0, 0.6])
        self.gamma['medium'] = fuzz.trimf(self.gamma.universe, [0.5, 0.7, 0.7])
        self.gamma['high'] = fuzz.trimf(self.gamma.universe, [0.7, 1, 1])

        # Plot graphs of relevance (optional)
        # self.distance_to_obstacle.view()
        # self.angle.view()
        # self.alpha.view()
        # self.beta.view()

    def IsolatedObstacle(self, obstacle_angle, distance):

        rules_isolated = []

        # Define fuzzy rules
        # OK
        rules_isolated.append(ctrl.Rule(self.distance_to_obstacle['near'] & self.angle['frontal'], self.alpha['low']))
        rules_isolated.append(ctrl.Rule(self.distance_to_obstacle['near'] & self.angle['frontal'], self.beta['high']))
        rules_isolated.append(ctrl.Rule(self.distance_to_obstacle['near'] & self.angle['frontal'], self.gamma['low']))

        # OK
        rules_isolated.append(ctrl.Rule(self.distance_to_obstacle['near'] & self.angle['lateral_right'], self.alpha['high']))
        rules_isolated.append(ctrl.Rule(self.distance_to_obstacle['near'] & self.angle['lateral_right'], self.beta['low']))
        rules_isolated.append(ctrl.Rule(self.distance_to_obstacle['near'] & self.angle['lateral_right'], self.gamma['low']))

        # OK
        rules_isolated.append(ctrl.Rule(self.distance_to_obstacle['near'] & self.angle['lateral_left'], self.alpha['high']))
        rules_isolated.append(ctrl.Rule(self.distance_to_obstacle['near'] & self.angle['lateral_left'], self.beta['low']))
        rules_isolated.append(ctrl.Rule(self.distance_to_obstacle['near'] & self.angle['lateral_left'], self.gamma['low']))

        # OK
        rules_isolated.append(ctrl.Rule(self.distance_to_obstacle['medium'] & self.angle['frontal'], self.alpha['medium']))
        rules_isolated.append(ctrl.Rule(self.distance_to_obstacle['medium'] & self.angle['frontal'], self.beta['high']))
        rules_isolated.append(ctrl.Rule(self.distance_to_obstacle['medium'] & self.angle['frontal'], self.gamma['low']))

        # OK
        rules_isolated.append(ctrl.Rule(self.distance_to_obstacle['medium'] & self.angle['lateral_right'], self.alpha['high']))
        rules_isolated.append(ctrl.Rule(self.distance_to_obstacle['medium'] & self.angle['lateral_right'], self.beta['low']))
        rules_isolated.append(ctrl.Rule(self.distance_to_obstacle['medium'] & self.angle['lateral_right'], self.gamma['low']))

        # OK
        rules_isolated.append(ctrl.Rule(self.distance_to_obstacle['medium'] & self.angle['lateral_left'], self.alpha['high']))
        rules_isolated.append(ctrl.Rule(self.distance_to_obstacle['medium'] & self.angle['lateral_left'], self.beta['low']))
        rules_isolated.append(ctrl.Rule(self.distance_to_obstacle['medium'] & self.angle['lateral_left'], self.gamma['low']))

        # OK
        rules_isolated.append(ctrl.Rule(self.distance_to_obstacle['distant'] & self.angle['frontal'], self.alpha['medium']))
        rules_isolated.append(ctrl.Rule(self.distance_to_obstacle['distant'] & self.angle['frontal'], self.beta['high']))
        rules_isolated.append(ctrl.Rule(self.distance_to_obstacle['distant'] & self.angle['frontal'], self.gamma['low']))
        
        # OK
        rules_isolated.append(ctrl.Rule(self.distance_to_obstacle['distant'] & self.angle['lateral_right'], self.alpha['high']))
        rules_isolated.append(ctrl.Rule(self.distance_to_obstacle['distant'] & self.angle['lateral_right'], self.beta['low']))
        rules_isolated.append(ctrl.Rule(self.distance_to_obstacle['distant'] & self.angle['lateral_right'], self.gamma['low']))

        # OK
        rules_isolated.append(ctrl.Rule(self.distance_to_obstacle['distant'] & self.angle['lateral_left'], self.alpha['high']))
        rules_isolated.append(ctrl.Rule(self.distance_to_obstacle['distant'] & self.angle['lateral_left'], self.beta['low']))
        rules_isolated.append(ctrl.Rule(self.distance_to_obstacle['distant'] & self.angle['lateral_left'], self.gamma['low']))

        # Fuzzy controller
        isolated_obstacle_ctrl = ctrl.ControlSystem(rules_isolated)
        isolated_obstacle = ctrl.ControlSystemSimulation(isolated_obstacle_ctrl)

        # Input values for simulation
        isolated_obstacle.input['distance_to_obstacle'] = distance
        isolated_obstacle.input['angle'] = obstacle_angle

        # Simulate the fuzzy system
        isolated_obstacle.compute()

        # Output values
        alpha_output = isolated_obstacle.output['alpha']
        beta_output = isolated_obstacle.output['beta']
        gamma_output = isolated_obstacle.output['gamma']

        # Plot graphs of relevance (optional)
        # self.alpha.view(isolated_obstacle)
        # self.beta.view(isolated_obstacle)
        # self.gamma.view(isolated_obstacle)

        return alpha_output, beta_output, gamma_output
    
    def NarrowCorridor(self):
        pass
    
if __name__ == '__main__':
    fuzzy = Fuzzy()
    alpha, beta, gamma = fuzzy.IsolatedObstacle(8.975979, 2.976854)
    print(alpha, beta, gamma)