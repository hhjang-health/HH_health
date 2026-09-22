# Welltable

식단과 운동, 신체 변화를 한 곳에서 관리하는 모바일 우선 로컬 앱입니다.

## 실행

```bash
python3 -m pip install -r requirements.txt
python3 app.py
```

브라우저에서 `http://127.0.0.1:5000`을 열면 됩니다. 같은 Wi-Fi의 안드로이드 폰에서는 컴퓨터에 표시되는 네트워크 주소와 포트(예: `http://192.168.x.x:5000`)로 접속할 수 있습니다.

첫 실행 시 `welltable.db`가 생성되고, 대표 음식 20종과 아침·점심·저녁 식단 세트가 예시 데이터로 준비됩니다. 이후에 등록하는 식단, 운동, 신체 기록은 이 파일에 계속 저장됩니다.

## 포함된 기능

- 음식별 칼로리·탄수화물·단백질·지방 정보와 식단 세트 저장
- 아침·점심·저녁 식단의 매일 랜덤 추천 및 식사 완료 기록
- 수동 운동 기록과 Samsung Health/Health Connect 동기화 흐름
- 주간 운동·식단 리포트와 체중 변화 그래프
- 체중·체지방률·골격근량 수동 기록

## Samsung Health 연동 메모

현재 버전의 **동기화** 버튼은 Health Connect에서 받아온 데이터를 저장하는 흐름을 보여 주는 로컬 시연입니다. 실제 Samsung Health 데이터를 읽으려면 Android 앱 래퍼(Kotlin 또는 Kivy/Buildozer)에서 Health Connect 권한을 요청하고, 받은 활동·체성분 데이터를 `/api/workouts` 및 `/api/body`로 전달하면 됩니다. 이때 사용자 동의와 Google Health Connect 권한 설정이 필요합니다.
