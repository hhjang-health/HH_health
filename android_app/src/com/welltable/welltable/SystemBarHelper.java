package com.welltable.welltable;

import android.app.Activity;
import android.graphics.Color;
import android.os.Build;
import android.view.View;
import android.view.Window;
import android.view.WindowInsets;
import android.view.WindowInsetsController;
import android.view.WindowManager;

/** Forces normal Android system chrome after SDL/Kivy initializes its surface. */
public final class SystemBarHelper {
    private SystemBarHelper() { }

    public static void show(final Activity activity) {
        if (activity == null) return;
        activity.runOnUiThread(new Runnable() {
            @Override public void run() {
                Window window = activity.getWindow();
                window.clearFlags(WindowManager.LayoutParams.FLAG_FULLSCREEN
                        | WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS
                        | WindowManager.LayoutParams.FLAG_TRANSLUCENT_STATUS);
                window.addFlags(WindowManager.LayoutParams.FLAG_FORCE_NOT_FULLSCREEN
                        | WindowManager.LayoutParams.FLAG_DRAWS_SYSTEM_BAR_BACKGROUNDS);
                // Keep normal (non edge-to-edge) system chrome visible.  On
                // Android 15 a transparent edge-to-edge bar was repeatedly
                // hidden by SDL after focus changes.
                // The status bar is the exact #091629 band used by the
                // approved home screen reference, not a separate blue block.
                window.setStatusBarColor(Color.rgb(8, 43, 75));
                window.setNavigationBarColor(Color.rgb(4, 10, 20));
                View decor = window.getDecorView();
                decor.setSystemUiVisibility(View.SYSTEM_UI_FLAG_VISIBLE);
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
                    window.setDecorFitsSystemWindows(true);
                    WindowInsetsController controller = window.getInsetsController();
                    if (controller != null) {
                        controller.setSystemBarsAppearance(0,
                                WindowInsetsController.APPEARANCE_LIGHT_STATUS_BARS
                                        | WindowInsetsController.APPEARANCE_LIGHT_NAVIGATION_BARS);
                        controller.show(WindowInsets.Type.statusBars() | WindowInsets.Type.navigationBars());
                    }
                }
            }
        });
    }
}
