package com.welltable.welltable;

import android.app.PendingIntent;
import android.appwidget.AppWidgetManager;
import android.appwidget.AppWidgetProvider;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.widget.RemoteViews;

/** Home-screen widget containing only the cafeteria section of 살빼자. */
public class CafeteriaWidgetProvider extends AppWidgetProvider {
    private static final String PREFS = "cafeteria_widget";

    @Override public void onUpdate(Context context, AppWidgetManager manager, int[] ids) {
        for (int id : ids) update(context, manager, id);
    }

    public static void updateAll(Context context) {
        AppWidgetManager manager = AppWidgetManager.getInstance(context);
        ComponentName component = new ComponentName(context, CafeteriaWidgetProvider.class);
        int[] ids = manager.getAppWidgetIds(component);
        for (int id : ids) update(context, manager, id);
    }

    private static void update(Context context, AppWidgetManager manager, int id) {
        SharedPreferences prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
        RemoteViews views = new RemoteViews(context.getPackageName(), R.layout.cafeteria_widget);
        views.setTextViewText(R.id.widget_title, prefs.getString("title", "오늘의 구내식당"));
        views.setTextViewText(R.id.widget_meal, prefs.getString("meal", "살빼자"));
        views.setTextViewText(R.id.widget_menu, prefs.getString("menu", "앱을 열어 오늘 메뉴를 확인하세요."));
        Intent launch = new Intent(context, WelltableActivity.class);
        launch.setFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TOP);
        PendingIntent pending = PendingIntent.getActivity(context, 20, launch,
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
        views.setOnClickPendingIntent(R.id.widget_open, pending);
        views.setOnClickPendingIntent(R.id.widget_title, pending);
        views.setOnClickPendingIntent(R.id.widget_menu, pending);
        manager.updateAppWidget(id, views);
    }
}
