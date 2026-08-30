import 'dart:convert';

import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;

import '../auth/session_store.dart';
import '../config.dart';
import 'notification_service.dart';

/// Registers this device's FCM token with n8n (the `device_tokens` table) and
/// handles the `briefing_time_changed` data message by re-scheduling the local
/// notification. Degrades gracefully when Firebase isn't configured yet
/// (falls back to the default 07:00 local notification).
class FcmService {
  FcmService._();
  static final FcmService instance = FcmService._();

  bool _configured = false;
  bool get isConfigured => _configured;

  String? _fcmToken;

  Future<void> init() async {
    try {
      await Firebase.initializeApp();
      final messaging = FirebaseMessaging.instance;
      await messaging.requestPermission();
      final token = await messaging.getToken();
      _configured = token != null && token.isNotEmpty;
      _fcmToken = token;

      if (_configured) {
        FirebaseMessaging.onBackgroundMessage(firebaseMessagingBackgroundHandler);
        final briefingTime = await _registerDevice(token!);
        if (briefingTime != null && briefingTime.isNotEmpty) {
          await NotificationService.instance.scheduleDaily(briefingTime);
        }
        FirebaseMessaging.onMessage.listen(_onMessage);
      }
    } catch (e) {
      debugPrint('FCM not configured ($e) — using default briefing time');
    }

    if (!_configured) {
      // No Firebase project yet: still fire a local notification at the default.
      await NotificationService.instance.scheduleDaily('07:00');
    }
  }

  /// Re-registers the device AFTER sign-in, so the backend can associate the
  /// FCM token with the authenticated user (device_tokens -> company).
  Future<void> registerAfterLogin() async {
    final token = _fcmToken;
    if (token == null || token.isEmpty) return;
    try {
      final briefingTime = await _registerDevice(token);
      if (briefingTime != null && briefingTime.isNotEmpty) {
        await NotificationService.instance.scheduleDaily(briefingTime);
      }
    } catch (e) {
      debugPrint('register_after_login failed: $e');
    }
  }

  Future<String?> _registerDevice(String token) async {
    try {
      final headers = {'Content-Type': 'application/json'};
      final sessionToken = SessionStore.instance.token;
      if (sessionToken != null && sessionToken.isNotEmpty) {
        headers['X-User-Token'] = sessionToken;
      }
      final resp = await http
          .post(
            Uri.parse('$n8nBaseUrl/webhook/device/register'),
            headers: headers,
            body: jsonEncode({
              'token': token,
              'platform':
                  defaultTargetPlatform == TargetPlatform.iOS ? 'ios' : 'android',
              'device_name': 'phone',
            }),
          )
          .timeout(const Duration(seconds: 10));
      if (resp.statusCode == 200) {
        final data = jsonDecode(resp.body) as Map<String, dynamic>;
        return data['briefing_time'] as String?;
      }
    } catch (e) {
      debugPrint('register_device failed: $e');
    }
    return null;
  }

  void _onMessage(RemoteMessage message) => _handleData(message.data);

  Future<void> _handleData(Map<String, dynamic> data) async {
    final time = data['briefing_time'];
    if (data['type'] == 'briefing_time_changed' &&
        time is String &&
        time.isNotEmpty) {
      await NotificationService.instance.scheduleDaily(time);
    }
  }
}

/// Top-level background handler (isolated VM entry point) for the data message
/// when the app is terminated. Re-schedules the local notification directly.
@pragma('vm:entry-point')
Future<void> firebaseMessagingBackgroundHandler(RemoteMessage message) async {
  final data = message.data;
  final time = data['briefing_time'];
  if (data['type'] == 'briefing_time_changed' &&
      time is String &&
      time.isNotEmpty) {
    await NotificationService.instance.init();
    await NotificationService.instance.scheduleDaily(time);
  }
}
