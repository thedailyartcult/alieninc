"""Citadel — turns Kriegspiel's own logic inward on your infrastructure.

Citadel models your infrastructure as a graph of services and dependencies,
then runs attack-path scenarios against it to find where the walls give first
— before anyone outside this system does. It reuses Kriegspiel's Monte Carlo
branching and doctrine system, but instead of geographic forces it simulates
lateral movement through a network.
"""
