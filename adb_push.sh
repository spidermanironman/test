#!/bin/bash
# adb_push.sh - Wrapper script for adb push with argument validation
#
# Usage: ./adb_push.sh <source> <destination>
#
# Example: ./adb_push.sh ./myfile.txt /sdcard/Download/myfile.txt

set -e

# Check if both source and destination arguments are provided
if [ $# -lt 2 ]; then
    echo "Error: adb push requires <source> and <destination> arguments"
    echo ""
    echo "Usage: $0 <source> <destination>"
    echo ""
    echo "Examples:"
    echo "  $0 ./local_file.txt /sdcard/Download/file.txt"
    echo "  $0 ./app-debug.apk /data/local/tmp/app.apk"
    echo "  $0 ./config/ /sdcard/config/"
    exit 1
fi

SOURCE="$1"
DESTINATION="$2"

# Verify the source file/directory exists
if [ ! -e "$SOURCE" ]; then
    echo "Error: Source file or directory '$SOURCE' does not exist"
    exit 1
fi

# Execute adb push with the provided arguments
echo "Pushing '$SOURCE' to '$DESTINATION'..."
adb push "$SOURCE" "$DESTINATION"

echo "Push completed successfully!"
