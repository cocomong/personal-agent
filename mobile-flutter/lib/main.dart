import 'package:flutter/material.dart';
import 'package:vapi/vapi.dart';

import 'agent_screen.dart';
import 'notifications/fcm_service.dart';
import 'notifications/notification_service.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  // Wait for the Vapi SDK to be ready (required on web; instant on mobile).
  await VapiClient.platformInitialized.future;

  // Local daily-briefing notification (offline, OS-scheduled).
  await NotificationService.instance.init();
  // FCM registration + briefing_time sync (graceful if Firebase isn't set up).
  await FcmService.instance.init();

  runApp(const PersonalAgentApp());
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
