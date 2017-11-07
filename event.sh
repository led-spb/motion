#!/bin/sh

. $(dirname $0)/config

case "$1" in
   motion)
     mosquitto_pub $MQTT_AUTH -t /home/sensor/motion_door -m 1 -r
     ;;
   motion_end)
     mosquitto_pub $MQTT_AUTH -t /home/sensor/motion_door -m 0 -r
     ;;
   photo)
     # send photo to MQTT with retain option
     mosquitto_pub $MQTT_AUTH -t /home/camera/door/photo -f "$2" -r
     ln -f -s "$2" /home/hub/motion/lastsnap.jpg
     ;;
   video)
     /home/hub/motion/convert.sh "$2"
     mosquitto_pub $MQTT_AUTH -t /home/camera/door/video -f "${2%%.*}.mp4"
     ;;
esac
