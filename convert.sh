#!/bin/bash

. $(dirname $0)/config

target="$MEDIA_PATH/${1%%.*}.mp4"

$FFMPEG -v info -i "$1" -c:v $CODEC -b:v $BITRATE -y "$target" >$(dirname $0)/convert.log 2>&1 && (
  rm "$1"
  ln -f -s "$target" /home/hub/motion/lastmotion.mp4
)
