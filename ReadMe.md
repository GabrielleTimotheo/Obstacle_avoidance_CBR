## How the repository works

This repository is an implementation of the Dynamic Window Approach (DWA), using the Fuzzy technique to weigh
the parameters of the objective function from DWA. In addition, Case-based Reasoning (CBR) is added, which
improves final results by using past cases. 


# Main file
The main file is obstacle_avoidance_fuzzy.py, which has the mainstream. collision_lib.py, frame_conversitions.py, 
and log_debug.py are used to adapt the code for ROS simulation.

# Other files
cbr.py is the implementation of CBR, and fuzzy_cbr.py, is the implementation of Fuzzy logic.  

cases.py is how the program deals with past cases. For this repository, we use SQL to work with cases.