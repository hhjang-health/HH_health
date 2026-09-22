# 1.0.35 verification — 2026-09-19

- Debug APK built successfully, version code 102610035, arm64-v8a, Android 8+.
- APK signature verified; launcher resolves to inset adaptive icon resource.
- Official public WonderPul Plus endpoint tested through the application transport: 삼성SDI동탄 breakfast and dinner K1 menus returned. Lunch has no K1–K4 entries on this date; non-kitchen corners intentionally excluded.
- Parser checked for meal separation, date filtering, K1/K4 normalization and exclusion of Ramyun.
- Existing-install Dongtan migration checked; a subsequently deleted restaurant is not resurrected on restart.
- Desktop Kivy UI exercised at 412×892 and 360×780. All five tabs checked at 360px width; dock does not overlap scroll viewport. Right-side meal add controls checked. Workout total tested with 12,345 minutes; text fits.
- Nutrition preview used sample meal data; restaurant preview used live source data.
- No Android device was connected. Android installation, launch, Health Connect, and mobile-network execution still require device validation.
