#!/bin/sh
cd $(dirname $0)
. ./config
echo $(date -Is): $* >>event.log

case "$1" in
   # this event will be occured when motion is detected
   # standart input contain snapshot in jpeg format
   motion_on)
     mosquitto_pub $MQTT -t $TOPIC_PHOTO -s -r
     mosquitto_pub $MQTT -t $TOPIC_MOTION -m 1 -r
     ;;

   # this event will be occured when motion is ended
   motion_off)
     mosquitto_pub $MQTT -t $TOPIC_MOTION -m 0 -r
     ;;

   # external action for make snapshot
   snapshot)
     # send photo to MQTT with retain option
     curl -s http://127.0.0.1:8092/camera/snapshot | mosquitto_pub $MQTT -t $TOPIC_PHOTO -s -r
     ;;


   # deprecated events from motion process
   motion)
     curl -s http://127.0.0.1:8092/camera/motion/start >/dev/null
     ;;

   motion_end)
     curl -s http://127.0.0.1:8092/camera/motion/stop >/dev/null
     #mosquitto_pub $MQTT -t $TOPIC_MOTION -m 0 -r
     ;;
esac
