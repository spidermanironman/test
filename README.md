# ADB Push Helper

A wrapper script for `adb push` with proper argument validation.

## The Problem

Running `adb push` without arguments results in:
```
adb.exe: push requires <source> and <destination> arguments
```

## Solution

Use the provided `adb_push.sh` script which validates arguments before executing:

```bash
./adb_push.sh <source> <destination>
```

### Examples

```bash
# Push a single file
./adb_push.sh ./myfile.txt /sdcard/Download/myfile.txt

# Push an APK
./adb_push.sh ./app-debug.apk /data/local/tmp/app.apk

# Push a directory
./adb_push.sh ./config/ /sdcard/config/
```

## Direct ADB Usage

If you prefer using `adb` directly, the correct syntax is:

```bash
adb push <local_source> <remote_destination>
```

Common destinations on Android devices:
- `/sdcard/Download/` - Downloads folder
- `/sdcard/` - Internal storage root
- `/data/local/tmp/` - Temporary storage (for APKs, etc.)
