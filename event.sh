#!/bin/sh
cd $(dirname $0)
. ./config

case "$1" in
   motion)
     mosquitto_pub $MQTT -t $TOPIC_MOTION -m 1 -r
     curl -s http://127.0.0.1:8082/0/action/snapshot >/dev/null 2>&1
     ;;
   motion_end)
     mosquitto_pub $MQTT -t $TOPIC_MOTION -m 0 -r
     ;;
   photo)
     # send photo to MQTT with retain option
     mosquitto_pub $MQTT -t $TOPIC_PHOTO -f "$2" -r
     ln -f -s "$2" "$MEDIA_PATH/lastsnap.jpg"
     ;;
   video)
     ./convert.sh "$2"
     mosquitto_pub $MQTT -t $TOPIC_VIDEO -f "$MEDIA_PATH/lastmotion.mp4"
     ;;
esac
