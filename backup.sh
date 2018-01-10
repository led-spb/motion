#!/bin/sh

. $(dirname $0)/config

# Creating file for last day
TMP_VIDEO=$(mktemp)
TARGET_FILE=$MEDIA_PATH/$(date --date="-1 day" "+%Y-%m-%d.mp4")

#echo Checking data for last day
find -H $MEDIA_PATH -daystart -type f -name "$MEDIA_MASK" -mtime $MTIME -print | sort |
while read filename; do
   echo Processing $(basename $filename)
   $FFMPEG -v quiet -i $filename -c:v copy -an -f mpegts -bsf h264_mp4toannexb pipe:1 >>$TMP_VIDEO
done


if [ -s "$TMP_VIDEO" ]
then
  echo Encoding $TARGET_FILE

  $FFMPEG -f mpegts -i $TMP_VIDEO -c:v $CODEC -b:v $BACKUP_BITRATE -an -y -f mp4 $TARGET_FILE && (
    echo Sending $TARGET_FILE
    mosquitto_pub $MQTT -t $TOPIC_VIDEOM -f "$TARGET_FILE"

    echo Cleaning source files
    find -H $MEDIA_PATH -daystart -type f -name "$MEDIA_MASK" -mtime $MTIME -delete
  )
else
  echo No data for last day
fi

echo Backup files
find -H $MEDIA_PATH -type f -name "*.mp4" -mtime +1 | xargs -I {} mv {} $BACKUP_PATH/

# Remove jpeg files
find -H $SOURCE -type f -name "*.jpg" -delete

echo Removing old archives
# remove old archives
find -H $BACKUP_PATH -type f -name "*.mp4" -mtime +$RETAIN_DAYS -delete
echo Finished
rm $TMP_VIDEO 2>/dev/null

exit
