#!/usr/bin/env python

# Software License Agreement (BSD License)
#
# Copyright (c) 2013, SRI International
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions
# are met:
#
#  * Redistributions of source code must retain the above copyright
#    notice, this list of conditions and the following disclaimer.
#  * Redistributions in binary form must reproduce the above
#    copyright notice, this list of conditions and the following
#    disclaimer in the documentation and/or other materials provided
#    with the distribution.
#  * Neither the name of SRI International nor the names of its
#    contributors may be used to endorse or promote products derived
#    from this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
# "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
# LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS
# FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE
# COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT,
# INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING,
# BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
# LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT
# LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN
# ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.
#
# Author: Acorn Pooley, Mike Lautman

# Inspired from http://docs.ros.org/kinetic/api/moveit_tutorials/html/doc/move_group_python_interface/move_group_python_interface_tutorial.html
# Modified by Alexandre Vannobel to test the FollowJointTrajectory Action Server for the Kinova Gen3 robot
# Modified by Marc-Olivier Thibault for the PAUL PMC project.

import sys
import time
import rospy
import moveit_commander
from kortex_driver.srv import *
from kortex_driver.msg import *
import moveit_msgs.msg
import geometry_msgs.msg

from shape_msgs.msg import MeshTriangle, Mesh, SolidPrimitive, Plane
from math import pi, radians
from std_srvs.srv import Empty
from tf.transformations import quaternion_from_euler
from copy import deepcopy

from std_msgs.msg import Float64
from sensor_msgs.msg import JointState
from paul_manipulation.srv import ArmPosition, ArmPositionResponse
from paul_manipulation.srv import ElevationPosition, ElevationPositionResponse
from paul_manipulation.srv import ElevationVision, ElevationVisionResponse

from paul_manipulation.msg import Elevation


# Calling arm position from terminal
"""
rosservice call /my_gen3/arm_position "pose:
  position: 
    x: 0.573351668066
    y: 0.00135417296048
    z: 0.423615402123
  orientation: 
    x: 0.50016774096
    y: 0.499762534748
    z: 0.500237426704
    w: 0.499832128509"
"""

SCAN_POSE_1_RIGHT = (0, 0, pi/2, pi/4, 0, pi/2)
SCAN_POSE_2_RIGHT = (0, 0, pi/2, pi/4, 0, pi/2)
SCAN_POSE_3_RIGHT = (0, 0, pi/2, pi/4, 0, pi/2)
SCAN_POSE_4_RIGHT = (0, 0, pi/2, pi/4, 0, pi/2)
SCAN_POSE_5_RIGHT = (0, 0, pi/2, pi/4, 0, pi/2)

SCAN_POSE_1_LEFT  = (0, 0, pi/2, pi/4, 0, pi/2)
SCAN_POSE_2_LEFT  = (0, 0, pi/2, pi/4, 0, pi/2)
SCAN_POSE_3_LEFT  = (0, 0, pi/2, pi/4, 0, pi/2)
SCAN_POSE_4_LEFT  = (0, 0, pi/2, pi/4, 0, pi/2)
SCAN_POSE_5_LEFT  = (0, 0, pi/2, pi/4, 0, pi/2)

BACK_POSE         = (0, 0, pi/2, pi/4, 0, pi/2)
DROP_POSE         = (0, 0, pi/2, pi/4, 0, pi/2)


class PAUL_manipulator(object):
  """PAUL_manipulator"""
  def __init__(self):
    # Initialize the node
    super(PAUL_manipulator, self).__init__()
    moveit_commander.roscpp_initialize(sys.argv)
    rospy.init_node('PAUL_manipulator')
    rospy.Subscriber('/arm_position_request', geometry_msgs.msg.Pose, self.request_pose_callback) 

    self.elevationService = rospy.Service('vision_elevation_first', ElevationVision, self.elevationPositionCallback)
    self.armService = rospy.Service('arm_position', ArmPosition, self.armPositionCallback)

    self.height = 0
    self.subHeight = rospy.Subscriber("/joint_states", JointState, self.GetHeightElevation)

    self.zones_list = []


    try:
      self.is_gripper_present = rospy.get_param(rospy.get_namespace() + "is_gripper_present", False)
      if self.is_gripper_present:
        gripper_joint_names = rospy.get_param(rospy.get_namespace() + "gripper_joint_names", [])
        self.gripper_joint_name = gripper_joint_names[0]
      else:
        gripper_joint_name = ""
      self.degrees_of_freedom = rospy.get_param(rospy.get_namespace() + "degrees_of_freedom", 7)

      # Create the MoveItInterface necessary objects
      arm_group_name = "arm"
      self.robot = moveit_commander.RobotCommander("my_gen3/robot_description")
      #self.scene = moveit_commander.PlanningSceneInterface()
      print("namespace: " + str(rospy.get_namespace()))
      self.scene = moveit_commander.PlanningSceneInterface(ns=rospy.get_namespace())
      self.arm_group = moveit_commander.MoveGroupCommander(arm_group_name, ns=rospy.get_namespace())
      self.planning_frame = self.arm_group.get_planning_frame()

      self.display_trajectory_publisher = rospy.Publisher(rospy.get_namespace() + 'move_group/display_planned_path',
                                                    moveit_msgs.msg.DisplayTrajectory,
                                                    queue_size=20)

      if self.is_gripper_present:
        gripper_group_name = "gripper"
        self.gripper_group = moveit_commander.MoveGroupCommander(gripper_group_name, ns=rospy.get_namespace())

      rospy.loginfo("Initializing node in namespace " + rospy.get_namespace())
    except Exception as e:
      print (e)
      self.is_init_success = False
    else:
      self.is_init_success = True

  def add_box(self, x, y, z, w, size, box_name = "box", timeout=4):
    
    box_pose = geometry_msgs.msg.PoseStamped()
    box_pose.header.frame_id = self.planning_frame
    box_pose.pose.orientation.w = w
    box_pose.pose.position.x = x
    box_pose.pose.position.y = y
    box_pose.pose.position.z = z

    self.scene.add_box(box_name, box_pose, size)

    return self.wait_for_state_update(box_name=box_name, box_is_known=True, timeout=timeout)

  def remove_box(self, box_name="box", timeout=4):
    self.scene.remove_world_object(box_name)

    return self.wait_for_state_update(box_name=box_name, box_is_attached=False, box_is_known=False, timeout=timeout)

  def reach_named_position(self, target):
    arm_group = self.arm_group
    
    # Going to one of those targets
    rospy.loginfo("Going to named target " + target)
    # Set the target
    arm_group.set_named_target(target)
    # Plan the trajectory
    planned_path1 = arm_group.plan()
    # Execute the trajectory and block while it's not finished
    return arm_group.execute(planned_path1, wait=True)

  def reach_joint_angles(self, J1, J2, J3, J4, J5, J6, tolerance):
    arm_group = self.arm_group
    success = True

    # Get the current joint positions
    joint_positions = arm_group.get_current_joint_values()
    rospy.loginfo("Printing current joint positions before movement :")
    for p in joint_positions: rospy.loginfo(p)

    # Set the goal joint tolerance
    self.arm_group.set_goal_joint_tolerance(tolerance)

    # Set the joint target configuration
    joint_positions[0] = J1
    joint_positions[1] = J2
    joint_positions[2] = J3
    joint_positions[3] = J4
    joint_positions[4] = J5
    joint_positions[5] = J6
    arm_group.set_joint_value_target(joint_positions)
    
    # Plan and execute in one command
    success &= arm_group.go(wait=True)

    # Show joint positions after movement
    new_joint_positions = arm_group.get_current_joint_values()
    rospy.loginfo("Printing current joint positions after movement :")
    for p in new_joint_positions: rospy.loginfo(p)
    return success

  def get_cartesian_pose(self):
    arm_group = self.arm_group

    # Get the current pose and display it
    pose = arm_group.get_current_pose()
    rospy.loginfo("Actual cartesian pose is : ")
    rospy.loginfo(pose.pose)

    return pose.pose

  def reach_cartesian_pose(self, pose, tolerance, constraints):
    arm_group = self.arm_group
    
    # Set the tolerance
    arm_group.set_goal_position_tolerance(tolerance)

    # Set the trajectory constraint if one is specified
    if constraints is not None:
      arm_group.set_path_constraints(constraints)

    # Get the current Cartesian Position
    arm_group.set_pose_target(pose)

    # Plan and execute
    rospy.loginfo("Planning and going to the Cartesian Pose")
    return arm_group.go(wait=True)

  def reach_cartesian_waypoints(self, waypoints, tolerance, constraints):
    arm_group = self.arm_group
    
    # Set the tolerance
    arm_group.set_goal_position_tolerance(tolerance)

    # Set the trajectory constraint if one is specified
    if constraints is not None:
      arm_group.set_path_constraints(constraints)

    # Get the current Cartesian Position
    plans = []
    for pose in waypoints:
      arm_group.set_pose_target(pose)
      plans.append(arm_group.plan())

    #arm_group.clear_pose_targets()
    rospy.loginfo("before planning")
    #(plan, fraction) = arm_group.compute_cartesian_path(waypoints, 0.01, 0.0)
    rospy.loginfo("after planning")
    

    # Plan and execute
    rospy.loginfo("Planning and going to the Cartesian Pose")
    return arm_group.go(plans, wait=True) #arm_group.execute(plan, wait=True)

  def reach_gripper_position(self, relative_position):
    gripper_group = self.gripper_group
    
    # We only have to move this joint because all others are mimic!
    gripper_joint = self.robot.get_joint(self.gripper_joint_name)
    
    gripper_max_absolute_pos = gripper_joint.max_bound()
    gripper_min_absolute_pos = gripper_joint.min_bound()
    try:
      val = gripper_joint.move(relative_position * (gripper_max_absolute_pos - gripper_min_absolute_pos) + gripper_min_absolute_pos, True)
      return val
    except:
      return False

  def wait_for_state_update(self, box_name = "box", box_is_known=False, box_is_attached=False, timeout=4):
    start = rospy.get_time()
    seconds = rospy.get_time()
    while (seconds - start < timeout) and not rospy.is_shutdown():
      attached_objects = self.scene.get_attached_objects([box_name])
      is_attached = len(attached_objects.keys()) > 0

      is_known = box_name in self.scene.get_known_object_names()

      if (box_is_attached == is_attached) and (box_is_known == is_known):
        return True

      rospy.sleep(0.1)
      seconds = rospy.get_time()
    return False

  def box_is_in_scene(self, box_name = 'box'):
    return box_name in self.scene.get_known_object_names()

  def request_pose_callback(self, pose_msg):
    rospy.loginfo("Reaching requested Z-Pose..." + str(pose_msg))
    
    actual_pose = self.get_cartesian_pose()
    print("******Actual position******")
    print(actual_pose)
    actual_pose.position.y += pose_msg.position.y
    actual_pose.position.z += pose_msg.position.z
    
    success = self.reach_cartesian_pose(pose=actual_pose, tolerance=0.01, constraints=None)


    rospy.loginfo("Reaching requested Pose..." + str(pose_msg))
    actual_pose.position.x += pose_msg.position.x
    
    success = self.reach_cartesian_pose(pose=actual_pose, tolerance=0.01, constraints=None)
    
    if success:
      rospy.loginfo("Closing the gripper...")
      success &= self.reach_gripper_position(0.65)

    if success:
      rospy.loginfo("taking article...")
      actual_pose.position.z += 0.025
      success = self.reach_cartesian_pose(pose=actual_pose, tolerance=0.01, constraints=None)

    rospy.loginfo("Request is a " + str(success))

  def example_send_gripper_command(value):
    # Initialize the request
    # Close the gripper
    req = SendGripperCommandRequest()
    finger = Finger()
    finger.finger_identifier = 0
    finger.value = value
    req.input.gripper.finger.append(finger)
    req.input.mode = GripperMode.GRIPPER_FORCE

    robot_name = rospy.get_param('~robot_name', "my_gen3_lite")
    send_gripper_command_full_name = '/' + robot_name + '/base/send_gripper_command'
    send_gripper_commandCallback = rospy.ServiceProxy(send_gripper_command_full_name, SendGripperCommand)

    rospy.loginfo("Sending the gripper command...")

    # Call the service 
    try:
      send_gripper_commandCallback(req)
    except rospy.ServiceException:
      rospy.logerr("Failed to call SendGripperCommand")
      return False
    else:
      time.sleep(0.5)
      return True

  def GeneratePose(x, y, z, theta, phi, psi):
    actual_pose = geometry_msgs.msg.Pose()
    actual_pose.position.x = x
    actual_pose.position.y = y
    actual_pose.position.z = z

    theta_x = radians(theta)
    theta_y = radians(phi)
    theta_z = radians(psi)

    q = quaternion_from_euler(theta_x, theta_y, theta_z)
    
    actual_pose.orientation.x = q[0]
    actual_pose.orientation.y = q[1]
    actual_pose.orientation.z = q[2]
    actual_pose.orientation.w = q[3]
    
    return actual_pose




  # For moving the elevation system with the arm in the scan position (safe position)
  def elevationPositionCallback(self, msg):    
    if msg.level.data < 0 or msg.level.data > 2:
      return ElevationVisionResponse(False)

    success = self.is_init_success
    # try:
    #   rospy.delete_param("/kortex_examples_test_results/moveit_general_python")
    # except:
    #   return ElevationVisionResponse(False)

    # Check for error in request
    if (msg.direction != "right" and msg.direction != "left"):
      rospy.loginfo("Direction needs to be left or right, instead: " + msg.direction)
      return ElevationVisionResponse(False)

    if (msg.shelf < 1 or msg.shelf > 5):
      rospy.loginfo("Shelf number is not between 1 and 5, instead: " + str(msg.shelf))
      return ElevationVisionResponse(False)

    # Create the curtain for the whole cart
    self.add_box(0.0,-0.25,0.0, 5.0, (0.7, 0.2, 1.5), box_name='Cart_curtain')

    # Associate the good position for the scan
    if (msg.direction == "right"):
      if (msg.shelf == 1):
        scanPosition = SCAN_POSE_1_RIGHT
      elif (msg.shelf == 2):
        scanPosition = SCAN_POSE_2_RIGHT
      elif (msg.shelf == 3):
        scanPosition = SCAN_POSE_3_RIGHT
      elif (msg.shelf == 4):
        scanPosition = SCAN_POSE_4_RIGHT
      elif (msg.shelf == 5):
        scanPosition = SCAN_POSE_5_RIGHT
    elif (msg.direction == "left"):
      if (msg.shelf == 1):
        scanPosition = SCAN_POSE_1_LEFT
      elif (msg.shelf == 2):
        scanPosition = SCAN_POSE_2_LEFT
      elif (msg.shelf == 3):
        scanPosition = SCAN_POSE_3_LEFT
      elif (msg.shelf == 4):
        scanPosition = SCAN_POSE_4_LEFT
      elif (msg.shelf == 5):
        scanPosition = SCAN_POSE_5_LEFT


    if success:
      rospy.loginfo("Reaching Scan Pose...")
      success &= self.reach_joint_angles(*scanPosition, tolerance=0.01)
      print(success)

    # Remove the curtain
    self.remove_box('Cart_curtain')

    # Call service elevation_controller_vision
    print("Calling service")
    rospy.wait_for_service('/elevation_controller_vision')
    print("Waiting succeeded")
    try:
      elevationServiceResponse = rospy.ServiceProxy('/elevation_controller_vision', ElevationPosition)
      elevation = Elevation()
      elevation.data = msg.level.data
      resp1 = elevationServiceResponse(elevation)
      print("Service answer: " )
      print(resp1)
    except rospy.ServiceException as e:
      print("Service call failed: %s"%e)
      return ElevationVisionResponse(False)

    return ElevationVisionResponse(resp1.success)



  def GetHeightElevation(self, msg):
    self.height = msg.position[0]

  # For moving the arm to the requested position
  def armPositionCallback(self, pose_msg):

    print(self.zones_list.count)
    for i in range(len(self.zones_list)):
      self.remove_box(self.zones_list[i])
    del self.zones_list[:]

    # Adding the fixed box which protect the arm from the elevation system in steel
    self.add_box(0.0, 0.0, -0.1075, 1.0, (0.35, 0.1, 0.18), box_name="Elevation_system_steel")
    self.zones_list.append("Elevation_system_steel")

    if self.height > 700:
      self.add_box(0.0, 0.17, 1.02, 1.0, (0.65, 0.2, 1.35), box_name="Cart_high")
      self.zones_list.append("Cart_high")
    elif self.height > 300:
      self.add_box(0.0, 0.17, 0.7225, 1.0, (0.65, 0.2, 1.35), box_name="Cart_middle")
      self.zones_list.append("Cart_middle")
    else:
      self.add_box(0.0, 0.03, -0.21, 1.0, (0.65, 0.18, 0.4), box_name="Wheels")
      self.add_box(0.0, 0.17, 0.4175, 1.0, (0.65, 0.2, 1.35), box_name="Cart_low")
      self.zones_list.append("Wheels")
      self.zones_list.append("Cart_low")


    rospy.loginfo("Reaching requested Z-Pose..." + str(pose_msg.pose))
    actual_pose = self.get_cartesian_pose()

    actual_pose.position.y += pose_msg.pose.position.y
    actual_pose.position.z += pose_msg.pose.position.z
    
    success = self.reach_cartesian_pose(pose=actual_pose, tolerance=0.01, constraints=None)

    rospy.loginfo("Reaching requested Pose..." + str(pose_msg.pose))
    actual_pose.position.x += pose_msg.pose.position.x
    
    success = self.reach_cartesian_pose(pose=actual_pose, tolerance=0.01, constraints=None)

    if success:
      rospy.loginfo("Closing the gripper...")
      success &= self.reach_gripper_position(0.65)

    if success:
      rospy.loginfo("taking article...")
      actual_pose.position.z += 0.025
      success = self.reach_cartesian_pose(pose=actual_pose, tolerance=0.01, constraints=None)

    rospy.loginfo("Request is a " + str(success))

    return ArmPositionResponse(success)


def main():
    robot = PAUL_manipulator()
    # robot.add_box(0.0,0.0,0.0, 1.0, (0.2, 0.2, 0.0), box_name='table')
    # robot.add_box(0.0, -0.050, 0.10, 1.0, (0.4, 0.01, 0.2))
    # try:
    #   robot.remove_box()
    # except:
    #   pass
    # rospy.loginfo("Reaching Named Target Home...")
    # success = robot.reach_named_position("home")
    # print(success)

    print("Awaiting requests...")
    rospy.spin()


def test():
    example = PAUL_manipulator()

    # For testing purposes
    success = example.is_init_success
    try:
        rospy.delete_param("/kortex_examples_test_results/moveit_general_python")
    except:
        pass

    example.add_box(0.0, 0.0, 0.0, 1.0, (0.2, 0.2, 0.2))

    # if success:
    #   rospy.loginfo("Reaching 1st Pose...")
    #   actual_pose = GeneratePose(0.5, 0.2, 0.1, 90, 0, 90)
    #   success &= example.reach_cartesian_pose(pose=actual_pose, tolerance=0.01, constraints=None)
    #   print(success)

    # if success:
    #   rospy.loginfo("Reaching over box...")
    #   actual_pose = GeneratePose(0.5, 0.5, 0.1, 90, 0, 90)
    #   success &= example.reach_cartesian_pose(pose=actual_pose, tolerance=0.01, constraints=None)
    #   print(success)





    # For testing purposes
    rospy.set_param("/kortex_examples_test_results/moveit_general_python", success)

    if not success:
        rospy.logerr("The example encountered an error.")

if __name__ == '__main__':
  main()
