package com.welltable.welltable;

import android.app.Activity;
import android.os.Bundle;
import android.view.Gravity;
import android.widget.TextView;

/** Shown by Health Connect when a user opens this app's permission rationale. */
public final class PermissionsRationaleActivity extends Activity {
    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        TextView message = new TextView(this);
        message.setText("살빼자는 사용자가 허용한 운동, 체중, 심박수, 수면 기록만 기기 안에서 식단·운동 통계에 사용합니다. 건강 정보는 외부 서버로 전송하지 않습니다.");
        message.setTextSize(18);
        message.setGravity(Gravity.CENTER);
        message.setPadding(48, 48, 48, 48);
        setContentView(message);
    }
}
