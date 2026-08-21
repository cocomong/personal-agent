# Vapi Flutter App — Setup

A Flutter (Dart) app implementing the Construction PM assistant's mobile client:
**Vapi** (voice + same-session text), **ElevenLabs** voice engine. See `doc/SYSTEM_DESIGN.md` §8.

---

## Requirements

- **Flutter** with **Dart SDK ≥ 3.6.0** (`vapi` 0.1.0 requires it).
  > ✅ Verified working on this machine: **Flutter 3.44.9 / Dart 3.12.2** (satisfies the constraint).
  > If you hit a Dart-version error on an older machine, run `flutter upgrade`.
- **iOS 13+** / **Android SDK 24+** (via the `daily_flutter` WebRTC dependency; `minSdk = 24` is already set in `android/app/build.gradle.kts`).

## 1. Create the project (if not already scaffolded)

> ✅ This scaffold already has `android/` and `ios/` platform folders generated
> (run via `flutter create --platforms=android,ios .`). Skip `flutter create`
> and go straight to `flutter pub get`:

```bash
flutter pub get
```

To (re)generate platform folders from scratch:

```bash
flutter create --platforms=android,ios --org com.personalagent .
flutter pub add vapi
```

## 2. Configure your keys

Edit `lib/config.dart`:

```dart
const String vapiPublicKey  = '<YOUR_VAPI_PUBLIC_KEY>';
const String vapiAssistantId = '<YOUR_VAPI_ASSISTANT_ID>';
```

(Public key + assistant id come from the Vapi dashboard — see `backend/VAPI_ASSISTANT.md`.)

## 3. iOS setup (info.plist + Podfile)

`ios/Podfile` — set the deployment target and the microphone preprocessor flag:

```ruby
platform :ios, '13.0'

post_install do |installer|
  installer.pods_project.targets.each do |target|
    flutter_additional_ios_build_settings(target)
    target.build_configurations.each do |config|
      config.build_settings['GCC_PREPROCESSOR_DEFINITIONS'] ||= [
        '$(inherited)',
        'PERMISSION_MICROPHONE=1',
      ]
    end
  end
end
```

`ios/Runner/Info.plist`:

```xml
<key>NSMicrophoneUsageDescription</key>
<string>This app requires access to the microphone for live voice calls.</string>
```

Also enable **Audio** background mode (Runner capabilities) for in-background calls.

## 4. Android setup (manifest + minSdk)

`android/app/src/main/AndroidManifest.xml`:

```xml
<uses-permission android:name="android.permission.INTERNET" />
<uses-permission android:name="android.permission.RECORD_AUDIO" />
<uses-permission android:name="android.permission.MODIFY_AUDIO_SETTINGS" />
```

`android/app/build.gradle.kts` — set `minSdk = 24`.

> The `permission_handler` package also needs its gradle flags (`PERMISSION_MICROPHONE`); follow the `permission_handler` README if you add it manually.

## 5. Run

```bash
flutter run          # on a connected device / emulator
flutter build ios    # or: flutter build apk
```

---

## Project layout

```
lib/
├── main.dart                       # entry: awaits VapiClient.platformInitialized, runs app
├── config.dart                     # VAPI_PUBLIC_KEY + ASSISTANT_ID
├── agent_screen.dart               # voice-text UI, mic-mute-on-type, shared transcript
├── session/vapi_session_controller.dart   # VapiClient/VapiCall wrapper (start/send/setMuted/stop)
└── models/transcript_entry.dart    # shared transcript row
```

## Notes

- **Same-session voice + text**: `start()` drives the voice call; `sendUserText()` sends a typed
  `add-message` on the SAME call, so the agent keeps context. Mic is muted while in text mode.
- **ElevenLabs voice**: configure `voice.provider='11labs'` on the assistant (dashboard), or pass
  inline `assistant:` config to `start()`.
- **Native WebRTC**: requires a real device (emulator audio can be choppy with echo cancellation).
