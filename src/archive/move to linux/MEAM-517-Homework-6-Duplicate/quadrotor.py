Fimport numpy as np
import matplotlib.pyplot as plt
from numpy.linalg import inv
from numpy.linalg import cholesky
from math import sin, cos
import math
from scipy.interpolate import interp1d
from scipy.integrate import ode
from scipy.integrate import solve_ivp
from scipy.linalg import expm
from scipy.linalg import solve_continuous_are

from pydrake.solvers import mathematicalprogram as mp
from pydrake.solvers.osqp import OsqpSolver
from pydrake.solvers.snopt import SnoptSolver
from pydrake.solvers.mathematicalprogram import MathematicalProgram, Solve
import pydrake.symbolic as sym

from pydrake.all import MonomialBasis, OddDegreeMonomialBasis, Variables


class Quadrotor(object):
  def __init__(self, Q, R, Qf):
    self.g = 9.81
    self.m = 1
    self.a = 0.25
    self.I = 0.0625
    self.Q = Q
    self.R = R
    self.Qf = Qf

    # Input limits
    self.umin = 0
    self.umax = 5.5

    self.n_x = 6
    self.n_u = 2
   
  def x_d(self):
    # Nominal state
    return np.array([0, 0, 0, 0, 0, 0])

  def u_d(self):
    # Nominal input
    return np.array([self.m*self.g/2, self.m*self.g/2])

  def continuous_time_full_dynamics(self, x, u):
    # Dynamics for the quadrotor
    g = self.g
    m = self.m
    a = self.a
    I = self.I

    theta = x[2]
    ydot = x[3]
    zdot = x[4]
    thetadot = x[5]
    u0 = u[0]
    u1 = u[1]

    xdot = np.array([ydot,
                     zdot,
                     thetadot,
                     -sin(theta) * (u0 + u1) / m,
                     -g + cos(theta) * (u0 + u1) / m,
                     a * (u0 - u1) / I])
    return xdot

  def continuous_time_linearized_dynamics(self):
    # Dynamics linearized at the fixed point
    # This function returns A and B matrix
    A = np.zeros((6,6))
    A[:3, -3:] = np.identity(3)
    A[3, 2] = -self.g;

    B = np.zeros((6,2))
    B[4,0] = 1/self.m;
    B[4,1] = 1/self.m;
    B[5,0] = self.a/self.I
    B[5,1] = -self.a/self.I

    return A, B

  def discrete_time_linearized_dynamics(self, T):
    # Discrete time version of the linearized dynamics at the fixed point
    # This function returns A and B matrix of the discrete time dynamics
    A_c, B_c = self.continuous_time_linearized_dynamics()
    A_d = np.identity(6) + A_c * T;
    B_d = B_c * T;

    return A_d, B_d

  def add_initial_state_constraint(self, prog, x, x_current):
    # TODO: impose initial state constraint.
    # Use AddBoundingBoxConstraint
    prog.AddBoundingBoxConstraint(x_current, x_current, x[0, :].flatten())

  def add_input_saturation_constraint(self, prog, x, u, N):
    # TODO: impose input limit constraint.
    # Use AddBoundingBoxConstraint
    # The limits are available through self.umin and self.umax
    u_min = self.umin * np.ones((2, ))
    u_max = self.umax * np.ones((2, ))
    u_min -= self.u_d()[0] * np.ones((2, ))
    u_max -= self.u_d()[1] * np.ones((2, ))
    for i in range(N - 1):
        prog.AddBoundingBoxConstraint(u_min, u_max, u[i, :].flatten())

  def add_dynamics_constraint(self, prog, x, u, N, T):
    # TODO: impose dynamics constraint.
    # Use AddLinearEqualityConstraint(expr, value)
    A, B = self.discrete_time_linearized_dynamics(T)
    for i in range(N - 1):
        for j in range(6):
            prog.AddLinearEqualityConstraint(x[i + 1, :].flatten()[j] == (A @ x[i, :].flatten().T)[j] + (B @ u[i, :].flatten().T)[j]) 
       

  def add_cost(self, prog, x, u, N):
    cost = 0
    for i in range(N - 1):
        cost += x[i, :].flatten() @ self.Q @ x[i, :].flatten().T + u[i, :].flatten() @ self.R @ u[i, :].flatten().T
    cost += x[-1, :].flatten() @ self.Qf @ x[-1, :].flatten().T
    prog.AddQuadraticCost(cost)
    
  def compute_mpc_feedback(self, x_current, use_clf=False):
    '''
    This function computes the MPC controller input u
    '''

    # Parameters for the QP
    N = 10
    T = 0.1

    # Initialize mathematical program and decalre decision variables
    prog = MathematicalProgram()
    x = np.zeros((N, 6), dtype="object")
    for i in range(N):
      x[i] = prog.NewContinuousVariables(6, "x_" + str(i))
    u = np.zeros((N-1, 2), dtype="object")
    for i in range(N-1):
      u[i] = prog.NewContinuousVariables(2, "u_" + str(i))

    # Add constraints and cost
    self.add_initial_state_constraint(prog, x, x_current)
    self.add_input_saturation_constraint(prog, x, u, N)
    self.add_dynamics_constraint(prog, x, u, N, T)
    self.add_cost(prog, x, u, N)

    # Placeholder constraint and cost to satisfy QP requirements
    # TODO: Delete after completing this function
    # prog.AddQuadraticCost(0)
    # prog.AddLinearEqualityConstraint(0, 0)

    # Solve the QP
    solver = OsqpSolver()
    result = solver.Solve(prog)

    u_mpc = np.zeros(2)
    # TODO: retrieve the controller input from the solution of the optimization problem
    # and use it to compute the MPC input u
    # You should make use of result.GetSolution(decision_var) where decision_var
    # is the variable you want
    u_mpc = result.GetSolution(u[0]) + self.u_d()[0]

    return u_mpc

  def compute_lqr_feedback(self, x):
    '''
    Infinite horizon LQR controller
    '''
    A, B = self.continuous_time_linearized_dynamics()
    S = solve_continuous_are(A, B, self.Q, self.R)
    K = -inv(self.R) @ B.T @ S
    u = self.u_d() + K @ x;
    return u
