"""Inject Health Connect's required permission-rationale entry points.

python-for-android's standard manifest template has no application-child
injection option, so this hook runs immediately before Gradle assembles the
APK and adds the documented activity and Android 14 activity alias.
"""
from pathlib import Path
import hashlib
import re


def before_apk_assemble(_toolchain):
    manifest = Path.cwd() / 'src' / 'main' / 'AndroidManifest.xml'
    text = manifest.read_text(encoding='utf-8')
    # Kivy's cutout style is intentionally minimal.  Declare normal system
    # chrome in the activity theme as well as in Java: Android 15 can otherwise
    # apply edge-to-edge before PythonActivity gets a chance to restore bars.
    values = manifest.parent / 'res' / 'values' / 'strings.xml'
    style = values.read_text(encoding='utf-8')
    private_tar = manifest.parent / 'assets' / 'private.tar'
    if private_tar.exists():
        digest = hashlib.sha1(private_tar.read_bytes()).hexdigest()
        style = re.sub(r'(<string name="private_version">)[^<]*(</string>)', r'\g<1>' + digest + r'\g<2>', style)
    if 'windowFullscreen">false' not in style:
        style = style.replace(
            '<item name="android:windowNoTitle">true</item>',
            '<item name="android:windowNoTitle">true</item>\n'
            '        <item name="android:windowFullscreen">false</item>\n'
            '        <item name="android:windowDrawsSystemBarBackgrounds">true</item>\n'
            '        <item name="android:statusBarColor">#082B4B</item>\n'
            '        <item name="android:navigationBarColor">#040A14</item>\n'
            '        <item name="android:windowLightStatusBar">false</item>\n'
            '        <item name="android:windowLightNavigationBar">false</item>'
        )
        values.write_text(style, encoding='utf-8')
    # Scale the original artwork inside Android's launcher safe area. This
    # preserves the bitmap exactly; the drawable adds black padding at runtime.
    res = manifest.parent / 'res'
    drawable = res / 'drawable'
    adaptive = res / 'mipmap-anydpi-v26'
    drawable.mkdir(parents=True, exist_ok=True)
    adaptive.mkdir(parents=True, exist_ok=True)
    (drawable / 'launcher_safe.xml').write_text('''<?xml version="1.0" encoding="utf-8"?>
<layer-list xmlns:android="http://schemas.android.com/apk/res/android">
    <item><shape><solid android:color="#000000" /></shape></item>
    <item><inset android:inset="12%" android:drawable="@mipmap/icon" /></item>
</layer-list>''', encoding='utf-8')
    (adaptive / 'launcher_safe.xml').write_text('''<?xml version="1.0" encoding="utf-8"?>
<adaptive-icon xmlns:android="http://schemas.android.com/apk/res/android">
    <background android:drawable="@android:color/black" />
    <foreground><inset android:inset="21%" android:drawable="@mipmap/icon" /></foreground>
</adaptive-icon>''', encoding='utf-8')
    # All supported devices are API 26+, so use the adaptive resource. Its 58%
    # artwork sits inside the circular mask's guaranteed central safe zone.
    text = text.replace('android:icon="@mipmap/icon"', 'android:icon="@mipmap/launcher_safe"')
    text = text.replace('android:icon="@drawable/icon"', 'android:icon="@mipmap/launcher_safe"')
    manifest.write_text(text, encoding='utf-8')
    widget_xml = res / 'xml'
    widget_xml.mkdir(parents=True, exist_ok=True)
    (widget_xml / 'cafeteria_widget_info.xml').write_text('''<?xml version="1.0" encoding="utf-8"?>
<appwidget-provider xmlns:android="http://schemas.android.com/apk/res/android"
    android:minWidth="250dp" android:minHeight="150dp"
    android:resizeMode="horizontal|vertical" android:updatePeriodMillis="0"
    android:initialLayout="@layout/cafeteria_widget" android:widgetCategory="home_screen" />''', encoding='utf-8')
    layout = res / 'layout'
    drawable.mkdir(parents=True, exist_ok=True)
    layout.mkdir(parents=True, exist_ok=True)
    (drawable / 'cafeteria_widget_background.xml').write_text('''<?xml version="1.0" encoding="utf-8"?>
<shape xmlns:android="http://schemas.android.com/apk/res/android">
    <solid android:color="#A62A496B" />
    <corners android:radius="24dp" />
    <stroke android:width="1dp" android:color="#55D5E7FA" />
    <padding android:left="16dp" android:top="14dp" android:right="16dp" android:bottom="14dp" />
</shape>''', encoding='utf-8')
    (layout / 'cafeteria_widget.xml').write_text('''<?xml version="1.0" encoding="utf-8"?>
<LinearLayout xmlns:android="http://schemas.android.com/apk/res/android"
    android:layout_width="match_parent" android:layout_height="match_parent"
    android:orientation="vertical" android:background="@drawable/cafeteria_widget_background">
    <TextView android:id="@+id/widget_title" android:layout_width="match_parent" android:layout_height="wrap_content"
        android:textColor="#F1F7FF" android:textSize="14sp" android:textStyle="bold" android:maxLines="1" android:ellipsize="end" />
    <TextView android:id="@+id/widget_meal" android:layout_width="wrap_content" android:layout_height="wrap_content"
        android:layout_marginTop="7dp" android:textColor="#9DF4E4" android:textSize="11sp" android:textStyle="bold" />
    <TextView android:id="@+id/widget_menu" android:layout_width="match_parent" android:layout_height="0dp" android:layout_weight="1"
        android:layout_marginTop="5dp" android:textColor="#DCE8F7" android:textSize="12sp" android:maxLines="4" android:ellipsize="end" />
    <TextView android:id="@+id/widget_open" android:layout_width="wrap_content" android:layout_height="wrap_content"
        android:layout_gravity="end" android:text="살빼자 열기  ›" android:textColor="#A9C9FF" android:textSize="11sp" />
</LinearLayout>''', encoding='utf-8')
    entries = ''
    if 'ViewPermissionUsageActivity' not in text:
        entries += '''
        <activity
            android:name="com.welltable.welltable.PermissionsRationaleActivity"
            android:exported="true">
            <intent-filter>
                <action android:name="androidx.health.ACTION_SHOW_PERMISSIONS_RATIONALE" />
            </intent-filter>
        </activity>
        <activity-alias
            android:name="com.welltable.welltable.ViewPermissionUsageActivity"
            android:exported="true"
            android:targetActivity="com.welltable.welltable.PermissionsRationaleActivity"
            android:permission="android.permission.START_VIEW_PERMISSION_USAGE">
            <intent-filter>
                <action android:name="android.intent.action.VIEW_PERMISSION_USAGE" />
                <category android:name="android.intent.category.HEALTH_PERMISSIONS" />
            </intent-filter>
        </activity-alias>
'''
    if 'CafeteriaWidgetProvider' not in text:
        entries += '''
        <receiver android:name="com.welltable.welltable.CafeteriaWidgetProvider" android:exported="false">
            <intent-filter><action android:name="android.appwidget.action.APPWIDGET_UPDATE" /></intent-filter>
            <meta-data android:name="android.appwidget.provider" android:resource="@xml/cafeteria_widget_info" />
        </receiver>
'''
    if entries:
        manifest.write_text(text.replace('</application>', entries + '    </application>', 1), encoding='utf-8')

    # Newer Buildozer/P4A combinations both copy ``android.add_src`` into
    # src/main/java and add the original directory as a Gradle source root.
    # That compiles every bridge class twice. Retain P4A's copied source and
    # remove only the redundant external source-set declaration.
    gradle = manifest.parent.parent.parent / 'build.gradle'
    if gradle.exists():
        gradle_text = gradle.read_text(encoding='utf-8')
        gradle_text = re.sub(r"\s*java \{srcDir '[^']*/android_app/src'\}\s*", "\n", gradle_text)
        gradle.write_text(gradle_text, encoding='utf-8')
