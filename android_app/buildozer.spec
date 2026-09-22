[app]
title = 살빼자
package.name = welltable
package.domain = com.welltable
source.dir = .
source.include_exts = py,kv,ttf,otf,png,json,db
icon.filename = %(source.dir)s/assets/icon-opaque.png
# Android launchers otherwise wrap a legacy icon in their own dark adaptive
# background.  Keep the approved art as foreground over a matching peach
# layer so Samsung One UI fills the icon mask without black padding.
icon.adaptive_foreground.filename = %(source.dir)s/assets/icon-adaptive-foreground.png
icon.adaptive_background.filename = %(source.dir)s/assets/icon-adaptive-background.png
version = 2.0.10
presplash.filename = %(source.dir)s/assets/startup.png
android.presplash_color = #091629
requirements = python3,kivy
orientation = portrait
# Keep Android's status bar visible for a normal phone-app experience.
fullscreen = 0
android.permissions = android.permission.INTERNET, android.permission.health.READ_EXERCISE, android.permission.health.WRITE_EXERCISE, android.permission.health.READ_WEIGHT, android.permission.health.READ_HEART_RATE, android.permission.health.READ_SLEEP, android.permission.health.READ_STEPS, android.permission.health.READ_ACTIVE_CALORIES_BURNED, android.permission.health.READ_TOTAL_CALORIES_BURNED, android.permission.health.READ_DISTANCE, android.permission.health.READ_SPEED, android.permission.health.READ_RESTING_HEART_RATE, android.permission.health.READ_HEART_RATE_VARIABILITY, android.permission.health.READ_OXYGEN_SATURATION, android.permission.health.READ_RESPIRATORY_RATE, android.permission.health.READ_BODY_FAT, android.permission.health.READ_HEIGHT, android.permission.health.READ_BASAL_METABOLIC_RATE, android.permission.health.READ_LEAN_BODY_MASS, android.permission.health.READ_BONE_MASS, android.permission.health.READ_HYDRATION, android.permission.health.READ_NUTRITION, android.permission.health.WRITE_NUTRITION, android.permission.health.READ_HEALTH_DATA_HISTORY
android.api = 35
# Health Connect itself supports Android 8 (API 26) and above.
android.minapi = 26
android.archs = arm64-v8a
android.accept_sdk_license = True
# Buildozer 1.5 requires p4a's current bundle-capable command surface.
# `develop` also retains the stable Python 3.11 Android toolchain.
p4a.branch = develop
# Standard Android Health Connect permissions make the app appear in the
# system's App permissions list and enable the per-app consent dialog.
android.gradle_dependencies = androidx.health.connect:connect-client:1.1.0-alpha10, org.jetbrains.kotlinx:kotlinx-coroutines-android:1.7.3
android.add_src = ./src
android.extra_manifest_xml = ./health_manifest.xml
p4a.hook = ./health_manifest_hook.py

[buildozer]
# python-for-android rejects a storage directory containing spaces.  Keep its
# intermediate build tree outside the project path (which intentionally has a
# user-facing space in its name); final APKs are still written to ./bin.
build_dir = /private/tmp/welltable-android-build
log_level = 1
warn_on_root = 1
