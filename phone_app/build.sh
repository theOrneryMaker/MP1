#!/bin/bash
# Build the MP1 phone app for Ember (run in WSL Ubuntu-24.04 as root: its debug key signs it, so it installs over
# the earlier MP1 app). Copies this folder, the phone page (EMBER_01/BUILD_PAGES/MP1 Ember Phone.html, made by
# tools/make_page.py) and the update package (EMBER_01/BUILD_FROZEN/MP1_Ember_update_*.zip, made by
# tools/make_package.py) into ~/mp1app_ember (building on the Windows drive is slow), builds, and puts MP1.apk here.
#   wsl -d Ubuntu-24.04 -u root -- bash ".../MP1 EMBER/phone_app/build.sh"
# Bump versionCode in app/build.gradle for each build you hand out (Android won't install an older or equal one).
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
FW="$HERE/../EMBER_01"
PAGE="$FW/BUILD_PAGES/MP1 Ember Phone.html"
GV=8.14.3
export ANDROID_HOME=~/android-sdk
if [ ! -x ~/gradle/gradle-$GV/bin/gradle ]; then
    mkdir -p ~/gradle && cd ~/gradle
    wget -q https://services.gradle.org/distributions/gradle-$GV-bin.zip -O g.zip && unzip -q g.zip && rm g.zip
fi
[ -f "$PAGE" ] || { echo "no phone page: run tools/make_page.py"; exit 1; }
ls "$FW"/BUILD_FROZEN/MP1_Ember_update_*.zip >/dev/null || { echo "no update package: run tools/make_package.py"; exit 1; }
mkdir -p ~/mp1app_ember
rm -rf ~/mp1app_ember/app
cp -r "$HERE/app" "$HERE/build.gradle" "$HERE/settings.gradle" "$HERE/gradle.properties" ~/mp1app_ember/
mkdir -p ~/mp1app_ember/app/src/main/assets/firmware
cp "$PAGE" ~/mp1app_ember/app/src/main/assets/mp1_phone.html
cp "$FW"/BUILD_FROZEN/MP1_Ember_update_*.zip ~/mp1app_ember/app/src/main/assets/firmware/
ls -la ~/mp1app_ember/app/src/main/assets ~/mp1app_ember/app/src/main/assets/firmware
echo "sdk.dir=$ANDROID_HOME" > ~/mp1app_ember/local.properties
cd ~/mp1app_ember
~/gradle/gradle-$GV/bin/gradle --console=plain -q assembleDebug
cp app/build/outputs/apk/debug/app-debug.apk "$HERE/MP1.apk"
ls -la "$HERE/MP1.apk"
