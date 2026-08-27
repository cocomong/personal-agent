import 'dart:async';

import 'package:flutter/material.dart';

import 'agent_screen.dart';
import 'notifications/fcm_service.dart';
import 'notifications/notification_service.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  // Show the UI immediately; all async setup (notifications, FCM, briefing
  // sync) runs in the background so a slow or hanging init can never leave a
  // blank launch screen. VapiClient.platformInitialized is awaited lazily by
  // VapiSessionController when a call actually starts.
  runApp(const PersonalAgentApp());
  unawaited(_bootstrap());
}

Future<void> _bootstrap() async {
  try {
    await NotificationService.instance.init();
    await FcmService.instance.init();
  } catch (e) {
    debugPrint('bootstrap error: $e');
  }
}

class PersonalAgentApp extends StatelessWidget {
  const PersonalAgentApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Personal Agent',
      theme: ThemeData.dark(useMaterial3: true),
      home: const AgentScreen(),
    );
  }
}
