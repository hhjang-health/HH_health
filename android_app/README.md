# 살빼자 Android

Kivy로 만든 **오프라인 우선 안드로이드 식단·운동 앱**입니다. 식단 세트, 당일 랜덤 식단, 운동, 체성분 기록은 앱 내부 SQLite 데이터베이스에 저장됩니다.

## 로컬 미리보기

```bash
python3.11 -m pip install -r requirements.txt
python3.11 main.py
```

## APK 만들기

Buildozer는 Linux에서 Android APK를 생성합니다. macOS에서는 WSL2, Ubuntu VM 또는 Linux CI에서 다음을 실행하세요.

```bash
python3 -m pip install buildozer cython
buildozer -v android debug
```

생성된 APK는 `bin/welltable-1.0.0-arm64-v8a_armeabi-v7a-debug.apk`에 있습니다. 이 파일을 안드로이드 폰으로 옮겨 설치하면 됩니다. 설치 전 휴대폰에서 해당 파일 관리 앱의 ‘알 수 없는 앱 설치’ 권한을 허용해야 합니다.

## Health Connect / Samsung Health

Samsung Health 자동 기록은 앱의 SQLite 구조와 `source='health_connect'` 필드에 맞춰 준비되어 있습니다. 실제 연동 배포 시에는 Android Health Connect SDK 권한(`ExerciseSession`, `TotalCaloriesBurned`, `Weight`, `BodyFat`)과 사용자 동의를 추가해야 합니다. 이 단계는 Google Play/Health Connect의 권한 검토 대상이므로, 사용자 동의 없이 데이터를 읽지 않도록 설계해야 합니다.
