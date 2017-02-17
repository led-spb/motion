#!/bin/sh

. $(dirname $0)/config

###########
RETAIN_DAYS=14
SOURCE=/home/hub/motion
SRC_MASK="*_*.mp4"
BACKUP_PATH="/media/yandex/motion"
CODEC=h264
MTIME=1
###########


# Creating file for last day
TMP_VIDEO=$(mktemp)
TARGET_FILE=$SOURCE/$(date --date="-1 day" "+%Y-%m-%d.mp4")

echo Checking data for last day
find -H $SOURCE -daystart -type f -name "$SRC_MASK" -mtime $MTIME -print | sort |
while read filename; do
   echo Processing $(basename $filename)
   avconv -v quiet -i $filename -c:v copy -an -f mpegts -bsf h264_mp4toannexb pipe:1 >>$TMP_VIDEO
done


if [ -s "$TMP_VIDEO" ]
then
  echo Encoding $TARGET_FILE

  avconv -f mpegts -i $TMP_VIDEO -c:v $CODEC -an -y -f mp4 $TARGET_FILE && (
    echo Sending $TARGET_FILE
    mosquitto_pub $MQTT_AUTH -t /home/alarm/camera/1/videom -f "$TARGET_FILE"

    echo Cleaning source files
    find -H $SOURCE -daystart -type f -name "$SRC_MASK" -mtime $MTIME -delete
  )
else
  echo No data for last day
fi

echo Backup files
find -H $SOURCE -type f -name "*.mp4" -mtime +1 | xargs -I {} mv {} $BACKUP_PATH/

# Remove jpeg files
find -H $SOURCE -type f -name "*.jpg" -delete

echo Removing old archives
# remove old archives
find -H $BACKUP_PATH -type f -name "*.mp4" -mtime +$RETAIN_DAYS -delete
echo Finished
rm $TMP_VIDEO 2>/dev/null

exit