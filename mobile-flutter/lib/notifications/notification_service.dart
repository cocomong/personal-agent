import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import 'package:flutter_timezone/flutter_timezone.dart';
import 'package:timezone/data/latest_all.dart' as tzdata;
import 'package:timezone/timezone.dart' as tz;

/// Schedules the repeating daily-briefing notification (local, offline,
/// OS-scheduled) and shows immediate link notifications pushed from the
/// assistant (FCM data message type `open_url`). FCM only *reconfigures* the
/// briefing alarm; the local schedule fires it, so a dropped/delayed push is
/// never a lost alarm.
///
/// Link notifications carry the URL as the notification payload; the tap
/// handler registered at [init] routes it to the browser (see main.dart).
class NotificationService {
  NotificationService._();
  static final NotificationService instance = NotificationService._();

  static const int _briefingId = 1001;
  static const String _briefingChannelId = 'daily_briefing';
  static const String _linkChannelId = 'link_actions';

  final FlutterLocalNotificationsPlugin _plugin = FlutterLocalNotificationsPlugin();
  bool _initialized = false;
  int _nextLinkId = 2000;
  void Function(String? payload, String? actionId)? _onTap;

  /// Invoked (from main) when a notification is tapped: [payload] is the
  /// notification payload (a URL string, or JSON {url, actions} for links
  /// with action buttons); [actionId] is 'view'/'approve'/... or null when
  /// the notification body itself was tapped.
  set onNotificationTap(void Function(String? payload, String? actionId)? cb) =>
      _onTap = cb;

  /// Idempotent init. Safe to call from bootstrap AND from the FCM background
  /// isolate (which runs in its own process/isolate).
  Future<void> init() async {
    if (_initialized) return;
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
        onDidReceiveNotificationResponse: (response) =>
            _onTap?.call(response.payload, response.actionId),
      );
      await _requestPermissions();
      _initialized = true;
      // App launched by tapping a notification while terminated: the payload
      // is only available here, right after initialize.
      final launch = await _plugin.getNotificationAppLaunchDetails();
      if (launch?.didNotificationLaunchApp ?? false) {
        _onTap?.call(launch?.notificationResponse?.payload,
            launch?.notificationResponse?.actionId);
      }
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
    await cancelBriefing();
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
      id: _briefingId,
      title: 'Daily briefing',
      body: 'Tap to start your morning briefing',
      scheduledDate: scheduled,
      notificationDetails: const NotificationDetails(
        android: AndroidNotificationDetails(
          _briefingChannelId,
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

  Future<void> cancelBriefing() => _plugin.cancel(id: _briefingId);

  /// Show an immediate plain notification (no tap action, no payload) —
  /// used for informational pushes like the PM "estimate approved" notice.
  Future<void> showNotice({required String title, required String body}) async {
    if (!_initialized) await init();
    final id = _nextLinkId++;
    try {
      await _plugin.show(
        id: id,
        title: title,
        body: body,
        notificationDetails: const NotificationDetails(
          android: AndroidNotificationDetails(
            _linkChannelId,
            'Action links',
            channelDescription: 'Links sent by the assistant (approvals, etc.)',
            importance: Importance.high,
            priority: Priority.high,
          ),
          iOS: DarwinNotificationDetails(),
        ),
      );
    } catch (e) {
      debugPrint('showNotice failed: $e');
    }
  }

  /// Show an immediate action notification. [url] is the default target
  /// (body tap). When [approveUrl]/[rejectUrl] are present the notification
  /// gains View / Approve (Reject) action buttons, and the payload becomes
  /// JSON {url, actions:{view, approve, reject}} so taps can route to the
  /// right URL. Payload stays a plain URL string when there are no actions
  /// (backwards compatible with existing pushes).
  Future<void> showLink({
    required String title,
    required String body,
    required String url,
    String? approveUrl,
    String? rejectUrl,
  }) async {
    if (!_initialized) await init();
    final id = _nextLinkId++;
    final hasActions = approveUrl != null;
    final payload = hasActions
        ? jsonEncode({
            'url': url,
            'actions': {
              'view': url,
              'approve': approveUrl,
              if (rejectUrl != null) 'reject': rejectUrl,
            },
          })
        : url;
    final androidActions = hasActions
        ? [
            const AndroidNotificationAction('view', 'View',
                icon: DrawableResourceAndroidBitmap('ic_launcher')),
            const AndroidNotificationAction('approve', 'Approve',
                icon: DrawableResourceAndroidBitmap('ic_launcher')),
            if (rejectUrl != null)
              const AndroidNotificationAction('reject', 'Reject',
                  icon: DrawableResourceAndroidBitmap('ic_launcher')),
          ]
        : null;
    try {
      await _plugin.show(
        id: id,
        title: title,
        body: body,
        notificationDetails: NotificationDetails(
          android: AndroidNotificationDetails(
            _linkChannelId,
            'Action links',
            channelDescription: 'Links sent by the assistant (approvals, etc.)',
            importance: Importance.high,
            priority: Priority.high,
            actions: androidActions,
          ),
          iOS: const DarwinNotificationDetails(),
        ),
        payload: payload,
      );
    } catch (e) {
      // Fall back to a plain notification (no action buttons) if the platform
      // rejects the action configuration.
      debugPrint('showLink with actions failed ($e); retrying plain');
      await _plugin.show(
        id: id,
        title: title,
        body: body,
        notificationDetails: const NotificationDetails(
          android: AndroidNotificationDetails(
            _linkChannelId,
            'Action links',
            channelDescription: 'Links sent by the assistant (approvals, etc.)',
            importance: Importance.high,
            priority: Priority.high,
          ),
          iOS: DarwinNotificationDetails(),
        ),
        payload: url,
      );
    }
  }
}
