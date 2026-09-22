package com.welltable.welltable;

import android.os.Bundle;

import org.kivy.android.PythonActivity;

/** Keeps normal system chrome visible after SDL receives window focus. */
public class WelltableActivity extends PythonActivity {
    private void restoreSystemBars() {
        SystemBarHelper.show(this);
        getWindow().getDecorView().postDelayed(new Runnable() {
            @Override public void run() { SystemBarHelper.show(WelltableActivity.this); }
        }, 250);
        getWindow().getDecorView().postDelayed(new Runnable() {
            @Override public void run() { SystemBarHelper.show(WelltableActivity.this); }
        }, 1100);
        getWindow().getDecorView().postDelayed(new Runnable() {
            @Override public void run() { SystemBarHelper.show(WelltableActivity.this); }
        }, 2200);
    }

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        restoreSystemBars();
    }

    @Override public void onResume() {
        super.onResume();
        restoreSystemBars();
    }

    @Override public void onWindowFocusChanged(boolean hasFocus) {
        super.onWindowFocusChanged(hasFocus);
        if (hasFocus) restoreSystemBars();
    }
}
