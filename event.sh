#!/bin/sh

. $(dirname $0)/config

case "$1" in
   motion)
     mosquitto_pub $MQTT_AUTH -t /home/alarm/camera/1/motion -m 1 -r
     ;;
   motion_end)
     mosquitto_pub $MQTT_AUTH -t /home/alarm/camera/1/motion -m 0 -r
     ;;
   photo)
     # send photo to MQTT with retain option
     mosquitto_pub $MQTT_AUTH -t /home/alarm/camera/1/photo -f "$2" -r
     ;;
   video)
     /home/hub/motion/convert.sh "$2"
     mosquitto_pub $MQTT_AUTH -t /home/alarm/camera/1/video -f "${2%%.*}.mp4"
     ;;
esac
