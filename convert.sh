#!/bin/bash

FFMPEG=ffmpeg
CODEC=h264_omx
target=${1%%.*}.mp4

$FFMPEG -v info -i "$1" -c:v $CODEC -b:v 50000 -y "$target" >$(dirname $0)/convert.log 2>&1 && (
  rm "$1"
  ln -f -s "$target" /home/hub/motion/lastmotion.mp4
)
