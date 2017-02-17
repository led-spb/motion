#!/bin/bash

target=${1%%.*}.mp4
/usr/local/bin/avconv -v info -i "$1" -c:v h264 -b:v 500000 -y "$target" >/home/hub/motion/convert.log 2>&1 && rm $1
ln -f -s "$target" /home/hub/motion/lastmotion.mp4
#/home/pi/alarm/alarm-control.py video "$target"
