import 'package:flutter/foundation.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import 'package:flutter_timezone/flutter_timezone.dart';
import 'package:timezone/data/latest_all.dart' as tzdata;
import 'package:timezone/timezone.dart' as tz;

/// Schedules the repeating daily-briefing notification (local, offline,
/// OS-scheduled). FCM only *reconfigures* it; this fires the alarm, so a
/// dropped/delayed push is never a lost alarm.
class NotificationService {
  NotificationService._();
  static final NotificationService instance = NotificationService._();

  static const int _notificationId = 1001;
  static const String _channelId = 'daily_briefing';

  final FlutterLocalNotificationsPlugin _plugin = FlutterLocalNotificationsPlugin();

  Future<void> init() async {
    try {
      tzdata.initializeTimeZones();
      try {
        final info = await FlutterTimezone.getLocalTimezone();
        tz.setLocalLocation(tz.getLocation(info.identifier));
      } catch (_) {
        // fall back to UTC; schedule still fires (offset by the timezone delta)
      }
      const android = AndroidInitializationSettings('@mipmap/ic_launcher');
      const darwin = DarwinInitializationSettings();
      await _plugin.initialize(
        settings: const InitializationSettings(android: android, iOS: darwin),
      );
      await _requestPermissions();
    } catch (e) {
      debugPrint('NotificationService init failed: $e');
    }
  }

  Future<void> _requestPermissions() async {
    await _plugin
        .resolvePlatformSpecificImplementation<AndroidFlutterLocalNotificationsPlugin>()
        ?.requestNotificationsPermission();
    await _plugin
        .resolvePlatformSpecificImplementation<IOSFlutterLocalNotificationsPlugin>()
        ?.requestPermissions(alert: true, badge: true, sound: true);
  }

  /// Schedule (or re-schedule) the daily notification at [time] "HH:MM".
  Future<void> scheduleDaily(String time) async {
    await cancel();
    final parts = time.split(':');
    final hour = int.tryParse(parts.isNotEmpty ? parts[0].trim() : '') ?? 7;
    final minute = int.tryParse(parts.length > 1 ? parts[1].trim() : '') ?? 0;

    final now = tz.TZDateTime.now(tz.local);
    var scheduled =
        tz.TZDateTime(tz.local, now.year, now.month, now.day, hour, minute);
    if (scheduled.isBefore(now)) {
      scheduled = scheduled.add(const Duration(days: 1));
    }

    await _plugin.zonedSchedule(
      id: _notificationId,
      title: 'Daily briefing',
      body: 'Tap to start your morning briefing',
      scheduledDate: scheduled,
      notificationDetails: const NotificationDetails(
        android: AndroidNotificationDetails(
          _channelId,
          'Daily briefing',
          channelDescription: 'Daily briefing reminder',
          importance: Importance.max,
          priority: Priority.high,
        ),
        iOS: DarwinNotificationDetails(),
      ),
      androidScheduleMode: AndroidScheduleMode.inexactAllowWhileIdle,
      matchDateTimeComponents: DateTimeComponents.time,
    );
  }

  Future<void> cancel() => _plugin.cancel(id: _notificationId);
}
