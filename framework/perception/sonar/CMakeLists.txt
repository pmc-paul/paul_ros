cmake_minimum_required(VERSION 2.8.3)
project(sonar)

find_package(catkin REQUIRED COMPONENTS
  rosserial_arduino
  rosserial_client
  rosserial_python
)

catkin_package()

rosserial_generate_ros_lib(
  PACKAGE rosserial_arduino
  SCRIPT make_libraries.py
)

rosserial_configure_client(
  DIRECTORY firmware
  TOOLCHAIN_FILE ${ROSSERIAL_ARDUINO_TOOLCHAIN}
)

rosserial_add_client_target(firmware sonar ALL)
rosserial_add_client_target(firmware sonar-upload)
