package com.welltable.welltable;

import android.app.Activity;
import android.content.Intent;
import android.net.Uri;
import android.os.Build;
import android.provider.Settings;

import androidx.activity.result.contract.ActivityResultContract;
import androidx.health.connect.client.HealthConnectClient;
import androidx.health.connect.client.PermissionController;
import androidx.health.connect.client.records.ExerciseSessionRecord;
import androidx.health.connect.client.records.ActiveCaloriesBurnedRecord;
import androidx.health.connect.client.records.TotalCaloriesBurnedRecord;
import androidx.health.connect.client.records.BodyFatRecord;
import androidx.health.connect.client.records.BasalMetabolicRateRecord;
import androidx.health.connect.client.records.HeightRecord;
import androidx.health.connect.client.records.HeartRateRecord;
import androidx.health.connect.client.records.LeanBodyMassRecord;
import androidx.health.connect.client.records.Record;
import androidx.health.connect.client.records.SleepSessionRecord;
import androidx.health.connect.client.records.StepsRecord;
import androidx.health.connect.client.records.DistanceRecord;
import androidx.health.connect.client.records.NutritionRecord;
import androidx.health.connect.client.records.metadata.Metadata;
import androidx.health.connect.client.records.WeightRecord;
import androidx.health.connect.client.request.ReadRecordsRequest;
import androidx.health.connect.client.request.AggregateRequest;
import androidx.health.connect.client.aggregate.AggregationResult;
import androidx.health.connect.client.response.ReadRecordsResponse;
import androidx.health.connect.client.time.TimeRangeFilter;
import androidx.health.connect.client.units.Energy;
import androidx.health.connect.client.units.Mass;

import org.json.JSONArray;
import org.json.JSONObject;

import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.temporal.ChronoUnit;
import java.lang.reflect.Constructor;
import java.util.Collections;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

import kotlin.coroutines.Continuation;
import kotlin.coroutines.EmptyCoroutineContext;
import kotlin.jvm.functions.Function2;
import kotlin.jvm.internal.Reflection;
import kotlin.reflect.KClass;
import kotlinx.coroutines.BuildersKt;
import kotlinx.coroutines.CoroutineScope;

/** Native reader for the on-device Health Connect store. */
public final class HealthConnectBridge {
    private static final int REQUEST_CODE = 48126;
    private static volatile String lastSyncJson = "{\"state\":\"idle\"}";

    private HealthConnectBridge() { }

    /**
     * Returns a short, stable status code so Python can present a useful next
     * action instead of treating an out-of-date provider as a permissions bug.
     */
    public static String availability(Activity activity) {
        try {
            int status = HealthConnectClient.getSdkStatus(activity);
            if (status == HealthConnectClient.SDK_AVAILABLE) return "available";
            if (status == HealthConnectClient.SDK_UNAVAILABLE_PROVIDER_UPDATE_REQUIRED) {
                return "update_required";
            }
            return "unavailable";
        } catch (Exception ignored) {
            return "unavailable";
        }
    }

    /** Open the official Health Connect listing; fall back to the browser. */
    public static boolean openHealthConnectUpdate(Activity activity) {
        final String packageName = "com.google.android.apps.healthdata";
        try {
            activity.startActivity(new Intent(Intent.ACTION_VIEW,
                    Uri.parse("market://details?id=" + packageName)));
            return true;
        } catch (Exception ignored) {
            try {
                activity.startActivity(new Intent(Intent.ACTION_VIEW,
                        Uri.parse("https://play.google.com/store/apps/details?id=" + packageName)));
                return true;
            } catch (Exception ignoredAgain) {
                return false;
            }
        }
    }

    public static boolean requestPermissions(Activity activity) {
        // Open the system app-permission panel first. This is the exact
        // Settings > Apps > 살빼자 > App permissions route on Samsung phones.
        if (openAppPermissionSettings(activity)) return true;
        // Do not gate this fallback on getSdkStatus(): some Samsung builds
        // return a transient unavailable status while the provider UI works.
        if (Build.VERSION.SDK_INT >= 34) {
            try {
                // Android 14+: exact Settings > Health Connect > App access
                // page for this application.
                Intent manage = new Intent("android.health.connect.action.MANAGE_HEALTH_PERMISSIONS");
                manage.putExtra(Intent.EXTRA_PACKAGE_NAME, activity.getPackageName());
                activity.startActivity(manage);
                return true;
            } catch (Exception ignored) {
                // Fall through to the SDK permission activity below.
            }
        }
        try {
            // Android 13 and older use the Health Connect provider activity.
            // Start it directly rather than through ActivityResultRegistry:
            // PythonActivity is not a ComponentActivity and cannot reliably
            // register that contract on Samsung firmware.
            ActivityResultContract<Set<String>, Set<String>> contract =
                    PermissionController.createRequestPermissionResultContract();
            Intent request = contract.createIntent(activity, requestedPermissions());
            activity.startActivity(request);
            return true;
        } catch (Exception ignored) {
            return false;
        }
    }

    /** Open Settings > Apps > this app > App permissions. */
    public static boolean openAppPermissionSettings(Activity activity) {
        try {
            // This platform Settings action opens the per-app "앱 권한" page
            // (not the generic app-info screen) on Samsung Android builds.
            Intent permissions = new Intent("android.intent.action.MANAGE_APP_PERMISSIONS");
            permissions.putExtra(Intent.EXTRA_PACKAGE_NAME, activity.getPackageName());
            permissions.setData(Uri.fromParts("package", activity.getPackageName(), null));
            if (permissions.resolveActivity(activity.getPackageManager()) != null) {
                activity.startActivity(permissions);
                return true;
            }
        } catch (Exception ignored) { }
        try {
            Intent details = new Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS);
            details.setData(Uri.fromParts("package", activity.getPackageName(), null));
            activity.startActivity(details);
            return true;
        } catch (Exception ignored) {
            return false;
        }
    }

    public static void sync(final Activity activity) {
        lastSyncJson = "{\"state\":\"syncing\"}";
        new Thread(new Runnable() {
            @Override public void run() {
                try {
                    String availability = availability(activity);
                    if ("update_required".equals(availability)) {
                        throw new IllegalStateException("Health Connect 업데이트가 필요합니다. 연결 버튼을 눌러 업데이트한 뒤 다시 동기화해 주세요.");
                    }
                    if (!"available".equals(availability)) {
                        throw new IllegalStateException("이 기기에서는 Health Connect를 사용할 수 없습니다. Android 시스템과 Google Play 서비스를 확인해 주세요.");
                    }
                    HealthConnectClient client = HealthConnectClient.getOrCreate(activity);
                    Set<String> granted = grantedPermissions(client);
                    if (!hasRequiredReadPermissions(granted)) {
                        JSONObject permission = new JSONObject();
                        permission.put("state", "permission_required");
                        permission.put("message", "체중·체지방·골격근량·활동 데이터를 읽을 권한을 허용해 주세요.");
                        lastSyncJson = permission.toString();
                        return;
                    }
                    lastSyncJson = createSnapshot(client).toString();
                } catch (Exception exception) {
                    try {
                        JSONObject error = new JSONObject();
                        error.put("state", "error");
                        error.put("message", exception.getMessage() == null ? "동기화 중 오류가 발생했습니다." : exception.getMessage());
                        lastSyncJson = error.toString();
                    } catch (Exception ignored) {
                        lastSyncJson = "{\"state\":\"error\",\"message\":\"동기화 중 오류가 발생했습니다.\"}";
                    }
                }
            }
        }, "welltable-health-sync").start();
    }

    public static String getLastSyncJson() { return lastSyncJson; }

    private static Set<String> requestedPermissions() {
        Set<String> permissions = new HashSet<>();
        permissions.add("android.permission.health.READ_EXERCISE");
        permissions.add("android.permission.health.READ_WEIGHT");
        permissions.add("android.permission.health.READ_BODY_FAT");
        permissions.add("android.permission.health.READ_HEIGHT");
        permissions.add("android.permission.health.READ_BASAL_METABOLIC_RATE");
        // Samsung Health publishes the user's muscle measurement through the
        // Lean Body Mass data type.  Without this explicit permission the
        // record is silently omitted from a snapshot even when weight and
        // body-fat are available.
        permissions.add("android.permission.health.READ_LEAN_BODY_MASS");
        permissions.add("android.permission.health.READ_HEALTH_DATA_HISTORY");
        permissions.add("android.permission.health.READ_HEART_RATE");
        permissions.add("android.permission.health.READ_SLEEP");
        permissions.add("android.permission.health.READ_STEPS");
        permissions.add("android.permission.health.READ_ACTIVE_CALORIES_BURNED");
        permissions.add("android.permission.health.READ_TOTAL_CALORIES_BURNED");
        permissions.add("android.permission.health.READ_DISTANCE");
        // The app writes only user-confirmed meal selections, never imported
        // food automatically.  Requesting this here lets the system show the
        // permission in the same Health Connect sheet.
        permissions.add("android.permission.health.WRITE_NUTRITION");
        permissions.add("android.permission.health.WRITE_EXERCISE");
        return permissions;
    }

    /** A partial grant must not silently look like a successful body sync. */
    private static boolean hasRequiredReadPermissions(Set<String> granted) {
        return granted.contains("android.permission.health.READ_WEIGHT")
                && granted.contains("android.permission.health.READ_BODY_FAT")
                && granted.contains("android.permission.health.READ_LEAN_BODY_MASS")
                && granted.contains("android.permission.health.READ_STEPS")
                && granted.contains("android.permission.health.READ_EXERCISE")
                && granted.contains("android.permission.health.READ_ACTIVE_CALORIES_BURNED")
                && granted.contains("android.permission.health.READ_DISTANCE");
    }

    /** Write only an explicitly saved manual/cafeteria meal to Health Connect. */
    public static boolean writeNutrition(Activity activity, String title, double calories,
                                         double protein, double carbs) {
        try {
            HealthConnectClient client = HealthConnectClient.getOrCreate(activity);
            if (!grantedPermissions(client).contains("android.permission.health.WRITE_NUTRITION")) return false;
            Instant now = Instant.now();
            ZoneOffset offset = ZoneId.systemDefault().getRules().getOffset(now);
            insert(client, Collections.<Record>singletonList(createNutritionRecord(
                    now, offset, title, calories, protein, carbs)));
            return true;
        } catch (Exception ignored) { return false; }
    }

    /** Write only a workout the user directly records in this app. */
    public static boolean writeWorkout(Activity activity, String title, int minutes) {
        try {
            HealthConnectClient client = HealthConnectClient.getOrCreate(activity);
            if (!grantedPermissions(client).contains("android.permission.health.WRITE_EXERCISE")) return false;
            Instant end = Instant.now();
            Instant start = end.minus(Math.max(1, minutes), ChronoUnit.MINUTES);
            ZoneOffset offset = ZoneId.systemDefault().getRules().getOffset(end);
            ExerciseSessionRecord record = new ExerciseSessionRecord(start, offset, end, offset,
                    exerciseTypeForTitle(title), title == null || title.trim().isEmpty() ? "운동" : title.trim());
            insert(client, Collections.<Record>singletonList(record));
            return true;
        } catch (Exception ignored) { return false; }
    }

    @SuppressWarnings({"unchecked", "rawtypes"})
    private static Set<String> grantedPermissions(final HealthConnectClient client) throws InterruptedException {
        return (Set<String>) BuildersKt.runBlocking(
                EmptyCoroutineContext.INSTANCE,
                new Function2<CoroutineScope, Continuation<? super Set<String>>, Object>() {
                    @Override public Object invoke(CoroutineScope scope, Continuation<? super Set<String>> continuation) {
                        return client.getPermissionController().getGrantedPermissions((Continuation) continuation);
                    }
                });
    }

    private static JSONObject createSnapshot(HealthConnectClient client) throws Exception {
        Instant now = Instant.now();
        // Body-composition measurements are often taken less frequently than
        // daily activity.  Keep activity data recent below, but search a full
        // year for the latest body measurement so a valid muscle reading is
        // not discarded merely because it is older than 30 days.
        TimeRangeFilter range = TimeRangeFilter.between(now.minus(365, ChronoUnit.DAYS), now);
        JSONObject payload = new JSONObject();
        payload.put("state", "ready");
        payload.put("synced_at", now.toString());

        List<WeightRecord> weights = read(client, WeightRecord.class, range);
        if (!weights.isEmpty()) {
            WeightRecord latest = weights.get(0);
            for (WeightRecord item : weights) if (item.getTime().isAfter(latest.getTime())) latest = item;
            payload.put("weight", latest.getWeight().getKilograms());
            payload.put("weight_time", latest.getTime().toString());
        }

        List<BodyFatRecord> bodyFats = read(client, BodyFatRecord.class, range);
        if (!bodyFats.isEmpty()) {
            BodyFatRecord latest = bodyFats.get(0);
            for (BodyFatRecord item : bodyFats) if (item.getTime().isAfter(latest.getTime())) latest = item;
            // Health Connect's Percentage value is already expressed on the
            // human-facing 0–100 scale.  Multiplying it again turned 25.9%
            // into 2,590%, so pass the source value through unchanged.
            payload.put("body_fat", latest.getPercentage().getValue());
            payload.put("body_fat_time", latest.getTime().toString());
        }

        // Samsung Health commonly exports skeletal-muscle measurements as
        // LeanBodyMass records.  Read the latest one independently because it
        // is not necessarily timestamped with the user's weight entry.
        List<LeanBodyMassRecord> leanMasses = read(client, LeanBodyMassRecord.class, range);
        if (!leanMasses.isEmpty()) {
            LeanBodyMassRecord latest = leanMasses.get(0);
            for (LeanBodyMassRecord item : leanMasses) if (item.getTime().isAfter(latest.getTime())) latest = item;
            payload.put("lean_body_mass", latest.getMass().getKilograms());
            payload.put("lean_body_mass_time", latest.getTime().toString());
        }

        List<HeightRecord> heights = read(client, HeightRecord.class, range);
        if (!heights.isEmpty()) {
            HeightRecord latest = heights.get(0);
            for (HeightRecord item : heights) if (item.getTime().isAfter(latest.getTime())) latest = item;
            payload.put("height_cm", latest.getHeight().getMeters() * 100d);
        }
        double basalKcalPerDay = 0d;
        List<BasalMetabolicRateRecord> basalRates = read(client, BasalMetabolicRateRecord.class, range);
        if (!basalRates.isEmpty()) {
            BasalMetabolicRateRecord latest = basalRates.get(0);
            for (BasalMetabolicRateRecord item : basalRates) if (item.getTime().isAfter(latest.getTime())) latest = item;
            basalKcalPerDay = latest.getBasalMetabolicRate().getKilocaloriesPerDay();
            payload.put("basal_kcal", basalKcalPerDay);
        }

        List<HeartRateRecord> heartRates = read(client, HeartRateRecord.class, range);
        long latestBpm = -1;
        Instant latestHeartTime = Instant.EPOCH;
        for (HeartRateRecord record : heartRates) {
            for (HeartRateRecord.Sample sample : record.getSamples()) {
                if (sample.getTime().isAfter(latestHeartTime)) {
                    latestHeartTime = sample.getTime();
                    latestBpm = sample.getBeatsPerMinute();
                }
            }
        }
        if (latestBpm >= 0) {
            payload.put("heart_rate", latestBpm);
            payload.put("heart_time", latestHeartTime.toString());
        }

        List<SleepSessionRecord> sleeps = read(client, SleepSessionRecord.class, range);
        if (!sleeps.isEmpty()) {
            SleepSessionRecord latest = sleeps.get(0);
            for (SleepSessionRecord item : sleeps) if (item.getEndTime().isAfter(latest.getEndTime())) latest = item;
            double hours = Math.max(0d, (latest.getEndTime().toEpochMilli() - latest.getStartTime().toEpochMilli()) / 3600000d);
            payload.put("sleep_hours", Math.round(hours * 10d) / 10d);
            payload.put("sleep_end", latest.getEndTime().toString());
        }

        // Health Connect timestamps are UTC.  A UTC midnight range omitted the
        // morning portion of a Korean day (and often returned 0 steps).  Use
        // the phone's local calendar day, the same boundary Samsung Health
        // presents to the user.
        ZoneId localZone = ZoneId.systemDefault();
        LocalDate localToday = LocalDate.now(localZone);
        Instant todayStart = localToday.atStartOfDay(localZone).toInstant();
        // Samsung Health may publish its live daily counter as one interval
        // that closes at the next local midnight.  Ending the query at "now"
        // drops that still-open record and made this app lag behind Samsung
        // Health.  Query the complete local calendar day; the record's count
        // is its current measured count, not a forecast.
        Instant tomorrowStart = localToday.plusDays(1).atStartOfDay(localZone).toInstant();
        long todaySteps = aggregateSteps(client, TimeRangeFilter.between(todayStart, tomorrowStart));
        payload.put("steps", todaySteps);

        // Samsung Health writes activity calories and travel distance as
        // separate Health Connect record types.  They are intentionally read
        // from exactly the same local-day range as steps so every number on
        // the tile refers to the same day.
        double activeCalories = 0d;
        // Samsung Health can publish today's activity calories as an
        // interval whose end is the next local midnight.  Querying only up
        // to "now" excludes that still-open interval and incorrectly shows
        // 0 kcal.  This is still *activity* energy only, never total energy.
        for (ActiveCaloriesBurnedRecord item : read(client, ActiveCaloriesBurnedRecord.class,
                TimeRangeFilter.between(todayStart, tomorrowStart))) {
            activeCalories += item.getEnergy().getKilocalories();
        }
        // Samsung Health installations often expose today's activity ring
        // only through TotalCaloriesBurnedRecord. Derive active energy by
        // subtracting elapsed resting energy; never display the raw total.
        // This matches Samsung Health's '활동 칼로리' card while retaining the
        // dedicated ActiveCalories record whenever the provider offers it.
        if (activeCalories <= 0d) {
            double totalCalories = 0d;
            for (TotalCaloriesBurnedRecord item : read(client, TotalCaloriesBurnedRecord.class,
                    TimeRangeFilter.between(todayStart, tomorrowStart))) {
                totalCalories += item.getEnergy().getKilocalories();
            }
            if (totalCalories > 0d) {
                double elapsedDayFraction = Math.max(0d, Math.min(1d,
                        (now.toEpochMilli() - todayStart.toEpochMilli()) / 86400000d));
                // If the provider omits BMR, use a conservative standard
                // resting estimate solely to avoid showing total calories.
                double resting = (basalKcalPerDay > 0d ? basalKcalPerDay : 1500d) * elapsedDayFraction;
                activeCalories = Math.max(0d, totalCalories - resting);
            }
        }
        payload.put("active_calories", Math.round(activeCalories));

        double distanceMeters = 0d;
        for (DistanceRecord item : read(client, DistanceRecord.class,
                TimeRangeFilter.between(todayStart, tomorrowStart))) {
            distanceMeters += item.getDistance().getMeters();
        }
        payload.put("distance_meters", Math.round(distanceMeters));

        JSONArray workouts = new JSONArray();
        long todayExerciseMinutes = 0L;
        for (ExerciseSessionRecord item : read(client, ExerciseSessionRecord.class, range)) {
            JSONObject workout = new JSONObject();
            workout.put("title", item.getTitle() == null || item.getTitle().trim().isEmpty()
                    ? exerciseTypeName(item.getExerciseType()) : item.getTitle());
            workout.put("start", item.getStartTime().toString());
            workout.put("minutes", Math.max(1, Math.round((item.getEndTime().toEpochMilli() - item.getStartTime().toEpochMilli()) / 60000f)));
            workout.put("type", item.getExerciseType());
            workouts.put(workout);
            if (!item.getEndTime().isBefore(todayStart) && !item.getStartTime().isAfter(now)) {
                todayExerciseMinutes += Math.max(1, Math.round((item.getEndTime().toEpochMilli() - item.getStartTime().toEpochMilli()) / 60000f));
            }
        }
        payload.put("active_minutes", todayExerciseMinutes);
        payload.put("workouts", workouts);
        return payload;
    }

    /** Translate the Health Connect exercise enum into a useful Korean title. */
    private static String exerciseTypeName(int type) {
        if (type == ExerciseSessionRecord.EXERCISE_TYPE_RUNNING
                || type == ExerciseSessionRecord.EXERCISE_TYPE_RUNNING_TREADMILL) return "러닝";
        if (type == ExerciseSessionRecord.EXERCISE_TYPE_WALKING) return "걷기";
        if (type == ExerciseSessionRecord.EXERCISE_TYPE_BIKING
                || type == ExerciseSessionRecord.EXERCISE_TYPE_BIKING_STATIONARY) return "사이클";
        if (type == ExerciseSessionRecord.EXERCISE_TYPE_STRENGTH_TRAINING
                || type == ExerciseSessionRecord.EXERCISE_TYPE_WEIGHTLIFTING) return "근력 운동";
        if (type == ExerciseSessionRecord.EXERCISE_TYPE_SWIMMING_POOL
                || type == ExerciseSessionRecord.EXERCISE_TYPE_SWIMMING_OPEN_WATER) return "수영";
        if (type == ExerciseSessionRecord.EXERCISE_TYPE_HIKING) return "등산";
        if (type == ExerciseSessionRecord.EXERCISE_TYPE_YOGA) return "요가";
        if (type == ExerciseSessionRecord.EXERCISE_TYPE_PILATES) return "필라테스";
        if (type == ExerciseSessionRecord.EXERCISE_TYPE_HIGH_INTENSITY_INTERVAL_TRAINING) return "HIIT";
        if (type == ExerciseSessionRecord.EXERCISE_TYPE_ELLIPTICAL) return "일립티컬";
        if (type == ExerciseSessionRecord.EXERCISE_TYPE_STRETCHING) return "스트레칭";
        if (type == ExerciseSessionRecord.EXERCISE_TYPE_DANCING) return "댄스";
        if (type == ExerciseSessionRecord.EXERCISE_TYPE_TENNIS) return "테니스";
        if (type == ExerciseSessionRecord.EXERCISE_TYPE_BADMINTON) return "배드민턴";
        if (type == ExerciseSessionRecord.EXERCISE_TYPE_SOCCER) return "축구";
        if (type == ExerciseSessionRecord.EXERCISE_TYPE_BASKETBALL) return "농구";
        return "운동";
    }

    private static int exerciseTypeForTitle(String title) {
        String value = title == null ? "" : title.toLowerCase();
        if (value.contains("걷") || value.contains("walk")) return ExerciseSessionRecord.EXERCISE_TYPE_WALKING;
        if (value.contains("달리") || value.contains("러닝") || value.contains("run")) return ExerciseSessionRecord.EXERCISE_TYPE_RUNNING;
        if (value.contains("자전거") || value.contains("사이클") || value.contains("cycle")) return ExerciseSessionRecord.EXERCISE_TYPE_BIKING;
        if (value.contains("수영") || value.contains("swim")) return ExerciseSessionRecord.EXERCISE_TYPE_SWIMMING_POOL;
        if (value.contains("요가") || value.contains("yoga")) return ExerciseSessionRecord.EXERCISE_TYPE_YOGA;
        if (value.contains("근력") || value.contains("웨이트") || value.contains("weight")) return ExerciseSessionRecord.EXERCISE_TYPE_STRENGTH_TRAINING;
        return ExerciseSessionRecord.EXERCISE_TYPE_OTHER_WORKOUT;
    }

    /**
     * connect-client 1.1.0-alpha10 exposes Kotlin record constructors to
     * Java, but not the newer Builder API.  Locate that stable 49-argument
     * constructor and explicitly fill only the nutrients this app owns.
     */
    private static NutritionRecord createNutritionRecord(Instant now, ZoneOffset offset,
                                                          String title, double calories,
                                                          double protein, double carbs) throws Exception {
        Constructor<?> selected = null;
        for (Constructor<?> candidate : NutritionRecord.class.getConstructors()) {
            if (candidate.getParameterTypes().length == 49) {
                selected = candidate;
                break;
            }
        }
        if (selected == null) throw new IllegalStateException("NutritionRecord constructor unavailable");
        Object[] values = new Object[49];
        values[0] = now; values[1] = offset; values[2] = now; values[3] = offset;
        // The first 42 nutrient positions are nullable. Energy is #4,
        // protein #24, and total carbohydrate #31 in the SDK constructor.
        values[7] = Energy.kilocalories(Math.max(0d, calories));
        values[27] = Mass.grams(Math.max(0d, protein));
        values[34] = Mass.grams(Math.max(0d, carbs));
        values[46] = title == null || title.trim().isEmpty() ? "식단 기록" : title.trim();
        values[47] = 0; // unspecified meal type; the user-selected title is retained.
        values[48] = new Metadata();
        return (NutritionRecord) selected.newInstance(values);
    }

    @SuppressWarnings({"unchecked", "rawtypes"})
    private static void insert(final HealthConnectClient client, final List<? extends Record> records) throws InterruptedException {
        BuildersKt.runBlocking(EmptyCoroutineContext.INSTANCE,
                new Function2<CoroutineScope, Continuation<Object>, Object>() {
                    @Override public Object invoke(CoroutineScope scope, Continuation<Object> continuation) {
                        return client.insertRecords((List) records, (Continuation) continuation);
                    }
                });
    }

    @SuppressWarnings({"unchecked", "rawtypes"})
    private static <T extends Record> List<T> read(final HealthConnectClient client, final Class<T> recordClass, final TimeRangeFilter range) throws InterruptedException {
        try { return (List<T>) ((ReadRecordsResponse<T>) BuildersKt.runBlocking(
                EmptyCoroutineContext.INSTANCE,
                new Function2<CoroutineScope, Continuation<? super ReadRecordsResponse<T>>, Object>() {
                    @Override public Object invoke(CoroutineScope scope, Continuation<? super ReadRecordsResponse<T>> continuation) {
                        KClass<T> type = Reflection.getOrCreateKotlinClass(recordClass);
                        ReadRecordsRequest<T> request = new ReadRecordsRequest<>(type, range, Collections.emptySet(), false, 1000, null);
                        return client.readRecords(request, (Continuation) continuation);
                    }
                })).getRecords();
        } catch (Exception ignored) { return Collections.emptyList(); }
    }

    @SuppressWarnings({"unchecked", "rawtypes"})
    private static long aggregateSteps(final HealthConnectClient client, final TimeRangeFilter range) {
        try {
            AggregationResult result = (AggregationResult) BuildersKt.runBlocking(
                    EmptyCoroutineContext.INSTANCE,
                    new Function2<CoroutineScope, Continuation<? super AggregationResult>, Object>() {
                        @Override public Object invoke(CoroutineScope scope, Continuation<? super AggregationResult> continuation) {
                            AggregateRequest request = new AggregateRequest(
                                    Collections.singleton(StepsRecord.COUNT_TOTAL), range, Collections.emptySet());
                            return client.aggregate(request, continuation);
                        }
                    });
            Long total = (Long) result.get(StepsRecord.COUNT_TOTAL);
            return total == null ? 0L : total;
        } catch (Exception ignored) {
            long total = 0L;
            try { for (StepsRecord item : read(client, StepsRecord.class, range)) total += item.getCount(); }
            catch (Exception ignoredAgain) { }
            return total;
        }
    }
}
