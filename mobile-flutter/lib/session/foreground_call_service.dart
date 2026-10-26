import 'package:flutter/services.dart';

/// Keeps a voice call alive while the screen is off.
///
/// On Android this drives a foreground service (microphone type) plus a
/// partial wake lock: without it, Doze suspends the process shortly after the
/// screen turns off and the WebRTC session drops. Best-effort by design — on
/// platforms without the native implementation (widget tests, iOS) the calls
/// are silently ignored and the call still works while the app is foregrounded.
class ForegroundCallService {
  ForegroundCallService._();

  static const MethodChannel _channel =
      MethodChannel('personal_agent/voice_call');

  static Future<void> start() => _invoke('start');

  static Future<void> stop() => _invoke('stop');

  static Future<void> _invoke(String method) async {
    try {
      await _channel.invokeMethod<void>(method);
    } on MissingPluginException {
      // No native implementation (tests / unsupported platform).
    } on PlatformException {
      // Service refused (e.g. permission): the call still works in foreground.
    }
  }
}
