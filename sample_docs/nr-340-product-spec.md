# NR-340 Warehouse Robot Product Specification

## Overview

The NR-340 is Northwind Robotics' third-generation autonomous mobile robot (AMR) for warehouse goods-to-person workflows. It transports totes and cases between storage zones and pick stations, coordinating with the Northwind Fleet Manager for task allocation, traffic control, and charging.

Target environments are ambient warehouses with flat concrete floors, aisle widths of 1.2 m or greater, and Wi-Fi or private 5G coverage.

## Key Specifications

- Payload capacity: 340 kg maximum, evenly distributed on the lift platform
- Top speed: 2.0 m/s unloaded, 1.5 m/s under load, 0.8 m/s in designated human-dense zones
- Footprint: 920 mm x 680 mm, 310 mm tall with the platform lowered
- Lift height: 60 mm platform stroke for tote and shelf engagement
- Battery: 48 V lithium iron phosphate, hot-swappable, 10 hours typical runtime per charge
- Charging: opportunity charging at fleet-managed docks, 0 to 80 percent in 35 minutes
- Navigation: SLAM with lidar plus fiducial markers in high-precision zones
- Safety: dual safety-rated lidars with 270 degree combined coverage, ISO 3691-4 compliant stop zones, emergency stop buttons on all four corners

## Fleet Integration

Each NR-340 maintains a persistent connection to Fleet Manager over MQTT with TLS. Task assignment uses a bidding model: the Fleet Manager publishes work, and robots bid based on battery state, distance, and current load. Firmware updates are staged by Fleet Manager and applied only when a robot is docked and idle, never mid-task.

If connectivity drops, the robot completes its current task using its local map, then proceeds to the nearest safe holding zone and waits. It never starts new work while offline.

## Operating Limits

The NR-340 is not rated for freezer environments (minimum ambient temperature 0 C), outdoor use, ramps steeper than 3 degrees, or payloads exceeding 340 kg. Exceeding the payload rating voids the safety certification and triggers an automatic overload fault that requires supervisor reset through Fleet Manager.

## Service and Maintenance

Preventive maintenance is due every 1,500 operating hours: drive wheel inspection, lidar lens cleaning, brake test, and battery health report. All service events must be logged in Fleet Manager. Only technicians who have completed NR-340 Level 2 certification may open the drive enclosure.
